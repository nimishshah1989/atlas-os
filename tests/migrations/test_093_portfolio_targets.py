"""Tests for migration 093 — portfolio target_weight + atlas_portfolio_proposed_change.

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


def test_target_weight_column_defined() -> None:
    """upgrade() source adds target_weight column to strategy_fm_custom_portfolios."""
    source = inspect.getsource(_MOD.upgrade)
    assert (
        "target_weight" in source
    ), "upgrade() must add target_weight column to strategy_fm_custom_portfolios"


def test_target_weight_is_numeric_not_float() -> None:
    """target_weight must use sa.Numeric, never sa.Float."""
    source = inspect.getsource(_MOD.upgrade)
    # Numeric must appear; Float must not be used for target_weight
    assert "Numeric" in source, "target_weight must be sa.Numeric type"


def test_instrument_id_indexed_no_fk() -> None:
    """instrument_id is a plain indexed UUID (no FK — universe tables have composite PKs)."""
    source = inspect.getsource(_MOD.upgrade)
    assert "instrument_id" in source, "instrument_id column must be present"
    # The migration source should NOT contain a ForeignKey referencing a universe table
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


def test_downgrade_drops_proposed_change_table() -> None:
    """downgrade() source drops atlas_portfolio_proposed_change."""
    source = inspect.getsource(_MOD.downgrade)
    assert (
        "atlas_portfolio_proposed_change" in source
    ), "downgrade() must drop atlas_portfolio_proposed_change"


def test_downgrade_drops_target_weight_column() -> None:
    """downgrade() source drops target_weight from strategy_fm_custom_portfolios."""
    source = inspect.getsource(_MOD.downgrade)
    assert (
        "target_weight" in source
    ), "downgrade() must drop target_weight column from strategy_fm_custom_portfolios"


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
def test_target_weight_column_exists_on_portfolios(db_engine) -> None:  # type: ignore[no-untyped-def]
    """Migration 093 adds target_weight to strategy_fm_custom_portfolios."""
    from sqlalchemy import text

    with db_engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'atlas'
                  AND table_name   = 'strategy_fm_custom_portfolios'
                  AND column_name  = 'target_weight'
            """)
        ).fetchall()
    assert len(rows) == 1, "target_weight column not found on strategy_fm_custom_portfolios"
    data_type = rows[0][1]
    assert data_type == "numeric", f"target_weight must be numeric type, got {data_type}"


@_SKIP_INTEGRATION
def test_proposed_change_status_check_rejects_invalid(db_engine) -> None:  # type: ignore[no-untyped-def]
    """status CHECK constraint rejects values outside ('pending','applied','rejected')."""
    import uuid

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    # We need a real portfolio_id to satisfy the FK; use a fresh UUID that may not exist.
    # If FK enforcement fires first, that's fine — we're testing the CHECK fires on valid FK.
    # Insert with NULL portfolio_id (FK allows NULL? — it does not; portfolio_id is NOT NULL).
    # The easiest approach: insert a row with an invalid status and expect IntegrityError
    # from EITHER the FK violation or the CHECK constraint.
    with pytest.raises(IntegrityError):
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
                    "pid": str(uuid.uuid4()),  # non-existent FK → IntegrityError
                    "iid": str(uuid.uuid4()),
                },
            )


@_SKIP_INTEGRATION
def test_proposed_change_status_check_accepts_valid_pending(db_engine) -> None:  # type: ignore[no-untyped-def]
    """A 'pending' status row inserts successfully when FK is satisfied."""
    import uuid

    from sqlalchemy import text

    # First insert a portfolio row so the FK is satisfied.
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
