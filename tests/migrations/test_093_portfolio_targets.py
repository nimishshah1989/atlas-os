"""Tests for migration 093 — per-instrument target_weight_pct in instruments JSONB
+ atlas_portfolio_proposed_change table.

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

_MOD = importlib.import_module("migrations.versions.093_portfolio_targets_holdings")


def test_revision_string() -> None:
    """Migration 093 has the correct revision identifier."""
    assert _MOD.revision == "093_portfolio_targets_holdings"


def test_down_revision_points_at_092() -> None:
    """down_revision must be the real 092 revision string."""
    assert _MOD.down_revision == "092_atlas_portfolio_policy"


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


def test_proposed_change_table_defined_in_upgrade() -> None:
    """upgrade() source creates the atlas_portfolio_proposed_change table."""
    source = inspect.getsource(_MOD.upgrade)
    assert (
        "atlas_portfolio_proposed_change" in source
    ), "upgrade() must create atlas_portfolio_proposed_change"


def test_status_check_constraint_defined() -> None:
    """upgrade() source contains the status CHECK constraint."""
    source = inspect.getsource(_MOD.upgrade)
    assert (
        "ck_proposed_change_status" in source
    ), "CHECK constraint ck_proposed_change_status must be defined inside upgrade()"
    assert (
        "pending" in source and "applied" in source and "rejected" in source
    ), "CHECK expression must reference 'pending', 'applied', 'rejected'"


def test_no_scalar_target_weight_column_added() -> None:
    """upgrade() must NOT add a portfolio-level scalar target_weight column.

    A single scalar cannot express per-instrument targets (Task 3.5). The
    per-instrument home is target_weight_pct inside the instruments JSONB array.
    """
    source = inspect.getsource(_MOD.upgrade)
    assert "add_column" not in source, (
        "upgrade() must not use op.add_column — the ambiguous scalar "
        "target_weight column was removed in favour of per-instrument JSONB"
    )


def test_jsonb_backfill_target_weight_pct_in_upgrade() -> None:
    """upgrade() source contains the JSONB backfill for target_weight_pct."""
    source = inspect.getsource(_MOD.upgrade)
    assert "target_weight_pct" in source, (
        "upgrade() must reference target_weight_pct " "(backfilled into instruments JSONB elements)"
    )


def test_backfill_sql_module_level() -> None:
    """Module defines the _BACKFILL_TARGET_WEIGHT_PCT SQL constant."""
    assert hasattr(
        _MOD, "_BACKFILL_TARGET_WEIGHT_PCT"
    ), "_BACKFILL_TARGET_WEIGHT_PCT SQL constant must be present in the module"
    sql = _MOD._BACKFILL_TARGET_WEIGHT_PCT
    assert "target_weight_pct" in sql
    assert "jsonb_agg" in sql
    assert "jsonb_array_elements" in sql


def test_strip_sql_module_level() -> None:
    """Module defines the _STRIP_TARGET_WEIGHT_PCT SQL constant for downgrade."""
    assert hasattr(
        _MOD, "_STRIP_TARGET_WEIGHT_PCT"
    ), "_STRIP_TARGET_WEIGHT_PCT SQL constant must be present in the module"
    sql = _MOD._STRIP_TARGET_WEIGHT_PCT
    assert "target_weight_pct" in sql
    assert "jsonb_agg" in sql


def test_downgrade_strips_target_weight_pct() -> None:
    """downgrade() source strips target_weight_pct from instruments JSONB."""
    source = inspect.getsource(_MOD.downgrade)
    assert (
        "target_weight_pct" in source
    ), "downgrade() must strip target_weight_pct from instruments JSONB elements"


def test_downgrade_drops_proposed_change_table() -> None:
    """downgrade() drops the atlas_portfolio_proposed_change table.

    downgrade() references the module-level _TABLE constant which holds the
    table name, so we verify via the constant rather than the literal string.
    """
    assert (
        _MOD._TABLE == "atlas_portfolio_proposed_change"
    ), "_TABLE module constant must equal 'atlas_portfolio_proposed_change'"
    source = inspect.getsource(_MOD.downgrade)
    assert "drop_table" in source, "downgrade() must call op.drop_table"
    assert (
        "_TABLE" in source
    ), "downgrade() must reference _TABLE (the atlas_portfolio_proposed_change table name)"


def test_downgrade_does_not_drop_target_weight_column() -> None:
    """downgrade() must NOT call drop_column for the now-removed scalar target_weight.

    The column no longer exists; dropping it in downgrade() would error on a live DB.
    """
    source = inspect.getsource(_MOD.downgrade)
    assert "drop_column" not in source, (
        "downgrade() must not reference drop_column — the scalar target_weight "
        "column was removed from the migration"
    )


def test_instrument_id_indexed_no_fk() -> None:
    """instrument_id is a plain indexed UUID (no FK — universe tables have composite PKs)."""
    source = inspect.getsource(_MOD.upgrade)
    assert "instrument_id" in source, "instrument_id column must be present"
    assert "atlas_universe_stocks" not in source, (
        "instrument_id must NOT have a FK to atlas_universe_stocks "
        "(composite PK — not a valid FK target)"
    )


def test_portfolio_id_fk_defined() -> None:
    """portfolio_id references atlas.strategy_fm_custom_portfolios.id with CASCADE."""
    source = inspect.getsource(_MOD.upgrade)
    assert (
        "strategy_fm_custom_portfolios.id" in source
    ), "portfolio_id must FK to atlas.strategy_fm_custom_portfolios.id"
    assert "CASCADE" in source, "FK must have ondelete CASCADE"


def test_timestamps_tz_aware() -> None:
    """created_at and updated_at columns use timezone=True."""
    source = inspect.getsource(_MOD.upgrade)
    assert "timezone=True" in source, "created_at and updated_at must use DateTime(timezone=True)"


def test_rationale_column_defined() -> None:
    """upgrade() source includes a rationale column."""
    source = inspect.getsource(_MOD.upgrade)
    assert (
        "rationale" in source
    ), "upgrade() must include a rationale column for Wave 3 Act affordance"


def test_numeric_type_used_for_proposed_weight() -> None:
    """proposed_weight must use sa.Numeric, never sa.Float."""
    source = inspect.getsource(_MOD.upgrade)
    assert "Numeric" in source, "proposed_weight must be sa.Numeric type"


# ---------------------------------------------------------------------------
# Integration tests — skipped unless ATLAS_INTEGRATION_TESTS=1
# ---------------------------------------------------------------------------

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB, EC2 only)",
)

_REQUIRED_PROPOSED_CHANGE_COLUMNS = {
    "id",
    "portfolio_id",
    "instrument_id",
    "proposed_weight",
    "status",
    "rationale",
    "created_at",
    "updated_at",
}


@_SKIP_INTEGRATION
def test_proposed_change_table_exists(db_engine) -> None:  # type: ignore[no-untyped-def]
    """Migration 093 creates atlas_portfolio_proposed_change with all required columns."""
    from sqlalchemy import text

    with db_engine.connect() as c:
        cols = c.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'atlas'
                  AND table_name   = 'atlas_portfolio_proposed_change'
            """)
        ).fetchall()
    found = {r[0] for r in cols}
    missing = _REQUIRED_PROPOSED_CHANGE_COLUMNS - found
    assert not missing, f"missing columns in atlas_portfolio_proposed_change: {missing}"


