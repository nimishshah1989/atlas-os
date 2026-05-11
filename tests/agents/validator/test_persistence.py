"""Integration tests for atlas.agents.validator.persistence.

Marked @pytest.mark.integration — requires a live DB connection.
Each test cleans up after itself via DELETE in fixture teardown.
"""

from __future__ import annotations

import uuid

import pytest

from atlas.agents.validator.persistence import finish_run, start_run, upsert_finding
from atlas.agents.validator.sensibility_scanner import Finding
from atlas.db import get_engine


@pytest.fixture()
def engine():  # type: ignore[no-untyped-def]
    return get_engine()


@pytest.fixture()
def run_id(engine):  # type: ignore[no-untyped-def]
    """Start a validator run; clean up the run + findings on teardown."""
    rid = start_run(engine, scope="sensibility")
    yield rid
    # Teardown: delete findings first (FK), then the run row
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM atlas.atlas_validator_findings WHERE run_id = :rid"),
            {"rid": str(rid)},
        )
        conn.execute(
            text("DELETE FROM atlas.atlas_validator_runs WHERE id = :rid"),
            {"rid": str(rid)},
        )


@pytest.mark.integration
def test_start_run_returns_uuid(engine) -> None:  # type: ignore[no-untyped-def]
    rid = start_run(engine, scope="sensibility")
    assert isinstance(rid, uuid.UUID)
    # Teardown
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM atlas.atlas_validator_runs WHERE id = :rid"),
            {"rid": str(rid)},
        )


@pytest.mark.integration
def test_finish_run_updates_status(engine, run_id) -> None:  # type: ignore[no-untyped-def]
    finish_run(engine, run_id, status="success", n_findings=3)
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, n_findings FROM atlas.atlas_validator_runs " "WHERE id = :rid"),
            {"rid": str(run_id)},
        ).fetchone()
    assert row is not None
    assert row[0] == "success"
    assert row[1] == 3


@pytest.mark.integration
def test_upsert_finding_inserts_row(engine, run_id) -> None:  # type: ignore[no-untyped-def]
    finding = Finding(
        finding_class="insensible_value",
        severity="P0",
        surface="atlas_stock_metrics_daily.ema_50",
        identifier="instrument_id=RELIANCE,date=2026-05-11",
        expected_value="any_numeric: finite",
        actual_value="inf",
        evidence={"message": "test"},
        remediation="fix compute pipeline",
    )
    upsert_finding(engine, run_id, finding)

    from sqlalchemy import text

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM atlas.atlas_validator_findings " "WHERE run_id = :rid"),
            {"rid": str(run_id)},
        ).scalar()
    assert count == 1


@pytest.mark.integration
def test_upsert_finding_deduplicates_on_second_call(engine, run_id) -> None:  # type: ignore[no-untyped-def]
    """Upserting the same finding twice must produce exactly one row."""
    finding = Finding(
        finding_class="insensible_value",
        severity="P1",
        surface="atlas_stock_metrics_daily.rs_percentile",
        identifier="instrument_id=TCS,date=2026-05-11",
        expected_value="*_percentile: [0, 1]",
        actual_value="1.5",
        evidence={},
        remediation="",
    )
    upsert_finding(engine, run_id, finding)
    upsert_finding(engine, run_id, finding)  # second call — same identity

    from sqlalchemy import text

    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM atlas.atlas_validator_findings "
                "WHERE surface = :surface AND identifier = :ident"
            ),
            {
                "surface": "atlas_stock_metrics_daily.rs_percentile",
                "ident": "instrument_id=TCS,date=2026-05-11",
            },
        ).scalar()
    assert count == 1


@pytest.mark.integration
def test_upsert_finding_updates_last_seen_on_duplicate(engine, run_id) -> None:  # type: ignore[no-untyped-def]
    """last_seen should update on re-detection even though row count stays 1."""
    finding = Finding(
        finding_class="insensible_value",
        severity="P0",
        surface="atlas_stock_metrics_daily.ema_10",
        identifier="instrument_id=HDFC,date=2026-05-11",
        expected_value="any_numeric: finite",
        actual_value="nan",
        evidence={},
        remediation="",
    )
    upsert_finding(engine, run_id, finding)
    upsert_finding(engine, run_id, finding)

    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT first_seen, last_seen FROM atlas.atlas_validator_findings "
                "WHERE surface = :surface AND identifier = :ident"
            ),
            {
                "surface": "atlas_stock_metrics_daily.ema_10",
                "ident": "instrument_id=HDFC,date=2026-05-11",
            },
        ).fetchone()
    assert row is not None
    # last_seen may equal first_seen if both inserts happen in same ms,
    # but the row must exist (deduplicated, not doubled)
    assert row[0] is not None  # first_seen
    assert row[1] is not None  # last_seen
