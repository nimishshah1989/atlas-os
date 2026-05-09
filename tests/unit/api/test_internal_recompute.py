"""Unit tests for atlas.api.internal_recompute — mocked DB + subprocess."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import contextmanager
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


@pytest.fixture
def mock_engine() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(mock_engine: MagicMock) -> TestClient:
    """TestClient with get_engine overridden to a MagicMock."""
    from atlas.api.internal_recompute import app
    from atlas.db import get_engine

    app.dependency_overrides[get_engine] = lambda: mock_engine
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _patch_db_no_running_row() -> Callable[..., Any]:
    """open_compute_session that returns no running row (concurrency check passes)."""
    conn = MagicMock()
    execute_result = MagicMock()
    execute_result.fetchone.return_value = None
    conn.execute.return_value = execute_result

    @contextmanager
    def _cm(_engine: Any) -> Any:
        yield conn

    return _cm


def _patch_db_running_row(existing_run_id: str) -> Callable[..., Any]:
    """open_compute_session that returns a running row (concurrency check triggers 409)."""
    conn = MagicMock()
    execute_result = MagicMock()
    row = MagicMock()
    row.__getitem__ = lambda self, idx: existing_run_id if idx == 0 else None  # type: ignore[misc]
    execute_result.fetchone.return_value = row
    conn.execute.return_value = execute_result

    @contextmanager
    def _cm(_engine: Any) -> Any:
        yield conn

    return _cm


# ---------------------------------------------------------------------------
# 1. No bearer → 401
# ---------------------------------------------------------------------------


class TestAuth:
    def test_post_without_bearer_returns_401(self, client: TestClient) -> None:
        response = client.post("/internal/recompute/m3")
        assert response.status_code == 401

    def test_post_with_wrong_bearer_returns_401(self, client: TestClient) -> None:
        response = client.post(
            "/internal/recompute/m3",
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert response.status_code == 401


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
        assert sorted(allowed) == ["all", "m3", "m4", "m5"]


# ---------------------------------------------------------------------------
# 3. Concurrent run → 409
# ---------------------------------------------------------------------------


class TestConcurrencyCheck:
    def test_post_when_concurrent_run_returns_409(self, client: TestClient) -> None:
        existing = str(uuid.uuid4())
        with patch(
            "atlas.api.internal_recompute.open_compute_session",
            _patch_db_running_row(existing),
        ):
            response = client.post("/internal/recompute/m3", headers=_AUTH_HEADER)

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["error_code"] == "already_running"
        assert detail["context"]["run_id"] == existing


# ---------------------------------------------------------------------------
# 4. Happy path → 202
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_post_happy_path_returns_202_and_spawns_subprocess(
        self, client: TestClient, tmp_path: pytest.TempPathFactory
    ) -> None:
        mock_popen = MagicMock()

        with (
            patch(
                "atlas.api.internal_recompute.open_compute_session",
                _patch_db_no_running_row(),
            ),
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
        assert "run_id" in data
        # run_id must be a valid UUID.
        run_id = uuid.UUID(data["run_id"])

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


# ---------------------------------------------------------------------------
# 5. Popen raises → 500
# ---------------------------------------------------------------------------


class TestPopenFailure:
    def test_post_when_popen_raises_returns_500(
        self, client: TestClient, tmp_path: pytest.TempPathFactory
    ) -> None:
        with (
            patch(
                "atlas.api.internal_recompute.open_compute_session",
                _patch_db_no_running_row(),
            ),
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