@_SKIP_INTEGRATION
def test_instruments_jsonb_has_target_weight_pct(db_engine) -> None:  # type: ignore[no-untyped-def]
    """After migration 093, all non-empty instruments JSONB arrays contain target_weight_pct."""
    from sqlalchemy import text

    with db_engine.connect() as c:
        # Count rows where at least one element is missing the key.
        row = c.execute(
            text("""
                SELECT COUNT(*) AS bad_count
                FROM atlas.strategy_fm_custom_portfolios
                WHERE instruments IS NOT NULL
                  AND jsonb_typeof(instruments) = 'array'
                  AND jsonb_array_length(instruments) > 0
                  AND EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements(instruments) AS elem
                      WHERE NOT (elem ? 'target_weight_pct')
                  )
            """)
        ).fetchone()
    assert row is not None
    assert row[0] == 0, (
        f"{row[0]} portfolio row(s) still have instruments elements "
        "missing target_weight_pct after migration 093"
    )


@_SKIP_INTEGRATION
def test_no_scalar_target_weight_on_portfolios_table(db_engine) -> None:  # type: ignore[no-untyped-def]
    """Migration 093 must NOT have added a scalar target_weight column.

    Per-instrument targets live in the instruments JSONB array, not in a
    portfolio-level scalar on strategy_fm_custom_portfolios.
    """
    from sqlalchemy import text

    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'atlas'
                  AND table_name   = 'strategy_fm_custom_portfolios'
                  AND column_name  = 'target_weight'
            """)
        ).fetchall()
    assert len(rows) == 0, (
        "scalar target_weight column must NOT exist on strategy_fm_custom_portfolios; "
        "per-instrument targets live in the instruments JSONB array"
    )


@_SKIP_INTEGRATION
def test_proposed_change_status_check_rejects_invalid(db_engine) -> None:  # type: ignore[no-untyped-def]
    """status CHECK constraint rejects values outside ('pending','applied','rejected').

    A real portfolio row is inserted first so the FK is satisfied — this isolates
    the CHECK constraint as the sole cause of the IntegrityError.
    """
    import uuid

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    portfolio_id = str(uuid.uuid4())

    # Create a real portfolio so the FK cannot fire — only the CHECK can reject.
    with db_engine.begin() as c:
        c.execute(
            text("""
                INSERT INTO atlas.strategy_fm_custom_portfolios
                    (id, name, instruments)
                VALUES
                    (:id, 'test-093-check', '[]'::jsonb)
            """),
            {"id": portfolio_id},
        )

    try:
        with pytest.raises(IntegrityError, match="ck_proposed_change_status"):
            with db_engine.begin() as c:
                c.execute(
                    text("""
                        INSERT INTO atlas.atlas_portfolio_proposed_change
                            (id, portfolio_id, instrument_id, proposed_weight, status)
                        VALUES
                            (:id, :pid, :iid, 5.0000, 'invalid_status')
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "pid": portfolio_id,
                        "iid": str(uuid.uuid4()),
                    },
                )
    finally:
        with db_engine.begin() as c:
            c.execute(
                text("DELETE FROM atlas.strategy_fm_custom_portfolios WHERE id = :id"),
                {"id": portfolio_id},
            )


