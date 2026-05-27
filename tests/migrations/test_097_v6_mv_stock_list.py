"""Regression tests for migration 097 — mv_stock_list_v6.

Materialized view created:
- atlas.mv_stock_list_v6 — one row per active M1 instrument with the 15+
  load-bearing columns for the v6 Stocks page list (action, conviction tape,
  confidence band, composite, cross-cell depth, returns, RS, vol, last-fire).

Composite + confidence band are LIFTED from atlas_stock_conviction_daily
(mig 039), not re-computed. See
docs/superpowers/specs/2026-05-26-v6-stocks-mvs-design.md for the full lift
mapping.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify upgrade() emits the CREATE MATERIALIZED VIEW + the
unique index that enables CONCURRENT refresh, and downgrade() drops both in
the correct order.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the migration applies cleanly against a real Postgres + that the MV
populates with expected shape after REFRESH. Skipped by default; run on EC2.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.097_v6_mv_stock_list"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="live-DB tests — set ATLAS_INTEGRATION_TESTS=1 to run (EC2 only)",
)


def _load() -> types.ModuleType:
    return importlib.import_module(_MODULE)


def _run_upgrade_with_mock() -> MagicMock:
    mod = _load()
    with patch.object(mod, "op") as mock_op:
        mock_op.get_bind.return_value = MagicMock()
        mod.upgrade()
    return mock_op


def _run_downgrade_with_mock() -> MagicMock:
    mod = _load()
    with patch.object(mod, "op") as mock_op:
        mock_op.get_bind.return_value = MagicMock()
        mod.downgrade()
    return mock_op


def _executed_statements(mock_op: MagicMock) -> list[str]:
    statements: list[str] = []
    for call in mock_op.execute.call_args_list:
        if not call.args:
            continue
        arg = call.args[0]
        statements.append(str(getattr(arg, "text", arg)))
    return statements


# --- revision metadata --------------------------------------------------


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "097"
    assert mod.down_revision == "096"
    assert mod.branch_labels is None


# --- upgrade ------------------------------------------------------------


def test_upgrade_creates_materialized_view() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE MATERIALIZED VIEW" in joined
    assert "MV_STOCK_LIST_V6" in joined
    assert "WITH NO DATA" in joined, "MV should be created WITH NO DATA — refresh is explicit"


def test_upgrade_emits_all_required_columns() -> None:
    """Every column the Stocks page list depends on must be in the SELECT."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()

    required_columns = [
        "instrument_id",
        "symbol",
        "company_name",
        "sector",
        "cap_tier",
        "action",
        "composite_score",
        "confidence_band",
        "cross_cell_depth",
        "tape_1m",
        "tape_3m",
        "tape_6m",
        "tape_12m",
        "ret_1m",
        "ret_3m",
        "ret_12m",
        "rs_3m_nifty500",
        "vol_60d",
        "predicted_excess",
        "cell_ic",
        "last_fire_date",
        "is_fresh_today",
    ]
    for col in required_columns:
        assert col in sql, f"required column '{col}' missing from MV body"


def test_upgrade_lifts_composite_from_conviction_table() -> None:
    """Spec: composite = (conviction_score - 0.5) * 20, lifted from atlas_stock_conviction_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert (
        "atlas_stock_conviction_daily" in sql
    ), "MV must read conviction_score from atlas_stock_conviction_daily"
    assert "conviction_score" in sql
    # The mapping itself — accept either explicit literal or the algebraic form
    assert (
        "0.5" in sql and "20" in sql
    ) or "* 20" in sql, "composite remap (score - 0.5) * 20 not present"


def test_upgrade_maps_confidence_label_to_band() -> None:
    """confidence_label industry_grade/baseline/descriptive_only → H/M/L."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    for label in ("industry_grade", "baseline", "descriptive_only"):
        assert label in sql, f"confidence label '{label}' must appear in CASE mapping"


def test_upgrade_filters_open_signal_calls_for_cross_cell_depth() -> None:
    """cross_cell_depth uses only open calls (exit_date IS NULL)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "atlas_signal_calls" in sql
    assert (
        "exit_date is null" in sql
    ), "MV must filter signal_calls on exit_date IS NULL for open positions"


def test_upgrade_creates_unique_index_for_concurrent_refresh() -> None:
    """CONCURRENTLY refresh requires a unique index on the MV."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE UNIQUE INDEX" in joined
    assert "MV_STOCK_LIST_V6" in joined
    assert "INSTRUMENT_ID" in joined


def test_upgrade_uses_idempotent_ddl() -> None:
    """All MV / index DDL must be IF NOT EXISTS — migration must be re-runnable safely."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    # All CREATE statements should be idempotent
    create_count = sql.count("CREATE MATERIALIZED VIEW")
    if_not_exists_mv = sql.count("CREATE MATERIALIZED VIEW IF NOT EXISTS")
    assert create_count == if_not_exists_mv, "MV CREATE must use IF NOT EXISTS"


# --- downgrade ----------------------------------------------------------


def test_downgrade_drops_materialized_view() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "DROP MATERIALIZED VIEW" in joined
    assert "MV_STOCK_LIST_V6" in joined


def test_downgrade_uses_idempotent_ddl() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "DROP MATERIALIZED VIEW IF EXISTS" in sql, "downgrade DROP must be IF EXISTS"


# --- integration tests (live DB) ----------------------------------------


@_SKIP_INTEGRATION
def test_mv_refresh_populates_rows() -> None:  # pragma: no cover - integration only
    """Refresh the MV against the live DB and assert ≥ 1 row per active M1 instrument."""
    import sqlalchemy as sa

    from atlas.db import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_stock_list_v6"))
        row_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM atlas.mv_stock_list_v6")
        ).scalar_one()
    assert row_count > 0, "mv_stock_list_v6 produced zero rows after refresh"


@_SKIP_INTEGRATION
def test_mv_concurrent_refresh_succeeds() -> None:  # pragma: no cover - integration only
    """The unique index on instrument_id must permit CONCURRENT refresh."""
    import sqlalchemy as sa

    from atlas.db import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        # First refresh to populate (non-concurrent ok)
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_stock_list_v6"))
        # Then concurrent — fails if the unique index is missing or non-unique
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_stock_list_v6"))


@_SKIP_INTEGRATION
def test_mv_composite_in_expected_range() -> None:  # pragma: no cover - integration only
    """composite_score must be in [-10, +10] per the lift mapping."""
    import sqlalchemy as sa

    from atlas.db import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_stock_list_v6"))
        result = conn.execute(
            sa.text("""
            SELECT MIN(composite_score), MAX(composite_score)
            FROM atlas.mv_stock_list_v6
            WHERE composite_score IS NOT NULL
            """)
        ).first()
    if result and result[0] is not None:
        assert result[0] >= -10, f"composite_score min {result[0]} < -10"
        assert result[1] <= 10, f"composite_score max {result[1]} > +10"


@_SKIP_INTEGRATION
def test_mv_confidence_band_is_h_m_l_or_null() -> None:  # pragma: no cover - integration only
    import sqlalchemy as sa

    from atlas.db import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_stock_list_v6"))
        bands = {
            row[0]
            for row in conn.execute(
                sa.text("SELECT DISTINCT confidence_band FROM atlas.mv_stock_list_v6")
            ).all()
        }
    bands.discard(None)
    assert bands.issubset({"H", "M", "L"}), f"unexpected confidence band values: {bands}"
