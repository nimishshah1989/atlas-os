"""Tests for migration 092 — atlas_portfolio_policy.

Lightweight (import-level) tests run everywhere without a DB.
Integration tests (requires ATLAS_INTEGRATION_TESTS=1) verify the live DB.
"""

from __future__ import annotations

import importlib
import inspect
import os

import pytest

# ---------------------------------------------------------------------------
# Import-level (no DB) — always run
# ---------------------------------------------------------------------------

_MOD = importlib.import_module("migrations.versions.092_atlas_portfolio_policy")


def test_revision_string() -> None:
    """Migration 092 has the correct revision identifier."""
    assert _MOD.revision == "092_atlas_portfolio_policy"


def test_down_revision_points_at_091() -> None:
    """down_revision must be the real 091 revision string (not just '091')."""
    assert _MOD.down_revision == "091_fund_recommendation_enum_fix"


def test_upgrade_callable() -> None:
    """upgrade() is defined and callable."""
    assert callable(_MOD.upgrade)


def test_downgrade_callable() -> None:
    """downgrade() is defined and callable."""
    assert callable(_MOD.downgrade)


def test_upgrade_takes_no_positional_args() -> None:
    """upgrade() matches Alembic's zero-arg calling convention."""
    sig = inspect.signature(_MOD.upgrade)
    params = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
    assert len(params) == 0


def test_downgrade_takes_no_positional_args() -> None:
    """downgrade() matches Alembic's zero-arg calling convention."""
    sig = inspect.signature(_MOD.downgrade)
    params = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
    assert len(params) == 0


def test_house_default_coherence_check_defined() -> None:
    """upgrade() source contains the house-default coherence CHECK constraint."""
    source = inspect.getsource(_MOD.upgrade)
    assert "ck_portfolio_policy_house_default_no_portfolio" in source, (
        "CHECK constraint ck_portfolio_policy_house_default_no_portfolio "
        "must be defined inside upgrade()"
    )
    assert "NOT is_house_default OR portfolio_id IS NULL" in source, (
        "CHECK expression 'NOT is_house_default OR portfolio_id IS NULL' "
        "must be present in upgrade()"
    )


# ---------------------------------------------------------------------------
# Integration tests — skipped unless ATLAS_INTEGRATION_TESTS=1
# ---------------------------------------------------------------------------

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB, EC2 only)",
)

_REQUIRED_COLUMNS = {
    "id",
    "portfolio_id",
    "is_house_default",
    # Deployment
    "cash_floor_pct",
    "respect_regime_cap",
    # Concentration
    "max_per_stock_pct",
    "max_per_sector_pct",
    "max_small_cap_pct",
    "min_holdings",
    "max_positions",
    # Entry
    "buy_states",
    "min_within_state_rank",
    "min_rs_rank",
    # Exit
    "hard_stop_pct",
    "state_exit_trim",
    "state_exit_full",
    "trailing_stop_pct",
    # Instrument / Benchmark / Cadence
    "instrument_universe",
    "benchmark",
    "rebalance_cadence",
    # Audit
    "created_at",
    "updated_at",
}


@_SKIP_INTEGRATION
def test_portfolio_policy_table_exists(db_engine) -> None:  # type: ignore[no-untyped-def]
    """Migration 092 creates atlas_portfolio_policy with all required columns."""
    from sqlalchemy import text

    with db_engine.connect() as c:
        cols = c.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'atlas'
                  AND table_name   = 'atlas_portfolio_policy'
            """)
        ).fetchall()
    found = {r[0] for r in cols}
    missing = _REQUIRED_COLUMNS - found
    assert not missing, f"missing columns in atlas_portfolio_policy: {missing}"


@_SKIP_INTEGRATION
def test_portfolio_policy_partial_unique_index(db_engine) -> None:  # type: ignore[no-untyped-def]
    """Partial unique index on is_house_default=TRUE exists."""
    from sqlalchemy import text

    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'atlas'
                  AND tablename  = 'atlas_portfolio_policy'
                  AND indexname  = 'uix_portfolio_policy_house_default'
            """)
        ).fetchall()
    assert len(rows) == 1, "partial unique index uix_portfolio_policy_house_default not found"
    indexdef = rows[0][1]
    assert "WHERE" in indexdef.upper(), "index must be a partial index (has WHERE clause)"
    assert "UNIQUE" in indexdef.upper(), "index must be unique"


@_SKIP_INTEGRATION
def test_portfolio_policy_check_instrument_universe(db_engine) -> None:  # type: ignore[no-untyped-def]
    """instrument_universe CHECK constraint rejects invalid values."""
    import uuid

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with db_engine.begin() as c:
            c.execute(
                text("""
                    INSERT INTO atlas.atlas_portfolio_policy
                        (id, is_house_default, instrument_universe,
                         benchmark, rebalance_cadence)
                    VALUES
                        (:id, FALSE, 'invalid_universe', 'NIFTY500', 'daily')
                """),
                {"id": str(uuid.uuid4())},
            )


@_SKIP_INTEGRATION
def test_portfolio_policy_check_rebalance_cadence(db_engine) -> None:  # type: ignore[no-untyped-def]
    """rebalance_cadence CHECK constraint rejects invalid values."""
    import uuid

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with db_engine.begin() as c:
            c.execute(
                text("""
                    INSERT INTO atlas.atlas_portfolio_policy
                        (id, is_house_default, instrument_universe,
                         benchmark, rebalance_cadence)
                    VALUES
                        (:id, FALSE, 'direct_equity', 'NIFTY500', 'quarterly')
                """),
                {"id": str(uuid.uuid4())},
            )


@_SKIP_INTEGRATION
def test_portfolio_policy_only_one_house_default(db_engine) -> None:  # type: ignore[no-untyped-def]
    """Partial unique index prevents two rows with is_house_default=TRUE."""
    import uuid

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    id1 = str(uuid.uuid4())
    id2 = str(uuid.uuid4())
    try:
        with db_engine.begin() as c:
            c.execute(
                text("""
                    INSERT INTO atlas.atlas_portfolio_policy
                        (id, is_house_default, instrument_universe,
                         benchmark, rebalance_cadence)
                    VALUES
                        (:id, TRUE, 'direct_equity', 'NIFTY500', 'daily')
                """),
                {"id": id1},
            )
        with pytest.raises(IntegrityError):
            with db_engine.begin() as c:
                c.execute(
                    text("""
                        INSERT INTO atlas.atlas_portfolio_policy
                            (id, is_house_default, instrument_universe,
                             benchmark, rebalance_cadence)
                        VALUES
                            (:id, TRUE, 'direct_equity', 'NIFTY500', 'weekly')
                    """),
                    {"id": id2},
                )
    finally:
        with db_engine.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_portfolio_policy WHERE id IN (:id1, :id2)"),
                {"id1": id1, "id2": id2},
            )
