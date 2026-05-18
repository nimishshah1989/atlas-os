"""Shared NSE scraper base — session warming, rate limit, retry."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
import responses

from atlas.data_prereqs.v6.base import BaseScraper, RateLimitExceeded


@responses.activate
def test_base_scraper_warms_session_with_homepage():
    """First request triggers a homepage GET to capture NSE session cookies."""
    responses.add(
        responses.GET,
        "https://www.nseindia.com/",
        body="<html></html>",
        headers={"Set-Cookie": "nsit=abc; path=/"},
    )
    responses.add(responses.GET, "https://www.nseindia.com/api/whatever", json={"ok": True})
    s = BaseScraper()
    out = s.get("https://www.nseindia.com/api/whatever")
    assert out.json() == {"ok": True}
    assert len(responses.calls) == 2
    assert responses.calls[0].request.url == "https://www.nseindia.com/"


@responses.activate
def test_base_scraper_uses_browser_headers():
    """All requests carry browser-like User-Agent + Accept headers."""
    responses.add(responses.GET, "https://www.nseindia.com/", body="ok")
    responses.add(responses.GET, "https://www.nseindia.com/api/x", json={})
    s = BaseScraper()
    s.get("https://www.nseindia.com/api/x")
    final_req = responses.calls[-1].request
    assert "Mozilla/5.0" in final_req.headers["User-Agent"]
    assert final_req.headers["Accept"].startswith("application/json")


@responses.activate
def test_base_scraper_retries_on_503():
    """503 from NSE → retry with backoff, succeed on second attempt."""
    responses.add(responses.GET, "https://www.nseindia.com/", body="ok")
    responses.add(responses.GET, "https://www.nseindia.com/api/y", status=503)
    responses.add(responses.GET, "https://www.nseindia.com/api/y", json={"data": 1})
    with patch("time.sleep"):
        s = BaseScraper(retry_max=3, retry_backoff_sec=0.01)
        out = s.get("https://www.nseindia.com/api/y")
    assert out.json() == {"data": 1}


@responses.activate
def test_base_scraper_raises_after_max_retries():
    """All retries exhausted → RateLimitExceeded."""
    responses.add(responses.GET, "https://www.nseindia.com/", body="ok")
    for _ in range(4):
        responses.add(responses.GET, "https://www.nseindia.com/api/z", status=429)
    with patch("time.sleep"):
        s = BaseScraper(retry_max=3, retry_backoff_sec=0.01)
        with pytest.raises(RateLimitExceeded):
            s.get("https://www.nseindia.com/api/z")


def test_base_scraper_enforces_min_interval_between_requests():
    """min_interval_sec=0.5 means 2 calls take >= 0.5s."""
    s = BaseScraper(min_interval_sec=0.5)
    t0 = time.monotonic()
    s._wait_for_interval()
    s._wait_for_interval()
    assert time.monotonic() - t0 >= 0.49
