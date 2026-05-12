"""Persistence helpers for the validator agent.

Three functions for the run lifecycle:
- ``start_run``: INSERT a new atlas_validator_runs row, return the UUID.
- ``finish_run``: UPDATE the run row with final status + finding count.
- ``upsert_finding``: INSERT or UPDATE an atlas_validator_findings row.

Upsert semantics: (finding_class, surface, identifier) is the natural key
for deduplication. Re-detection of the same finding updates last_seen and
updated_at rather than creating a duplicate row. When the same field is wrong
on multiple frontend pages, the most recently crawled route wins — intentional:
one finding per field, not per page.

All DB access is in explicit transactions (engine.begin()) so partial writes
roll back on error.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.agents.validator.models import Finding

log = structlog.get_logger()


def start_run(engine: Engine, *, scope: str) -> uuid.UUID:
    """INSERT a new atlas_validator_runs row with status='running'.

    Args:
        engine: SQLAlchemy engine.
        scope: Validator scope tag (e.g. 'sensibility', 'frontend_diff').

    Returns:
        The UUID of the newly created run row.
    """
    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_validator_runs
                    (id, started_at, status, scope, created_at, updated_at)
                VALUES
                    (:id, :started_at, 'running', :scope, :created_at, :updated_at)
            """),
            {
                "id": str(run_id),
                "started_at": now,
                "scope": scope,
                "created_at": now,
                "updated_at": now,
            },
        )
    log.info("validator_run_started", run_id=str(run_id), scope=scope)
    return run_id


def finish_run(
    engine: Engine,
    run_id: uuid.UUID,
    *,
    status: str,
    n_findings: int,
) -> None:
    """UPDATE atlas_validator_runs with final status + finding count.

    Args:
        engine: SQLAlchemy engine.
        run_id: UUID returned by ``start_run``.
        status: Final status — 'success' or 'failed'.
        n_findings: Total number of findings detected in this run.
    """
    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE atlas.atlas_validator_runs
                SET completed_at = :completed_at,
                    status       = :status,
                    n_findings   = :n_findings,
                    updated_at   = :updated_at
                WHERE id = :id
            """),
            {
                "id": str(run_id),
                "completed_at": now,
                "status": status,
                "n_findings": n_findings,
                "updated_at": now,
            },
        )
    log.info(
        "validator_run_finished",
        run_id=str(run_id),
        status=status,
        n_findings=n_findings,
    )


def upsert_finding(
    engine: Engine,
    run_id: uuid.UUID,
    finding: Finding,
    *,
    route: str | None = None,
) -> None:
    """INSERT or UPDATE an atlas_validator_findings row.

    Deduplication key: (finding_class, surface, identifier).
    On conflict: update all volatile fields while preserving first_seen.
    Most recently seen route, severity, and delta values replace prior values.

    Args:
        engine: SQLAlchemy engine.
        run_id: UUID of the current validator run.
        finding: ``Finding`` dataclass to persist. ``finding.delta_abs`` and
                 ``finding.delta_pct`` are written to the corresponding DB columns.
        route: Frontend route where the finding was observed (e.g. '/stocks').
               NULL for Phase A+B DB-only findings which have no frontend route.
    """
    import json as _json

    now = datetime.now(UTC)
    finding_id = str(uuid.uuid4())
    delta_abs = float(finding.delta_abs) if finding.delta_abs is not None else None
    delta_pct = float(finding.delta_pct) if finding.delta_pct is not None else None

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_validator_findings (
                    id, run_id, finding_class, severity, route, surface,
                    identifier, expected_value, actual_value,
                    delta_abs, delta_pct,
                    evidence, remediation,
                    first_seen, last_seen,
                    created_at, updated_at
                ) VALUES (
                    :id, :run_id, :finding_class, :severity, :route, :surface,
                    :identifier, :expected_value, :actual_value,
                    :delta_abs, :delta_pct,
                    CAST(:evidence AS jsonb), :remediation,
                    :first_seen, :last_seen,
                    :created_at, :updated_at
                )
                ON CONFLICT (finding_class, surface, identifier)
                DO UPDATE SET
                    last_seen       = EXCLUDED.last_seen,
                    updated_at      = EXCLUDED.updated_at,
                    run_id          = EXCLUDED.run_id,
                    route           = EXCLUDED.route,
                    severity        = EXCLUDED.severity,
                    expected_value  = EXCLUDED.expected_value,
                    actual_value    = EXCLUDED.actual_value,
                    delta_abs       = EXCLUDED.delta_abs,
                    delta_pct       = EXCLUDED.delta_pct,
                    evidence        = EXCLUDED.evidence
            """),
            {
                "id": finding_id,
                "run_id": str(run_id),
                "finding_class": finding.finding_class,
                "severity": finding.severity,
                "route": route,
                "surface": finding.surface,
                "identifier": finding.identifier,
                "expected_value": finding.expected_value,
                "actual_value": finding.actual_value,
                "delta_abs": delta_abs,
                "delta_pct": delta_pct,
                "evidence": _json.dumps(finding.evidence),
                "remediation": finding.remediation,
                "first_seen": now,
                "last_seen": now,
                "created_at": now,
                "updated_at": now,
            },
        )
    log.debug(
        "finding_upserted",
        surface=finding.surface,
        severity=finding.severity,
        identifier=finding.identifier,
        route=route,
    )
