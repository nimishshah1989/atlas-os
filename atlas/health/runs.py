"""record_run / finish_run — pipeline run logging helpers.

Every backfill / daily script wraps its work with::

    from atlas.health.runs import record_run, finish_run

    run_id = record_run("m4_daily", milestone="M4")
    try:
        rows = do_work()
        finish_run(run_id, status="success", rows_written=rows)
    except Exception as exc:
        finish_run(run_id, status="failed", error=exc)
        raise

Writes one row per invocation to ``atlas.atlas_pipeline_runs``.
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import traceback
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()

_GIT_SHA_CACHE: str | None = None


def _git_sha() -> str | None:
    """Return short git SHA at process start. Cached for the process lifetime."""
    global _GIT_SHA_CACHE
    if _GIT_SHA_CACHE is not None:
        return _GIT_SHA_CACHE
    try:
        sha = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--short=12", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        ).stdout.strip()
        _GIT_SHA_CACHE = sha or None
    except Exception:
        _GIT_SHA_CACHE = None
    return _GIT_SHA_CACHE


def _hostname() -> str:
    """Best-effort hostname for run attribution."""
    try:
        return socket.gethostname()[:64]
    except Exception:
        return platform.node()[:64] or "unknown"


def record_run(
    script_name: str,
    *,
    milestone: str | None = None,
    phase: str | None = None,
    engine: Engine | None = None,
) -> uuid.UUID:
    """Insert a row with status=running. Returns the run_id."""
    env_run_id = os.environ.get("ATLAS_PIPELINE_RUN_ID")
    if env_run_id:
        try:
            run_id = uuid.UUID(env_run_id)
        except ValueError:
            log.warning("invalid_pipeline_run_id_env", value=env_run_id)
            run_id = uuid.uuid4()
    else:
        run_id = uuid.uuid4()
    eng = engine or get_engine()
    # Plain connect() is fine here — INSERT/UPDATE on atlas_pipeline_runs
    # are short-lived (<1 ms) and do not need statement_timeout disabled.
    # Using eng.connect() directly avoids importing atlas.compute._session,
    # which would cross a bounded-context boundary.
    with eng.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_pipeline_runs (
                    run_id, script_name, milestone, phase,
                    started_at, status, host, git_sha
                ) VALUES (
                    :run_id, :script_name, :milestone, :phase,
                    :started_at, 'running', :host, :git_sha
                )
            """),
            {
                "run_id": str(run_id),
                "script_name": script_name[:64],
                "milestone": milestone[:8] if milestone else None,
                "phase": phase[:32] if phase else None,
                "started_at": datetime.now(UTC),
                "host": _hostname(),
                "git_sha": _git_sha(),
            },
        )
        conn.commit()
    log.info("pipeline_run_started", run_id=str(run_id), script=script_name)
    return run_id


def finish_run(
    run_id: uuid.UUID,
    *,
    status: str,
    rows_written: int | None = None,
    error: Any = None,
    engine: Engine | None = None,
) -> None:
    """Update the run row with end time, status, rows, and any error."""
    if status not in {"success", "failed"}:
        raise ValueError(f"invalid status {status!r}")

    error_text: str | None = None
    if error is not None:
        if isinstance(error, BaseException):
            error_text = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
        else:
            error_text = str(error)
        # Cap at 4 KB.
        if len(error_text) > 4096:
            error_text = error_text[:4096] + "\n...(truncated)"

    eng = engine or get_engine()
    with eng.connect() as conn:
        conn.execute(
            text("""
                UPDATE atlas.atlas_pipeline_runs
                SET ended_at = :ended_at,
                    status = :status,
                    rows_written = :rows_written,
                    error_message = :error_message,
                    updated_at = :ended_at
                WHERE run_id = :run_id
            """),
            {
                "run_id": str(run_id),
                "ended_at": datetime.now(UTC),
                "status": status,
                "rows_written": rows_written,
                "error_message": error_text,
            },
        )
        conn.commit()
    log.info(
        "pipeline_run_finished",
        run_id=str(run_id),
        status=status,
        rows=rows_written,
    )


def safe_record(script_name: str, **kwargs: Any) -> uuid.UUID | None:
    """Best-effort record_run that never raises.

    Use in scripts where a DB connection issue must NOT block the pipeline
    itself from running. Returns None if recording fails.
    """
    try:
        return record_run(script_name, **kwargs)
    except Exception as exc:
        log.warning("record_run_failed", script=script_name, error=str(exc))
        return None


def safe_finish(run_id: uuid.UUID | None, **kwargs: Any) -> None:
    """Best-effort finish_run that never raises."""
    if run_id is None:
        return
    try:
        finish_run(run_id, **kwargs)
    except Exception as exc:
        log.warning("finish_run_failed", run_id=str(run_id), error=str(exc))


__all__ = ["record_run", "finish_run", "safe_record", "safe_finish"]
