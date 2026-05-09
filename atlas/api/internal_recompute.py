"""M13 internal recompute API. Bearer-secret-gated, never user-facing.

Spawns scripts/m{3,4,5}_daily.py for FM-triggered threshold recomputes.
Runs on .214:8002 behind ATLAS_INTERNAL_SECRET. Public-port siblings
(atlas.api.app) are NOT the same app — keeps internal-only endpoints
isolated from anything that might leak into the public API surface.

For milestone="all": spawns m3, m4, m5 sequentially in a single shell
command joined by &&. This ensures each script must succeed before the
next starts, which matches the natural data dependency (m4 needs m3
output, m5 needs m4 output). The trade-off is that one logfile captures
all three runs; the run_id in ATLAS_PIPELINE_RUN_ID covers the aggregate.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()

app = FastAPI(title="Atlas Internal Recompute API", version="0.1.0")

# Resolved once at import time — atlas/api/internal_recompute.py → atlas-os/
ATLAS_ROOT = Path(__file__).resolve().parent.parent.parent

LOG_DIR = Path("/var/log/atlas")

_ALLOWED_MILESTONES: set[str] = {"m3", "m4", "m5", "all"}


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def verify_bearer(authorization: str = Header(default="")) -> None:
    """Raise 401 if the Authorization header doesn't match ATLAS_INTERNAL_SECRET."""
    secret = os.environ.get("ATLAS_INTERNAL_SECRET", "")
    if not secret:
        # Misconfiguration — fail safe.
        # spec: structured error envelope per CLAUDE.md API design rule
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "secret_not_configured",
                "message": "ATLAS_INTERNAL_SECRET env var is not set on the server",
                "context": {},
            },
        )
    expected = f"Bearer {secret}"
    if authorization != expected:
        # spec: structured error envelope per CLAUDE.md API design rule
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "invalid_bearer",
                "message": "missing or invalid bearer token",
                "context": {},
            },
        )


# ---------------------------------------------------------------------------
# DB session helper (mirrors atlas.api.portfolios pattern)
# ---------------------------------------------------------------------------


@contextmanager
def _db(engine: Engine) -> Generator[Any, None, None]:
    """Open a read-only DB connection.

    Concurrency check is per-milestone (running m3 does not block m4 — they
    write to different tables). For milestone='all', the check widens to
    M3+M4+M5 since "all" launches all three sequentially.
    """
    with engine.connect() as conn:
        yield conn


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@app.post("/internal/recompute/{milestone}", status_code=202)
def trigger_recompute(
    milestone: str,
    request: Request,
    engine: Engine = Depends(get_engine),  # noqa: B008
    _auth: None = Depends(verify_bearer),  # pyright: ignore[reportUnusedParameter]
) -> dict[str, Any]:
    """Spawn a pipeline recompute for the requested milestone.

    Returns 202 immediately with a run_id; the subprocess runs in the
    background with stdout/stderr redirected to a dated logfile.
    """
    source_ip = request.client.host if request.client else "unknown"

    # 1. Allowlist check.
    if milestone not in _ALLOWED_MILESTONES:
        log.warning(
            "recompute_invalid_milestone",
            milestone=milestone,
            source_ip=source_ip,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_milestone",
                "message": f"Milestone {milestone!r} is not allowed.",
                "context": {"allowed": sorted(_ALLOWED_MILESTONES)},
            },
        )

    # 2. Concurrency check — any of M3/M4/M5 running in the last 6 hours?
    milestones_to_check = ["M3", "M4", "M5"] if milestone == "all" else [milestone.upper()]
    placeholders = ", ".join(f":m{i}" for i in range(len(milestones_to_check)))
    params: dict[str, Any] = {f"m{i}": v for i, v in enumerate(milestones_to_check)}

    with _db(engine) as conn:
        row = conn.execute(
            text(
                f"""
                SELECT run_id
                FROM atlas.atlas_pipeline_runs
                WHERE milestone IN ({placeholders})
                  AND status = 'running'
                  AND started_at > NOW() - INTERVAL '6 hours'
                ORDER BY started_at DESC
                LIMIT 1
                """
            ),
            params,
        ).fetchone()

    if row is not None:
        existing_run_id = str(row[0])
        log.warning(
            "recompute_already_running",
            existing_run_id=existing_run_id,
            milestone=milestone,
            source_ip=source_ip,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "already_running",
                "message": "A pipeline run is already in progress.",
                "context": {"run_id": existing_run_id},
            },
        )

    # 3. Allocate run_id and prepare logfile.
    run_id = uuid.uuid4()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"recompute-{milestone}-{run_id}.log"

    # 4. Build subprocess command.
    if milestone == "all":
        # Sequential: m3 must succeed before m4, m4 before m5 (data dependency).
        # One shell invocation, one logfile capturing all three scripts.
        # shlex.quote protects against sys.executable paths with spaces.
        cmd: list[str] | str
        exe = shlex.quote(sys.executable)
        cmd = (
            f"{exe} scripts/m3_daily.py"
            f" && {exe} scripts/m4_daily.py"
            f" && {exe} scripts/m5_daily.py"
        )
        use_shell = True
    else:
        cmd = [sys.executable, f"scripts/{milestone}_daily.py"]
        use_shell = False

    child_env = {**os.environ, "ATLAS_PIPELINE_RUN_ID": str(run_id)}

    now_iso = datetime.now(UTC).isoformat()

    log.info(
        "recompute_spawning",
        compute_run_id=str(run_id),
        milestone=milestone,
        log_file=str(log_path),
        source_ip=source_ip,
    )

    # 5. Spawn.
    # The `with` block closes the parent's file handle once Popen returns.
    # The subprocess has already inherited the fd via dup2; the kernel's
    # per-fd reference count keeps the underlying file alive as long as the
    # child holds it open, even after the parent closes its handle.
    try:
        with log_path.open("w") as logfile:
            subprocess.Popen(  # noqa: S603
                cmd,
                stdout=logfile,
                stderr=subprocess.STDOUT,
                env=child_env,
                cwd=str(ATLAS_ROOT),
                shell=use_shell,
            )
    except (FileNotFoundError, PermissionError) as exc:
        log.error(
            "recompute_spawn_failed",
            run_id=str(run_id),
            milestone=milestone,
            source_ip=source_ip,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "spawn_failed",
                "message": "Failed to start the pipeline subprocess.",
                "context": {"error": str(exc)},
            },
        ) from exc

    # 6. Return 202 immediately.
    # spec: data.compute_run_id per M13_THRESHOLDS_ADMIN.md §response-envelope
    return {
        "data": {
            "compute_run_id": str(run_id),
            "milestone": milestone,
            "status": "running",
            "log_file": str(log_path),
        },
        "meta": {
            "data_as_of": now_iso,
            "fetched_at": now_iso,
            "source": "atlas-internal",
        },
    }
