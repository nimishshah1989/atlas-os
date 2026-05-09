"""Unit tests for atlas.api.internal_recompute — mocked DB + subprocess."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_SECRET = "test-secret"  # noqa: S105 — test fixture value, not a real secret
_AUTH_HEADER = {"Authorization": f"Bearer {_SECRET}"}


@pytest.fixture(autouse=True)
def set_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ATLAS_INTERNAL_SECRET is always set for all tests in this module."""
    monkeypatch.setenv("ATLAS_INTERNAL_SECRET", _SECRET)


def _make_engine_mock(existing_run_id: str | None) -> MagicMock:
    """Return a mock Engine whose .connect() context manager yields a conn mock.

    If existing_run_id is None, fetchone() returns None (concurrency passes).
    If given a string, fetchone() returns a row-like mock (triggers 409).
    """
    conn = MagicMock()
    execute_result = MagicMock()

    if existing_run_id is None:
        execute_result.fetchone.return_value = None
    else:
        row = MagicMock()
        row.__getitem__ = lambda _, idx: existing_run_id if idx == 0 else None  # type: ignore[misc]
        execute_result.fetchone.return_value = row

    conn.execute.return_value = execute_result

    engine = MagicMock()
    # engine.connect() used as context manager — must yield conn
    engine.connect.return_value.__enter__ = lambda _: conn
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    # Expose conn directly so tests can inspect execute call_args without
    # having to navigate through the lambda-based __enter__ mock.
    engine._test_conn = conn

    return engine


@pytest.fixture
def mock_engine() -> MagicMock:
    return _make_engine_mock(existing_run_id=None)


@pytest.fixture
def client(mock_engine: MagicMock) -> Any:
    """TestClient with get_engine overridden to a MagicMock."""
    from atlas.api.internal_recompute import app
    from atlas.db import get_engine

    app.dependency_overrides[get_engine] = lambda: mock_engine
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. No bearer → 401
# ---------------------------------------------------------------------------


