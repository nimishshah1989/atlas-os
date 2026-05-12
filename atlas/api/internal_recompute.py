"""M13 internal recompute API. Bearer-secret-gated, never user-facing.

Spawns scripts/m{3,4,5}_daily.py for FM-triggered threshold recomputes.
Runs on .214:8002 behind ATLAS_INTERNAL_SECRET. Public-port siblings
(atlas.api.app) are NOT the same app — keeps internal-only endpoints
isolated from anything that might leak into the public API surface.

Milestone 'all' is NOT supported in v0 — see M13 PRD failure modes.
The shared ATLAS_PIPELINE_RUN_ID env across an m3 && m4 && m5 shell chain
causes PK collision in atlas_pipeline_runs (m3 inserts; m4/m5 collide on
safe_record's silent failure path → no audit row → SEBI gap). v0.1 will
return a batch_id and spawn three independent processes with separate UUIDs.
"""

from __future__ import annotations

import os
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

from atlas.api.admin.proposals import router as admin_proposals_router
from atlas.api.admin.weight_performance import router as admin_perf_router
from atlas.api.agents import router as agents_router
from atlas.db import get_engine

log = structlog.get_logger()

app = FastAPI(title="Atlas Internal API", version="0.2.0")

# SP04 Stage 4a — admin proposal endpoints. SP04 Stage 4c — weight
# performance + revert log. SP07 — specialist agents (chat UI backend).
# All three routers gate themselves via the _require_admin dependency
# (JWT role=admin OR ATLAS_INTERNAL_SECRET bearer), so no extra
# middleware is needed.
app.include_router(admin_proposals_router)
app.include_router(admin_perf_router)
app.include_router(agents_router)

# Resolved once at import time — atlas/api/internal_recompute.py → atlas-os/
ATLAS_ROOT = Path(__file__).resolve().parent.parent.parent

LOG_DIR = Path("/var/log/atlas")

_ALLOWED_MILESTONES: set[str] = {"m3", "m4", "m5"}  # "all" deferred — see M13 PRD failure modes


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
    """Open a read-only DB connection for the concurrency check."""
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

    # 2. Concurrency check — is this milestone running in the last 6 hours?
    milestones_to_check = [milestone.upper()]
    placeholders = ", ".join(f":m{i}" for i in range(len(milestones_to_check)))
    params: dict[str, Any] = {f"m{i}": v for i, v in enumerate(milestones_to_check)}

    # placeholders is built from a closed-set milestone whitelist (see
    # _ALLOWED_MILESTONES above), so the f-string is injection-safe.
    sql_text = f"""
        SELECT run_id
        FROM atlas.atlas_pipeline_runs
        WHERE milestone IN ({placeholders})
          AND status IN ('queued', 'running')
          AND started_at > NOW() - INTERVAL '6 hours'
        ORDER BY started_at DESC
        LIMIT 1
    """  # noqa: S608
    with _db(engine) as conn:
        row = conn.execute(text(sql_text), params).fetchone()

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

    # 4. Insert a queued row BEFORE spawning so the concurrency guard above
    #    catches a second concurrent request that races past the SELECT above.
    #    The subprocess's safe_record() call will UPDATE this row to 'running'.
    now_utc = datetime.now(UTC)
    now_iso = now_utc.isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_pipeline_runs
                    (run_id, script_name, milestone, started_at, status)
                VALUES (:rid, :script, :ms, :started, 'queued')
            """),
            {
                "rid": str(run_id),
                "script": f"{milestone}_daily.py",
                "ms": milestone.upper(),
                "started": now_utc,
            },
        )

    # 5. Build subprocess command.
    cmd = [sys.executable, f"scripts/{milestone}_daily.py"]

    child_env = {**os.environ, "ATLAS_PIPELINE_RUN_ID": str(run_id)}

    log.info(
        "recompute_spawning",
        compute_run_id=str(run_id),
        milestone=milestone,
        log_file=str(log_path),
        source_ip=source_ip,
    )

    # 6. Spawn.
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
                shell=False,
            )
    except (FileNotFoundError, PermissionError) as exc:
        log.error(
            "recompute_spawn_failed",
            run_id=str(run_id),
            milestone=milestone,
            source_ip=source_ip,
            error=str(exc),
        )
        # Roll back the queued row so the concurrency guard doesn't block
        # a subsequent retry after the spawn failure is resolved.
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM atlas.atlas_pipeline_runs WHERE run_id = :rid"),
                {"rid": str(run_id)},
            )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "spawn_failed",
                "message": "Failed to start the pipeline subprocess.",
                "context": {"error": str(exc)},
            },
        ) from exc

    # 7. Return 202 immediately.
    # spec: data.compute_run_id per M13_THRESHOLDS_ADMIN.md §response-envelope
    return {
        "data": {
            "compute_run_id": str(run_id),
            "milestone": milestone,
            "status": "queued",
            "log_file": str(log_path),
        },
        "meta": {
            "data_as_of": now_iso,
            "fetched_at": now_iso,
            "source": "atlas-internal",
        },
    }


# ---------------------------------------------------------------------------
# M15 — wire portfolios + strategies + rule-based routers behind the same
# bearer auth. The frontend already calls port 8002 with ATLAS_INTERNAL_SECRET.
# ---------------------------------------------------------------------------

from atlas.api.portfolios import router as _portfolios_router  # noqa: E402
from atlas.api.portfolios import rule_based_router as _rule_based_router  # noqa: E402
from atlas.api.strategies import router as _strategies_router  # noqa: E402

app.include_router(_portfolios_router, dependencies=[Depends(verify_bearer)])
app.include_router(_rule_based_router, dependencies=[Depends(verify_bearer)])
app.include_router(_strategies_router, dependencies=[Depends(verify_bearer)])
