"""Tests for atlas/intelligence/states/persistence.py — Task 1.8."""

import os
import uuid

import pandas as pd
import pytest
from sqlalchemy import text

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB)",
)


def _sample_panel_row(iid, dt, state="stage_2a"):
    return {
        "instrument_id": iid,
        "date": pd.Timestamp(dt).date(),
        "state": state,
        "prior_state": "stage_1",
        "state_since_date": pd.Timestamp(dt).date(),
        "dwell_days": 0,
        "dwell_percentile": 0.25,
        "urgency_score": "urgent",
        "within_state_rank": 0.95,
        "rs_rank_12m": 0.92,
        "close_vs_sma_50": 0.05,
        "close_vs_sma_150": 0.12,
        "close_vs_sma_200": 0.18,
        "sma_200_slope": 0.0008,
        "volume_ratio_50d": 1.8,
        "distribution_days": 0,
        "classifier_version": "v1.0-test",
    }


@_SKIP_INTEGRATION
def test_persist_state_panel_writes_rows(db_engine):
    from atlas.intelligence.states.persistence import persist_state_panel

    iid = uuid.uuid4()
    panel = pd.DataFrame([_sample_panel_row(iid, "2026-05-15")])
    try:
        n = persist_state_panel(db_engine, panel)
        assert n == 1
        with db_engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT state, dwell_days, urgency_score "
                    "FROM atlas.atlas_stock_state_daily WHERE instrument_id = :iid"
                ),
                {"iid": str(iid)},
            ).fetchall()
        assert len(rows) == 1
        assert rows[0].state == "stage_2a"
        assert rows[0].dwell_days == 0
        assert rows[0].urgency_score == "urgent"
    finally:
        with db_engine.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_stock_state_daily WHERE instrument_id = :iid"),
                {"iid": str(iid)},
            )


@_SKIP_INTEGRATION
def test_persist_state_panel_upserts_on_conflict(db_engine):
    """Re-inserting the same (instrument_id, date) updates rather than fails."""
    from atlas.intelligence.states.persistence import persist_state_panel

    iid = uuid.uuid4()
    panel1 = pd.DataFrame([_sample_panel_row(iid, "2026-05-15", state="stage_2a")])
    panel2 = pd.DataFrame([_sample_panel_row(iid, "2026-05-15", state="stage_2b")])
    try:
        persist_state_panel(db_engine, panel1)
        persist_state_panel(db_engine, panel2)
        with db_engine.connect() as c:
            rows = c.execute(
                text("SELECT state FROM atlas.atlas_stock_state_daily WHERE instrument_id = :iid"),
                {"iid": str(iid)},
            ).fetchall()
        assert len(rows) == 1
        assert rows[0].state == "stage_2b"  # second insert overwrote
    finally:
        with db_engine.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_stock_state_daily WHERE instrument_id = :iid"),
                {"iid": str(iid)},
            )


@_SKIP_INTEGRATION
def test_persist_state_panel_handles_empty_panel(db_engine):
    """Empty panel returns 0 written without error."""
    from atlas.intelligence.states.persistence import persist_state_panel

    panel = pd.DataFrame(
        columns=[
            "instrument_id",
            "date",
            "state",
            "prior_state",
            "state_since_date",
            "dwell_days",
            "urgency_score",
            "classifier_version",
        ]
    )
    n = persist_state_panel(db_engine, panel)
    assert n == 0


def test_persist_state_panel_returns_zero_for_empty_no_db():
    """Empty panel handling shouldn't require DB access."""
    from atlas.intelligence.states.persistence import persist_state_panel

    panel = pd.DataFrame(columns=["instrument_id"])
    # We pass None as engine; the function must short-circuit on empty panel
    # before any DB call. If it tries to use engine, it'll AttributeError.
    n = persist_state_panel(None, panel)  # type: ignore[arg-type]
    assert n == 0