@_SKIP_INTEGRATION
def test_proposed_change_status_check_accepts_valid_pending(db_engine) -> None:  # type: ignore[no-untyped-def]
    """A 'pending' status row inserts successfully when FK is satisfied."""
    import uuid

    from sqlalchemy import text

    portfolio_id = str(uuid.uuid4())
    proposed_id = str(uuid.uuid4())
    instrument_id = str(uuid.uuid4())

    try:
        with db_engine.begin() as c:
            c.execute(
                text("""
                    INSERT INTO atlas.strategy_fm_custom_portfolios
                        (id, name, instruments)
                    VALUES
                        (:id, 'test-093', '[]'::jsonb)
                """),
                {"id": portfolio_id},
            )
            c.execute(
                text("""
                    INSERT INTO atlas.atlas_portfolio_proposed_change
                        (id, portfolio_id, instrument_id, proposed_weight, status)
                    VALUES
                        (:id, :pid, :iid, 5.0000, 'pending')
                """),
                {"id": proposed_id, "pid": portfolio_id, "iid": instrument_id},
            )
    finally:
        with db_engine.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_portfolio_proposed_change WHERE id = :id"),
                {"id": proposed_id},
            )
            c.execute(
                text("DELETE FROM atlas.strategy_fm_custom_portfolios WHERE id = :id"),
                {"id": portfolio_id},
            )
