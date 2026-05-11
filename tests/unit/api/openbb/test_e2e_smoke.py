"""End-to-end smoke tests for the OpenBB SSE flow.

These tests use FastAPI ``TestClient`` with streaming to capture the SSE
stream and verify event types appear in the expected order.

Marked ``pytest.mark.integration`` — skipped in fast unit runs unless
``ATLAS_INTEGRATION_TESTS=true`` is set. Requires a live DB with SP02 views
populated.

For CI without a live DB: the unknown-intent path below does NOT touch DB
(it short-circuits in ``_stream`` before dispatch), so the fallback test
runs regardless.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from atlas.api import app

os.environ.setdefault("OPENBB_BACKEND_API_KEY", "")
os.environ.setdefault("ATLAS_AUTH_DISABLED", "true")

client = TestClient(app)


def _parse_sse_stream(content: bytes) -> list[dict]:
    """Parse raw SSE bytes into a list of event dicts.

    sse-starlette emits each event as ``data: <json>\\n\\n``. Some lines
    may be ``: ping`` heartbeats — ignore them.
    """
    events = []
    for line in content.decode().splitlines():
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                try:
                    events.append(json.loads(payload))
                except json.JSONDecodeError:
                    pass
    return events


class TestUnknownIntentE2E:
    """These tests don't require a DB — unknown intent short-circuits."""

    def test_unknown_intent_returns_200(self) -> None:
        resp = client.post(
            "/v1/query",
            json={"messages": [{"role": "user", "content": "what is the weather today?"}]},
        )
        assert resp.status_code == 200

    def test_unknown_intent_stream_contains_fallback_text(self) -> None:
        with client.stream(
            "POST",
            "/v1/query",
            json={
                "messages": [{"role": "user", "content": "completely unrecognised query abc123"}]
            },
        ) as resp:
            content = resp.read()
        events = _parse_sse_stream(content)
        message_events = [e for e in events if e.get("type") == "message_chunk"]
        assert message_events, "Fallback must emit at least one message_chunk"
        full_text = " ".join(e["data"] for e in message_events)
        assert "regime" in full_text.lower() or "rotation" in full_text.lower()

    def test_unknown_intent_stream_ends_with_done(self) -> None:
        with client.stream(
            "POST",
            "/v1/query",
            json={"messages": [{"role": "user", "content": "random gibberish 12345"}]},
        ) as resp:
            content = resp.read()
        events = _parse_sse_stream(content)
        types = [e.get("type") for e in events]
        assert types[-1] == "done", f"Last event should be done, got: {types[-1]}"


# All handler-touching tests below require a live DB (SP02 views).
pytestmark_db = pytest.mark.skipif(
    os.getenv("ATLAS_INTEGRATION_TESTS") != "true",
    reason="DB-touching e2e — set ATLAS_INTEGRATION_TESTS=true to run",
)


@pytestmark_db
class TestRegimeE2E:
    def test_regime_query_returns_sse_stream(self) -> None:
        resp = client.post(
            "/v1/query",
            json={"messages": [{"role": "user", "content": "show me current regime"}]},
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_regime_stream_contains_required_event_types(self) -> None:
        with client.stream(
            "POST",
            "/v1/query",
            json={"messages": [{"role": "user", "content": "market regime"}]},
        ) as resp:
            content = resp.read()
        events = _parse_sse_stream(content)
        types = [e.get("type") for e in events]
        assert "reasoning_step" in types
        assert "done" in types
        # Either table (populated) or message_chunk (empty view) — both valid
        assert "table" in types or "message_chunk" in types


@pytestmark_db
class TestLeadersE2E:
    def test_leaders_stream_ends_with_done(self) -> None:
        with client.stream(
            "POST",
            "/v1/query",
            json={"messages": [{"role": "user", "content": "top RS stocks"}]},
        ) as resp:
            content = resp.read()
        events = _parse_sse_stream(content)
        types = [e.get("type") for e in events]
        assert types[-1] == "done", f"Last event should be done, got: {types[-1]}"


@pytestmark_db
class TestRotationE2E:
    def test_rotation_stream_contains_chart_when_data_available(self) -> None:
        with client.stream(
            "POST",
            "/v1/query",
            json={"messages": [{"role": "user", "content": "sector rotation"}]},
        ) as resp:
            content = resp.read()
        events = _parse_sse_stream(content)
        types = [e.get("type") for e in events]
        # If the view is populated, there should be a chart event
        if "table" in types:
            assert "chart" in types, "Rotation must emit chart when table data available"
