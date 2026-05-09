"""Unit tests for ATLAS_PIPELINE_RUN_ID env-var injection in record_run.

Tests that:
- A valid UUID env var causes record_run to use that UUID.
- A garbage env var falls back to uuid4() and logs a warning.
- Absent env var produces a fresh uuid4() as before.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_engine() -> MagicMock:
    """Return a mock Engine whose connect() yields a no-op conn context manager."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda self: self
    mock_conn.__exit__ = MagicMock(return_value=False)
    engine = MagicMock()
    engine.connect.return_value = mock_conn
    return engine


class TestRecordRunEnvInjection:
    def test_valid_env_run_id_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ATLAS_PIPELINE_RUN_ID=<valid uuid> → record_run returns that uuid."""
        expected = uuid.uuid4()
        monkeypatch.setenv("ATLAS_PIPELINE_RUN_ID", str(expected))
        mock_engine = _make_mock_engine()

        from atlas.health.runs import record_run

        result = record_run("test_script", milestone="M3", engine=mock_engine)

        assert result == expected

    def test_garbage_env_run_id_falls_back_to_random(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ATLAS_PIPELINE_RUN_ID=garbage → falls back to uuid4() and logs warning."""
        monkeypatch.setenv("ATLAS_PIPELINE_RUN_ID", "not-a-uuid")
        mock_engine = _make_mock_engine()

        with patch("atlas.health.runs.log") as mock_log:
            from atlas.health.runs import record_run

            result = record_run("test_script", milestone="M3", engine=mock_engine)

        # Should still return a valid UUID (not the garbage string).
        assert isinstance(result, uuid.UUID)
        # Should have logged a warning about the bad value.
        mock_log.warning.assert_called_once()
        call_kwargs = mock_log.warning.call_args
        assert "invalid_pipeline_run_id_env" in call_kwargs[0]

    def test_absent_env_var_produces_fresh_uuid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No ATLAS_PIPELINE_RUN_ID → uuid4() as before (no warning logged)."""
        monkeypatch.delenv("ATLAS_PIPELINE_RUN_ID", raising=False)
        mock_engine = _make_mock_engine()

        with patch("atlas.health.runs.log") as mock_log:
            from atlas.health.runs import record_run

            result = record_run("test_script", engine=mock_engine)

        assert isinstance(result, uuid.UUID)
        mock_log.warning.assert_not_called()