class TestAuth:
    def test_post_without_bearer_returns_401(self, client: TestClient) -> None:
        response = client.post("/internal/recompute/m3")
        assert response.status_code == 401
        assert response.json()["detail"]["error_code"] == "invalid_bearer"

    def test_post_with_wrong_bearer_returns_401(self, client: TestClient) -> None:
        response = client.post(
            "/internal/recompute/m3",
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error_code"] == "invalid_bearer"

    def test_post_when_secret_not_configured_returns_500(
        self, monkeypatch: pytest.MonkeyPatch, client: TestClient
    ) -> None:
        """Missing ATLAS_INTERNAL_SECRET → structured 500, not a 401 or crash."""
        # autouse fixture sets the env var; delete it for this test only.
        monkeypatch.delenv("ATLAS_INTERNAL_SECRET", raising=False)
        response = client.post("/internal/recompute/m3", headers=_AUTH_HEADER)
        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail["error_code"] == "secret_not_configured"


# ---------------------------------------------------------------------------
# 2. Invalid milestone → 400
# ---------------------------------------------------------------------------


class TestMilestoneAllowlist:
    def test_post_with_invalid_milestone_returns_400(self, client: TestClient) -> None:
        response = client.post("/internal/recompute/m99", headers=_AUTH_HEADER)
        assert response.status_code == 400
        body = response.json()
        # FastAPI wraps HTTPException detail in {"detail": ...}
        detail = body["detail"]
        assert detail["error_code"] == "invalid_milestone"
        allowed = detail["context"]["allowed"]
        # "all" is deferred in v0 — allowlist is only m3/m4/m5
        assert sorted(allowed) == ["m3", "m4", "m5"]

    def test_post_all_milestone_returns_400_in_v0(self, client: TestClient) -> None:
        """'all' is not in the v0 allowlist — allowlist check fires before concurrency check."""
        response = client.post("/internal/recompute/all", headers=_AUTH_HEADER)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error_code"] == "invalid_milestone"
        assert "all" not in detail["context"]["allowed"]


# ---------------------------------------------------------------------------
# 3. Concurrent run → 409
# ---------------------------------------------------------------------------


class TestConcurrencyCheck:
    def test_post_when_concurrent_run_returns_409(self) -> None:
        existing = str(uuid.uuid4())
        engine_mock = _make_engine_mock(existing_run_id=existing)

        from atlas.api.internal_recompute import app
        from atlas.db import get_engine

        app.dependency_overrides[get_engine] = lambda: engine_mock
        try:
            tc = TestClient(app, raise_server_exceptions=False)
            response = tc.post("/internal/recompute/m3", headers=_AUTH_HEADER)
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["error_code"] == "already_running"
        assert detail["context"]["run_id"] == existing

    def test_post_all_returns_400_even_when_m3_running(self) -> None:
        """'all' is not in the v0 allowlist — allowlist check fires before concurrency check.

        Even if M3 is running, posting /all must return 400 (not 409), because
        the allowlist guard short-circuits before the DB concurrency check.
        """
        existing = str(uuid.uuid4())
        engine_mock = _make_engine_mock(existing_run_id=existing)

        from atlas.api.internal_recompute import app
        from atlas.db import get_engine

        app.dependency_overrides[get_engine] = lambda: engine_mock
        try:
            tc = TestClient(app, raise_server_exceptions=False)
            response = tc.post("/internal/recompute/all", headers=_AUTH_HEADER)
        finally:
            app.dependency_overrides.clear()

        # Allowlist check fires first — returns 400, not 409.
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error_code"] == "invalid_milestone"
        # DB must NOT have been queried (allowlist guard is pre-DB).
        engine_mock._test_conn.execute.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Happy path → 202
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_post_happy_path_returns_202_and_spawns_subprocess(
        self, client: TestClient, tmp_path: Any
    ) -> None:
        mock_popen = MagicMock()

        with (
            patch("atlas.api.internal_recompute.LOG_DIR", tmp_path),
            patch("atlas.api.internal_recompute.subprocess.Popen", mock_popen),
        ):
            response = client.post("/internal/recompute/m3", headers=_AUTH_HEADER)

        assert response.status_code == 202
        body = response.json()

        # Envelope shape.
        assert "data" in body
        assert "meta" in body
        data = body["data"]
        assert data["milestone"] == "m3"
        assert data["status"] == "running"
        # spec: data.compute_run_id per M13_THRESHOLDS_ADMIN.md §response-envelope
        assert "compute_run_id" in data
        # compute_run_id must be a valid UUID.
        run_id = uuid.UUID(data["compute_run_id"])

        # Log file path must contain milestone and run_id.
        log_file = data["log_file"]
        assert f"recompute-m3-{run_id}" in log_file

        # subprocess.Popen must have been called exactly once.
        assert mock_popen.call_count == 1
        popen_call = mock_popen.call_args
        # argv[0] is sys.executable, argv[1] is scripts/m3_daily.py
        argv = popen_call[0][0]
        assert argv[1] == "scripts/m3_daily.py"
        # env must contain the pre-allocated run_id.
        env_passed = popen_call[1]["env"]
        assert env_passed["ATLAS_PIPELINE_RUN_ID"] == str(run_id)

    def test_post_closes_parent_logfile_handle_after_popen(self, tmp_path: Any) -> None:
        """Parent process must close its logfile fd after Popen succeeds.

        The subprocess already inherited the fd via dup2; closing the parent's
        handle avoids leaking one fd per recompute in the API server process.
        Wire pathlib.Path.open to a mock so we can assert __exit__ was called.
        """
        engine_mock = _make_engine_mock(existing_run_id=None)
        proc_mock = MagicMock()
        proc_mock.pid = 99999
        mock_popen = MagicMock(return_value=proc_mock)

        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.__exit__.return_value = None

        from atlas.api.internal_recompute import app
        from atlas.db import get_engine

        app.dependency_overrides[get_engine] = lambda: engine_mock
        try:
            with (
                patch("atlas.api.internal_recompute.LOG_DIR", tmp_path),
                patch("atlas.api.internal_recompute.subprocess.Popen", mock_popen),
                patch("pathlib.Path.open", return_value=mock_file),
            ):
                tc = TestClient(app, raise_server_exceptions=False)
                response = tc.post("/internal/recompute/m3", headers=_AUTH_HEADER)
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 202
        # The parent's with-block must have exited, calling __exit__ on the file
        # object. This verifies the fd is closed in the parent after Popen returns.
        mock_file.__exit__.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Popen raises → 500
# ---------------------------------------------------------------------------


class TestPopenFailure:
    def test_post_when_popen_raises_returns_500(self, client: TestClient, tmp_path: Any) -> None:
        with (
            patch("atlas.api.internal_recompute.LOG_DIR", tmp_path),
            patch(
                "atlas.api.internal_recompute.subprocess.Popen",
                side_effect=FileNotFoundError("python not found"),
            ),
        ):
            response = client.post("/internal/recompute/m4", headers=_AUTH_HEADER)

        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail["error_code"] == "spawn_failed"
        assert "python not found" in detail["context"]["error"]
