"""Shared scraper base for NSE / external data sources.

Responsibilities:
- Session warming (visit https://www.nseindia.com/ once to capture cookies)
- Browser-like headers on every request
- Min-interval rate limiting (default 0.5s between calls)
- Exponential-backoff retry on 429/503 (default 3 retries)
- Raise RateLimitExceeded if all retries fail
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests
import structlog

log = structlog.get_logger()


class RateLimitExceeded(Exception):  # noqa: N818 — spec-defined name; callers import by this exact name
    """All retries exhausted; the upstream source is throttling us."""


@dataclass
class BaseScraper:
    min_interval_sec: float = 0.5
    retry_max: int = 3
    retry_backoff_sec: float = 1.0
    nse_homepage: str = "https://www.nseindia.com/"
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )

    # Non-init fields — initialised in __post_init__
    session: requests.Session = field(init=False, repr=False)
    _warmed: bool = field(init=False, default=False, repr=False)
    _last_request_at: float | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self._warmed = False
        self._last_request_at = None

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.nse_homepage,
        }

    def _warm_session(self) -> None:
        if self._warmed:
            return
        try:
            self.session.get(self.nse_homepage, headers=self._headers(), timeout=10)
            self._warmed = True
        except requests.RequestException as exc:
            log.warning("session_warm_failed", err=str(exc))

    def _wait_for_interval(self) -> None:
        if self._last_request_at is None:
            self._last_request_at = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_sec:
            time.sleep(self.min_interval_sec - elapsed)
        self._last_request_at = time.monotonic()

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        """GET url with session warming, rate limiting, and retry on 429/503."""
        self._warm_session()
        attempt = 0
        while True:
            self._wait_for_interval()
            resp = self.session.get(url, headers=self._headers(), params=params, timeout=30)
            if resp.status_code in (429, 503):
                attempt += 1
                if attempt > self.retry_max:
                    log.error("retries_exhausted", url=url, status=resp.status_code)
                    raise RateLimitExceeded(f"{url} status {resp.status_code}")
                backoff = self.retry_backoff_sec * (2 ** (attempt - 1))
                log.info("retry", url=url, attempt=attempt, backoff=backoff)
                time.sleep(backoff)
                continue
            resp.raise_for_status()
            return resp
