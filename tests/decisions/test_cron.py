"""Tests for ``atlas.decisions.cron`` — daily inference orchestrator.

Tests focus on the contract layer above DB I/O:

* Trigger-only cadence (a hit on an already-open (iid, cell, tenure) skips
  the write — no new signal_call_id).
* In-run idempotency (two hits on the same triple from one cron pass
  produce exactly one row).
* Re-entry after exit (the prior open row is closed → the new hit DOES
  mint a new signal_call_id).
* Deprecated cells filtered out at read.
* Drift-warn cells still fire (advisory mode per CONTEXT.md).
* ``write=False`` skips DB writes but populates counts.

DB I/O is mocked at the four loader functions
(``_load_scorecard`` / ``_load_regime`` / ``_load_active_cells`` /
``_load_open_positions`` / ``_load_prior_calls``) plus ``bulk_upsert``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine

from atlas.decisions.cron import (
    SIGNAL_CALL_COLUMNS,
    SignalCallsWriteResult,
    compute_daily_signal_calls,
)
from atlas.regime.classifier import RegimeState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _scorecard_row(
    instrument_id: str = "11111111-1111-1111-1111-111111111111",
    **features: Any,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "instrument_id": instrument_id,
        "scorecard_id": str(uuid4()),
        "cap_tier": "Mid",
        "family_trend": "G",
        "family_volatility": "A",
        "family_volume": "A",
        "family_path": "A",
        "family_sector": "G",
        "rs_residual_6m": Decimal("0.10"),
        "log_med_tv_60d": Decimal("16.0"),
        "realized_vol_60d": Decimal("0.25"),
        "formation_max_dd": Decimal("0.15"),
        "listing_age_days": 1200,
        "log_price": Decimal("6.5"),
    }
    defaults.update(features)
    return defaults


def _cell(
    *,
    cell_id: UUID | None = None,
    rule_type: str = "pullback",
    tier: str = "Mid",
    action: str = "POSITIVE",
    tenure: str = "6m",
    eligibility: list[dict[str, Any]] | None = None,
    entry: list[dict[str, Any]] | None = None,
    confidence_unconditional: Decimal | None = None,
    confidence_by_regime: dict[str, Decimal] | None = None,
    drift_status: str = "healthy",
) -> dict[str, Any]:
    rule_dsl = {
        "rule_type": rule_type,
        "eligibility": eligibility or [],
        "entry": entry or [],
        "tier": tier,
        "action": action,
        "tenure": tenure,
        "methodology_lock_ref": "TEST_LOCK_2026-05-24",
    }
    return {
        "cell_id": cell_id or uuid4(),
        "cap_tier": tier,
        "action": action,
        "tenure": tenure,
        "rule_dsl": rule_dsl,
        "confidence_unconditional": confidence_unconditional,
        "confidence_by_regime": confidence_by_regime,
        "stable_features": None,
        "methodology_lock_ref": "TEST_LOCK_2026-05-24",
        "rule_version": 1,
        "drift_status": drift_status,
    }


def _patch_cron(
    *,
    scorecard_rows: list[dict[str, Any]],
    regime: RegimeState | None,
    cells: list[dict[str, Any]],
    open_triples: set[tuple[str, str, str]] | None = None,
    prior_triples: set[tuple[str, str, str]] | None = None,
    bulk_upsert_calls: list[dict[str, Any]] | None = None,
):
    """Build the patcher list for compute_daily_signal_calls.

    Patches every DB I/O function in atlas.decisions.cron at the module
    level, plus bulk_upsert. Returns a list of patchers — caller starts
    + stops them.
    """
    open_triples = open_triples or set()
    prior_triples = prior_triples or set()

    def _fake_load_scorecard(_engine, _td):  # type: ignore[no-untyped-def]
        return scorecard_rows

    def _fake_load_regime(_engine, _td):  # type: ignore[no-untyped-def]
        return regime

    def _fake_load_cells(_engine):  # type: ignore[no-untyped-def]
        return cells

    def _fake_load_open(_engine, _td):  # type: ignore[no-untyped-def]
        return set(open_triples)

    def _fake_load_prior(_engine, _td):  # type: ignore[no-untyped-def]
        return set(prior_triples)

    def _fake_bulk_upsert(_engine, *, table, columns, rows, pk_columns, **_kw):  # type: ignore[no-untyped-def]
        if bulk_upsert_calls is not None:
            bulk_upsert_calls.append(
                {
                    "table": table,
                    "columns": list(columns),
                    "rows": list(rows),
                    "pk_columns": list(pk_columns),
                }
            )
        return len(rows)

    return [
        patch("atlas.decisions.cron._load_scorecard", side_effect=_fake_load_scorecard),
        patch("atlas.decisions.cron._load_regime", side_effect=_fake_load_regime),
        patch("atlas.decisions.cron._load_active_cells", side_effect=_fake_load_cells),
        patch("atlas.decisions.cron._load_open_positions", side_effect=_fake_load_open),
        patch("atlas.decisions.cron._load_prior_calls", side_effect=_fake_load_prior),
        patch("atlas.decisions.cron.bulk_upsert", side_effect=_fake_bulk_upsert),
    ]


def _enter_all(patchers):  # type: ignore[no-untyped-def]
    for p in patchers:
        p.start()


def _exit_all(patchers):  # type: ignore[no-untyped-def]
    for p in reversed(patchers):
        p.stop()


def _run_cron(
    *,
    target_date: date,
    scorecard_rows: list[dict[str, Any]],
    regime: RegimeState | None,
    cells: list[dict[str, Any]],
    open_triples: set[tuple[str, str, str]] | None = None,
    prior_triples: set[tuple[str, str, str]] | None = None,
    write: bool = True,
) -> tuple[SignalCallsWriteResult, list[dict[str, Any]]]:
    """Run the cron with mocked I/O. Returns (result, captured bulk_upsert calls)."""
    calls: list[dict[str, Any]] = []
    patchers = _patch_cron(
        scorecard_rows=scorecard_rows,
        regime=regime,
        cells=cells,
        open_triples=open_triples,
        prior_triples=prior_triples,
        bulk_upsert_calls=calls,
    )
    _enter_all(patchers)
    try:
        result = compute_daily_signal_calls(
            target_date=target_date,
            db_engine=cast(Engine, MagicMock()),
            write=write,
        )
    finally:
        _exit_all(patchers)
    return result, calls


# ---------------------------------------------------------------------------
# Happy path — single new signal
# ---------------------------------------------------------------------------


def test_cron_writes_new_signal_on_fresh_hit() -> None:
    """A hit with no existing open position mints a new signal_call_id."""
    td = date(2026, 5, 22)
    iid = "11111111-1111-1111-1111-111111111111"
    row = _scorecard_row(instrument_id=iid)
    cell = _cell(
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
    )

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell],
    )

    assert result.new_signals == 1
    assert result.hits_total == 1
    assert result.reactivations == 0
    assert result.skipped_open == 0
    assert result.errors == 0
    assert result.regime_state is RegimeState.RISK_ON
    assert result.universe_size == 1
    assert result.cells_evaluated == 1
    assert len(calls) == 1
    assert calls[0]["table"] == "atlas.atlas_signal_calls"
    assert list(calls[0]["columns"]) == list(SIGNAL_CALL_COLUMNS)
    assert calls[0]["pk_columns"] == ["signal_call_id"]
    assert len(calls[0]["rows"]) == 1
    row_tuple = calls[0]["rows"][0]
    # (signal_call_id, instrument_id, scorecard_id, date, cell_id,
    #  cap_tier_at_trigger, tenure, action, conf_uncond, conf_regime,
    #  regime_state_at_call, cell_active_in_regime)
    assert isinstance(row_tuple[0], UUID)
    assert row_tuple[3] == td
    assert row_tuple[5] == "Mid"
    assert row_tuple[6] == "6m"
    assert row_tuple[7] == "POSITIVE"
    assert row_tuple[10] == "Risk-On"


# ---------------------------------------------------------------------------
# Trigger-only cadence — day-2 active does not re-write
# ---------------------------------------------------------------------------


def test_cron_skips_write_when_open_position_exists() -> None:
    """Day-2 evaluation of an already-open call MUST NOT write a new row."""
    td = date(2026, 5, 22)
    iid = "22222222-2222-2222-2222-222222222222"
    cell_uuid = uuid4()
    row = _scorecard_row(instrument_id=iid)
    cell = _cell(
        cell_id=cell_uuid,
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
    )
    # The (iid, cell, tenure) triple is already open from yesterday.
    open_set = {(iid, str(cell_uuid), "6m")}

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell],
        open_triples=open_set,
    )

    assert result.hits_total == 1  # The cell hit
    assert result.new_signals == 0  # but no new row written
    assert result.skipped_open == 1
    # bulk_upsert NOT called because rows_to_write is empty.
    assert calls == []


def test_cron_reactivation_after_exit_mints_new_signal_id() -> None:
    """Re-entry after exit: triple in prior_calls, NOT in open_triples → new row."""
    td = date(2026, 5, 22)
    iid = "33333333-3333-3333-3333-333333333333"
    cell_uuid = uuid4()
    row = _scorecard_row(instrument_id=iid)
    cell = _cell(
        cell_id=cell_uuid,
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
    )
    # Triple has triggered before (was open, then closed) — now re-fires.
    open_set: set[tuple[str, str, str]] = set()
    prior_set = {(iid, str(cell_uuid), "6m")}

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell],
        open_triples=open_set,
        prior_triples=prior_set,
    )

    assert result.new_signals == 1
    assert result.reactivations == 1
    assert result.skipped_open == 0
    assert len(calls) == 1
    assert len(calls[0]["rows"]) == 1


def test_cron_in_run_idempotent_dedupe_same_triple() -> None:
    """Same (iid, cell, tenure) cannot fire twice within one cron pass.

    Constructed by having two cells with the same cell_id (impossible in
    the DB due to PK, but the dedup logic must still drop the second).
    """
    td = date(2026, 5, 22)
    iid = "44444444-4444-4444-4444-444444444444"
    cell_uuid = uuid4()
    row = _scorecard_row(instrument_id=iid)
    # Two cells with identical (cell_id, tenure) — second is the dup
    cell_a = _cell(
        cell_id=cell_uuid,
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
    )
    cell_b = _cell(
        cell_id=cell_uuid,
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
    )

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell_a, cell_b],
    )

    # Both cells hit, but only one row written (in-run dedup).
    assert result.hits_total == 2
    assert result.new_signals == 1
    assert len(calls) == 1
    assert len(calls[0]["rows"]) == 1


# ---------------------------------------------------------------------------
# Filtering at read — deprecated cells excluded upstream
# ---------------------------------------------------------------------------


def test_cron_drift_warn_cells_still_fire() -> None:
    """Drift-warn is advisory in v6 — drift_warn cells still produce rows."""
    td = date(2026, 5, 22)
    iid = "55555555-5555-5555-5555-555555555555"
    row = _scorecard_row(instrument_id=iid)
    cell = _cell(
        drift_status="drift_warn",
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
    )

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell],
    )

    assert result.new_signals == 1
    assert len(calls) == 1


def test_cron_deprecated_cells_excluded_at_loader_level() -> None:
    """Deprecated cells are filtered out at the SQL ``WHERE deprecated_at IS NULL``.

    The mock here returns ZERO cells (the loader is responsible for the
    filter); cron must surface an empty-cells warning + zero writes.
    """
    td = date(2026, 5, 22)
    row = _scorecard_row()

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[],
    )

    assert result.cells_evaluated == 0
    assert result.new_signals == 0
    assert calls == []


# ---------------------------------------------------------------------------
# Missing-input guards
# ---------------------------------------------------------------------------


def test_cron_no_regime_for_date_returns_error_no_writes() -> None:
    """Missing regime row → error counted, no writes attempted."""
    td = date(2026, 5, 22)
    row = _scorecard_row()
    cell = _cell()

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=None,  # regime row absent
        cells=[cell],
    )

    assert result.errors == 1
    assert result.new_signals == 0
    assert result.regime_state is None
    assert calls == []


def test_cron_empty_scorecard_short_circuits() -> None:
    td = date(2026, 5, 22)
    cell = _cell()

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[],
        regime=RegimeState.RISK_ON,
        cells=[cell],
    )

    assert result.universe_size == 0
    assert result.new_signals == 0
    assert calls == []


def test_cron_no_hits_no_writes() -> None:
    """When no cell hits, no rows are written."""
    td = date(2026, 5, 22)
    row = _scorecard_row(rs_residual_6m=Decimal("-0.20"))  # well below entry
    cell = _cell(
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
    )

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell],
    )

    assert result.hits_total == 0
    assert result.new_signals == 0
    assert calls == []


# ---------------------------------------------------------------------------
# write=False
# ---------------------------------------------------------------------------


def test_cron_write_false_skips_bulk_upsert() -> None:
    """write=False → counts populated but no DB write call."""
    td = date(2026, 5, 22)
    row = _scorecard_row()
    cell = _cell(
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
    )

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell],
        write=False,
    )

    assert result.new_signals == 1
    assert result.hits_total == 1
    assert calls == []


# ---------------------------------------------------------------------------
# Regime gating surfaced on row
# ---------------------------------------------------------------------------


def test_cron_cell_active_in_regime_written_to_row() -> None:
    """Row tuple captures cell_active_in_regime + regime_state_at_call."""
    td = date(2026, 5, 22)
    row = _scorecard_row()
    # Confidence < 0.55 in Risk-On → cell_active_in_regime=False
    cell = _cell(
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
        confidence_by_regime={"Risk-On": Decimal("0.40")},
    )

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell],
    )

    assert result.new_signals == 1
    row_tuple = calls[0]["rows"][0]
    # cell_active_in_regime at index 11; regime_state_at_call at index 10
    assert row_tuple[10] == "Risk-On"
    assert row_tuple[11] is False


def test_cron_confidence_unconditional_defaults_to_zero_when_unknown() -> None:
    """Placeholder cells without walk-forward confidence → 0.0000 default."""
    td = date(2026, 5, 22)
    row = _scorecard_row()
    cell = _cell(  # confidence_unconditional left None
        entry=[],
    )

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell],
    )

    assert result.new_signals == 1
    row_tuple = calls[0]["rows"][0]
    # confidence_unconditional at index 8 — defaults to Decimal("0.0000").
    assert row_tuple[8] == Decimal("0.0000")


# ---------------------------------------------------------------------------
# Malformed rule_dsl handling
# ---------------------------------------------------------------------------


def test_cron_invalid_cell_rule_dsl_logged_as_error_not_halting() -> None:
    """A cell with a malformed rule_dsl is counted as error and skipped."""
    td = date(2026, 5, 22)
    row = _scorecard_row()
    bad_cell = {
        "cell_id": uuid4(),
        "cap_tier": "Mid",
        "action": "POSITIVE",
        "tenure": "6m",
        "rule_dsl": {
            "rule_type": "invalid_archetype",  # not in the Literal allowlist
            "tier": "Mid",
            "action": "POSITIVE",
            "tenure": "6m",
            "methodology_lock_ref": "BAD",
        },
        "confidence_unconditional": Decimal("0.50"),
        "confidence_by_regime": None,
    }
    good_cell = _cell(
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
    )

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[bad_cell, good_cell],
    )

    assert result.errors >= 1
    assert result.new_signals == 1
    assert len(calls) == 1
    assert len(calls[0]["rows"]) == 1


# ---------------------------------------------------------------------------
# Multiple instruments + multiple cells
# ---------------------------------------------------------------------------


def test_cron_multiple_instruments_multiple_cells_cross_product() -> None:
    td = date(2026, 5, 22)
    iids = [
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "cccccccc-cccc-cccc-cccc-cccccccccccc",
    ]
    rows = [
        _scorecard_row(instrument_id=iids[0], rs_residual_6m=Decimal("0.20")),
        # exactly at threshold — `>` is strict so this row does NOT hit pullback
        _scorecard_row(instrument_id=iids[1], rs_residual_6m=Decimal("0.05")),
        _scorecard_row(instrument_id=iids[2], rs_residual_6m=Decimal("-0.10")),
    ]
    pullback_cell = _cell(
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        action="POSITIVE",
        confidence_unconditional=Decimal("0.62"),
    )
    severely_broken_cell = _cell(
        rule_type="severely_broken",
        entry=[{"feature": "rs_residual_6m", "cmp": "<", "value": Decimal("-0.05")}],
        action="NEGATIVE",
        confidence_unconditional=Decimal("0.70"),
    )

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=rows,
        regime=RegimeState.RISK_ON,
        cells=[pullback_cell, severely_broken_cell],
    )

    # iids[0] hits pullback (0.20>0.05); iids[1] does not (0.05 not >0.05);
    # iids[2] hits severely_broken (-0.10 < -0.05). 2 hits total.
    assert result.hits_total == 2
    assert result.new_signals == 2
    assert len(calls) == 1
    assert len(calls[0]["rows"]) == 2


# ---------------------------------------------------------------------------
# Signal columns contract — guard against accidental reordering
# ---------------------------------------------------------------------------


def test_signal_call_columns_match_migration_080_schema() -> None:
    """SIGNAL_CALL_COLUMNS must align with the columns the cron writes.

    Guards against drift between the cron's row-building code and the
    table definition. The 12 columns here are the insert set; other
    columns (id, computed_at, exit_*, predicted_excess, stable_features)
    are either server-defaulted or filled by atlas/ledger/ on exit.
    """
    expected = (
        "signal_call_id",
        "instrument_id",
        "scorecard_id",
        "date",
        "cell_id",
        "cap_tier_at_trigger",
        "tenure",
        "action",
        "confidence_unconditional",
        "confidence_regime_conditional",
        "regime_state_at_call",
        "cell_active_in_regime",
    )
    assert SIGNAL_CALL_COLUMNS == expected


# ---------------------------------------------------------------------------
# Smoke — result dataclass fields populated
# ---------------------------------------------------------------------------


def test_cron_result_carries_runtime_and_run_id() -> None:
    td = date(2026, 5, 22)
    row = _scorecard_row()
    cell = _cell(
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
    )

    result, _calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell],
    )

    assert result.runtime_seconds >= 0
    assert result.run_id is not None
    UUID(result.run_id)  # well-formed
    assert result.target_date == td


# ---------------------------------------------------------------------------
# Open-position check is keyed on (iid, cell, tenure) — different tenures distinct
# ---------------------------------------------------------------------------


def test_cron_different_tenures_for_same_iid_cell_independent() -> None:
    """Same (iid, cell) but different tenures get distinct signal_call_ids.

    Models the case where Mid Pullback at 6m is open but Mid Pullback at
    12m fires today for the first time.
    """
    td = date(2026, 5, 22)
    iid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    row = _scorecard_row(instrument_id=iid)

    cell_6m_id = uuid4()
    cell_12m_id = uuid4()
    cell_6m = _cell(
        cell_id=cell_6m_id,
        tenure="6m",
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.60"),
    )
    cell_12m = _cell(
        cell_id=cell_12m_id,
        tenure="12m",
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_unconditional=Decimal("0.58"),
    )
    # 6m is already open. 12m is fresh.
    open_set = {(iid, str(cell_6m_id), "6m")}

    result, calls = _run_cron(
        target_date=td,
        scorecard_rows=[row],
        regime=RegimeState.RISK_ON,
        cells=[cell_6m, cell_12m],
        open_triples=open_set,
    )

    assert result.hits_total == 2
    assert result.skipped_open == 1
    assert result.new_signals == 1  # only the 12m mints a row
    assert len(calls) == 1
    assert len(calls[0]["rows"]) == 1
    written = calls[0]["rows"][0]
    # tenure is at index 6 per SIGNAL_CALL_COLUMNS
    assert written[6] == "12m"
