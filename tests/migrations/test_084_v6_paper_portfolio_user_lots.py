"""Regression tests for migration 084 — atlas_paper_portfolio + atlas_user_lots.

Tables + objects created:
- atlas_paper_portfolio  — E1 per-user paper portfolio mirroring POSITIVE
  signal triggers (uniqueness on user_id+instrument_id+cell_id+tenure+entry_date).
- atlas_user_lots        — minimal manual real-holding entry (E3 tax-aware
  resolver deferred to v7 per outside-voice T7).

Row-Level Security is enabled on BOTH tables with FOR ALL policies that
scope access to `request.jwt.claims ->> 'sub' = user_id`. Service-role
connections bypass RLS.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, indexes, FKs, partial index DDL,
RLS enable + policies, and downgrade ordering match the v6 spec.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the migration applies cleanly on a real Postgres + that the RLS
policies actually filter rows for a non-service JWT. Skipped by default;
run on EC2 / staging.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.084_v6_paper_portfolio_user_lots"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="live-DB tests — set ATLAS_INTEGRATION_TESTS=1 to run (EC2 only)",
)


def _load() -> types.ModuleType:
    return importlib.import_module(_MODULE)


def _run_upgrade_with_mock() -> MagicMock:
    """Run upgrade() with op mocked; return the mock for assertions."""
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


def _table_call(table_name: str):
    """Return the create_table call for the named table."""
    mock_op = _run_upgrade_with_mock()
    for call in mock_op.create_table.call_args_list:
        if call.args[0] == table_name:
            return call
    raise AssertionError(f"{table_name} not created")


def _executed_sql_upgrade() -> list[str]:
    """Return all SQL strings passed to op.execute() during upgrade."""
    mock_op = _run_upgrade_with_mock()
    return [
        c.args[0] if isinstance(c.args[0], str) else str(c.args[0])
        for c in mock_op.execute.call_args_list
    ]


def _executed_sql_downgrade() -> list[str]:
    mock_op = _run_downgrade_with_mock()
    return [
        c.args[0] if isinstance(c.args[0], str) else str(c.args[0])
        for c in mock_op.execute.call_args_list
    ]


# ---------------------------------------------------------------------------
# Unit: metadata
# ---------------------------------------------------------------------------


class TestMigrationMetadata:
    def test_revision(self) -> None:
        assert _load().revision == "084"

    def test_down_revision_083(self) -> None:
        assert _load().down_revision == "083"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: upgrade() creates both tables
# ---------------------------------------------------------------------------


class TestUpgradeCreatesTables:
    def test_creates_paper_portfolio_table(self) -> None:
        mock_op = _run_upgrade_with_mock()
        table_names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_paper_portfolio" in table_names

    def test_creates_user_lots_table(self) -> None:
        mock_op = _run_upgrade_with_mock()
        table_names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_user_lots" in table_names

    def test_only_two_tables_created(self) -> None:
        """Migration 084 is scoped to two tables — no scope creep."""
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_table.call_count == 2

    def test_paper_portfolio_in_atlas_schema(self) -> None:
        assert _table_call("atlas_paper_portfolio").kwargs.get("schema") == "atlas"

    def test_user_lots_in_atlas_schema(self) -> None:
        assert _table_call("atlas_user_lots").kwargs.get("schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: atlas_paper_portfolio column inventory
# ---------------------------------------------------------------------------


class TestPaperPortfolioColumns:
    def _column_names(self) -> list[str]:
        call = _table_call("atlas_paper_portfolio")
        return [c.name for c in call.args[1:] if hasattr(c, "name")]

    def test_has_id(self) -> None:
        assert "id" in self._column_names()

    def test_has_user_id(self) -> None:
        assert "user_id" in self._column_names()

    def test_has_signal_call_id(self) -> None:
        assert "signal_call_id" in self._column_names()

    def test_has_instrument_id(self) -> None:
        assert "instrument_id" in self._column_names()

    def test_has_cell_id(self) -> None:
        assert "cell_id" in self._column_names()

    def test_has_tenure(self) -> None:
        assert "tenure" in self._column_names()

    def test_has_entry_date(self) -> None:
        assert "entry_date" in self._column_names()

    def test_has_entry_price(self) -> None:
        assert "entry_price" in self._column_names()

    def test_has_exit_date(self) -> None:
        assert "exit_date" in self._column_names()

    def test_has_exit_price(self) -> None:
        assert "exit_price" in self._column_names()

    def test_has_exit_reason(self) -> None:
        assert "exit_reason" in self._column_names()

    def test_has_excess_return(self) -> None:
        assert "excess_return" in self._column_names()

    def test_has_created_at(self) -> None:
        assert "created_at" in self._column_names()

    def test_has_updated_at(self) -> None:
        assert "updated_at" in self._column_names()


# ---------------------------------------------------------------------------
# Unit: atlas_paper_portfolio column rules (nullable / pk / types)
# ---------------------------------------------------------------------------


class TestPaperPortfolioColumnRules:
    def _columns(self) -> dict:
        call = _table_call("atlas_paper_portfolio")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_id_is_primary_key(self) -> None:
        assert self._columns()["id"].primary_key is True

    def test_user_id_not_null(self) -> None:
        assert self._columns()["user_id"].nullable is False

    def test_signal_call_id_not_null(self) -> None:
        assert self._columns()["signal_call_id"].nullable is False

    def test_instrument_id_not_null(self) -> None:
        assert self._columns()["instrument_id"].nullable is False

    def test_cell_id_not_null(self) -> None:
        assert self._columns()["cell_id"].nullable is False

    def test_tenure_not_null(self) -> None:
        assert self._columns()["tenure"].nullable is False

    def test_entry_date_not_null(self) -> None:
        assert self._columns()["entry_date"].nullable is False

    def test_entry_price_not_null(self) -> None:
        assert self._columns()["entry_price"].nullable is False

    def test_exit_date_nullable(self) -> None:
        """exit_date populates when the cell exit fires; open positions
        keep NULL.
        """
        assert self._columns()["exit_date"].nullable is True

    def test_exit_price_nullable(self) -> None:
        assert self._columns()["exit_price"].nullable is True

    def test_exit_reason_nullable(self) -> None:
        assert self._columns()["exit_reason"].nullable is True

    def test_excess_return_nullable(self) -> None:
        """Computed at exit — NULL while position is open."""
        assert self._columns()["excess_return"].nullable is True

    def test_entry_price_is_numeric_not_float(self) -> None:
        """Financial domain rule: Numeric, not Float."""
        import sqlalchemy as sa

        col = self._columns()["entry_price"]
        assert isinstance(col.type, sa.Numeric)

    def test_excess_return_is_numeric_not_float(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["excess_return"]
        assert isinstance(col.type, sa.Numeric)

    def test_created_at_is_tz_aware(self) -> None:
        assert self._columns()["created_at"].type.timezone is True

    def test_updated_at_is_tz_aware(self) -> None:
        assert self._columns()["updated_at"].type.timezone is True


# ---------------------------------------------------------------------------
# Unit: atlas_paper_portfolio foreign keys
# ---------------------------------------------------------------------------


class TestPaperPortfolioForeignKeys:
    def _fks(self) -> list:
        call = _table_call("atlas_paper_portfolio")
        fks: list = []
        for c in call.args[1:]:
            if not hasattr(c, "foreign_keys"):
                continue
            for fk in c.foreign_keys:
                fks.append((c.name, fk))
        return fks

    def test_signal_call_id_fk_with_restrict(self) -> None:
        sc_fks = [fk for col, fk in self._fks() if col == "signal_call_id"]
        assert len(sc_fks) == 1
        fk = sc_fks[0]
        assert "atlas_signal_calls" in fk.target_fullname
        assert "signal_call_id" in fk.target_fullname
        assert fk.ondelete == "RESTRICT"

    def test_cell_id_fk_with_restrict(self) -> None:
        cell_fks = [fk for col, fk in self._fks() if col == "cell_id"]
        assert len(cell_fks) == 1
        fk = cell_fks[0]
        assert "atlas_cell_definitions" in fk.target_fullname
        assert "cell_id" in fk.target_fullname
        assert fk.ondelete == "RESTRICT"

    def test_no_fk_on_user_id(self) -> None:
        """user_id targets Supabase auth.users which lives in a different
        schema; we do NOT cross-schema FK to it.
        """
        user_fks = [fk for col, fk in self._fks() if col == "user_id"]
        assert len(user_fks) == 0

    def test_no_fk_on_instrument_id(self) -> None:
        """instrument_id is resolved at the application layer across
        stocks / etfs / mfs masters.
        """
        inst_fks = [fk for col, fk in self._fks() if col == "instrument_id"]
        assert len(inst_fks) == 0


# ---------------------------------------------------------------------------
# Unit: atlas_paper_portfolio uniqueness + partial index
# ---------------------------------------------------------------------------


class TestPaperPortfolioConstraintsAndIndexes:
    def test_unique_constraint_on_user_inst_cell_tenure_date(self) -> None:
        """Per /grill Q11 D11: uniqueness key is
        (user_id, instrument_id, cell_id, tenure, entry_date).
        """
        import sqlalchemy as sa

        call = _table_call("atlas_paper_portfolio")
        uqs = [arg for arg in call.args[1:] if isinstance(arg, sa.UniqueConstraint)]
        assert len(uqs) == 1, f"expected exactly one UniqueConstraint, got {len(uqs)}"
        uq = uqs[0]
        # UniqueConstraint is unbound (no table attached in mocked context),
        # so .columns is empty — use _pending_colargs which holds the names
        # passed at construction.
        cols = set(uq._pending_colargs)
        assert cols == {"user_id", "instrument_id", "cell_id", "tenure", "entry_date"}

    def test_partial_open_position_index_via_raw_sql(self) -> None:
        """Partial index `WHERE exit_date IS NULL` for the open-positions
        hot read path must be created via raw SQL (Alembic op.create_index
        doesn't support partial conditions across all backends consistently).
        """
        sql_list = _executed_sql_upgrade()
        partial = next(
            (
                sql
                for sql in sql_list
                if "ix_atlas_paper_portfolio_user_open" in sql
                and "WHERE exit_date IS NULL" in sql
                and "CREATE INDEX" in sql.upper()
            ),
            None,
        )
        assert partial is not None, "partial index on (user_id) WHERE exit_date IS NULL not found"
        assert "atlas.atlas_paper_portfolio" in partial
        assert "user_id" in partial

    def test_signal_call_id_index_for_cascade(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_paper_portfolio_signal_call_id" in names

    def test_entry_date_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_paper_portfolio_entry_date" in names

    def test_exit_date_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_paper_portfolio_exit_date" in names


# ---------------------------------------------------------------------------
# Unit: atlas_user_lots columns + types
# ---------------------------------------------------------------------------


class TestUserLotsColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_user_lots")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_has_id(self) -> None:
        assert "id" in self._columns()

    def test_has_user_id(self) -> None:
        assert "user_id" in self._columns()

    def test_has_instrument_id(self) -> None:
        assert "instrument_id" in self._columns()

    def test_has_lot_date(self) -> None:
        assert "lot_date" in self._columns()

    def test_has_quantity(self) -> None:
        assert "quantity" in self._columns()

    def test_has_cost_basis(self) -> None:
        assert "cost_basis" in self._columns()

    def test_has_is_realized(self) -> None:
        assert "is_realized" in self._columns()

    def test_has_realized_date(self) -> None:
        assert "realized_date" in self._columns()

    def test_has_realized_price(self) -> None:
        assert "realized_price" in self._columns()

    def test_id_is_primary_key(self) -> None:
        assert self._columns()["id"].primary_key is True

    def test_quantity_is_numeric_not_float(self) -> None:
        import sqlalchemy as sa

        assert isinstance(self._columns()["quantity"].type, sa.Numeric)

    def test_cost_basis_is_numeric_not_float(self) -> None:
        import sqlalchemy as sa

        assert isinstance(self._columns()["cost_basis"].type, sa.Numeric)

    def test_realized_price_is_numeric_not_float(self) -> None:
        import sqlalchemy as sa

        assert isinstance(self._columns()["realized_price"].type, sa.Numeric)

    def test_is_realized_default_false(self) -> None:
        """is_realized defaults FALSE — users record bought lots first,
        flip to true on sale.
        """
        col = self._columns()["is_realized"]
        assert col.nullable is False
        # server_default text contains FALSE.
        assert "FALSE" in str(col.server_default.arg).upper()

    def test_realized_date_nullable(self) -> None:
        assert self._columns()["realized_date"].nullable is True

    def test_realized_price_nullable(self) -> None:
        assert self._columns()["realized_price"].nullable is True


# ---------------------------------------------------------------------------
# Unit: atlas_user_lots indexes
# ---------------------------------------------------------------------------


class TestUserLotsIndexes:
    def test_user_instrument_composite_index(self) -> None:
        """Per CEO plan §E1 archived E3-v7 section: fast lookup on
        (user_id, instrument_id) — 'show me all TCS lots this user holds'.
        """
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_user_lots_user_instrument" in names

    def test_user_instrument_index_columns(self) -> None:
        mock_op = _run_upgrade_with_mock()
        for call in mock_op.create_index.call_args_list:
            if call.args[0] == "ix_atlas_user_lots_user_instrument":
                assert list(call.args[2]) == ["user_id", "instrument_id"]
                return
        pytest.fail("ix_atlas_user_lots_user_instrument index not found")


# ---------------------------------------------------------------------------
# Unit: Row-Level Security — enable + policies
# ---------------------------------------------------------------------------


class TestRowLevelSecurity:
    def test_rls_enabled_on_paper_portfolio(self) -> None:
        sql_list = _executed_sql_upgrade()
        enable = next(
            (
                sql
                for sql in sql_list
                if "atlas_paper_portfolio" in sql and "ENABLE ROW LEVEL SECURITY" in sql.upper()
            ),
            None,
        )
        assert enable is not None, "RLS not enabled on atlas_paper_portfolio"

    def test_rls_enabled_on_user_lots(self) -> None:
        sql_list = _executed_sql_upgrade()
        enable = next(
            (
                sql
                for sql in sql_list
                if "atlas_user_lots" in sql and "ENABLE ROW LEVEL SECURITY" in sql.upper()
            ),
            None,
        )
        assert enable is not None, "RLS not enabled on atlas_user_lots"

    def test_paper_portfolio_policy_created_with_jwt_scoping(self) -> None:
        sql_list = _executed_sql_upgrade()
        policy = next(
            (
                sql
                for sql in sql_list
                if "CREATE POLICY" in sql.upper()
                and "paper_portfolio_user_isolation" in sql
                and "atlas_paper_portfolio" in sql
            ),
            None,
        )
        assert policy is not None, "paper_portfolio_user_isolation policy not created"
        # JWT sub claim pattern.
        assert "request.jwt.claims" in policy
        assert "'sub'" in policy
        # user_id = JWT sub UUID cast.
        assert "user_id" in policy
        assert "::uuid" in policy
        # FOR ALL — covers SELECT/INSERT/UPDATE/DELETE.
        assert "FOR ALL" in policy.upper()
        # Both USING and WITH CHECK present.
        assert "USING" in policy.upper()
        assert "WITH CHECK" in policy.upper()

    def test_user_lots_policy_created_with_jwt_scoping(self) -> None:
        sql_list = _executed_sql_upgrade()
        policy = next(
            (
                sql
                for sql in sql_list
                if "CREATE POLICY" in sql.upper()
                and "user_lots_user_isolation" in sql
                and "atlas_user_lots" in sql
            ),
            None,
        )
        assert policy is not None, "user_lots_user_isolation policy not created"
        assert "request.jwt.claims" in policy
        assert "'sub'" in policy
        assert "user_id" in policy
        assert "::uuid" in policy
        assert "FOR ALL" in policy.upper()
        assert "USING" in policy.upper()
        assert "WITH CHECK" in policy.upper()


# ---------------------------------------------------------------------------
# Unit: downgrade
# ---------------------------------------------------------------------------


class TestDowngrade:
    def test_drops_both_tables(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {"atlas_paper_portfolio", "atlas_user_lots"}

    def test_drops_policies_before_tables(self) -> None:
        """DROP POLICY must come before DROP TABLE — policies are
        attached to the table and Postgres errors otherwise on some
        configurations / replication setups.
        """
        mod = _load()
        recorded: list[tuple[str, str]] = []
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record(method_name):
                def _fn(*args, **kwargs):
                    name = args[0] if args else kwargs.get("name", "")
                    recorded.append((method_name, str(name)))
                    return MagicMock()

                return _fn

            mock_op.drop_index.side_effect = _record("drop_index")
            mock_op.drop_table.side_effect = _record("drop_table")
            mock_op.execute.side_effect = _record("execute")
            mod.downgrade()

        first_table_drop = next(i for i, (m, _) in enumerate(recorded) if m == "drop_table")
        # Both policy drops must precede the first drop_table.
        pp_policy_idx = next(
            (
                i
                for i, (m, payload) in enumerate(recorded[:first_table_drop])
                if m == "execute"
                and "DROP POLICY" in payload.upper()
                and "paper_portfolio_user_isolation" in payload
            ),
            None,
        )
        ul_policy_idx = next(
            (
                i
                for i, (m, payload) in enumerate(recorded[:first_table_drop])
                if m == "execute"
                and "DROP POLICY" in payload.upper()
                and "user_lots_user_isolation" in payload
            ),
            None,
        )
        assert pp_policy_idx is not None, "paper_portfolio policy drop missing before tables"
        assert ul_policy_idx is not None, "user_lots policy drop missing before tables"

    def test_disables_rls_on_downgrade(self) -> None:
        sql_list = _executed_sql_downgrade()
        assert any(
            "atlas_paper_portfolio" in sql and "DISABLE ROW LEVEL SECURITY" in sql.upper()
            for sql in sql_list
        )
        assert any(
            "atlas_user_lots" in sql and "DISABLE ROW LEVEL SECURITY" in sql.upper()
            for sql in sql_list
        )

    def test_drops_partial_open_position_index_via_raw_sql(self) -> None:
        """Partial index was created via raw SQL; downgrade must drop it
        via raw SQL too (drop_index by name may not target partial indexes
        cleanly across all dialect versions).
        """
        sql_list = _executed_sql_downgrade()
        drop = next(
            (
                sql
                for sql in sql_list
                if "DROP INDEX" in sql.upper() and "ix_atlas_paper_portfolio_user_open" in sql
            ),
            None,
        )
        assert drop is not None, "partial open-position index not dropped via raw SQL"

    def test_drops_all_named_indexes(self) -> None:
        """Every named index created via op.create_index must be dropped
        via op.drop_index on downgrade.
        """
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_index.call_args_list}
        expected = {
            "ix_atlas_user_lots_user_instrument",
            "ix_atlas_paper_portfolio_exit_date",
            "ix_atlas_paper_portfolio_entry_date",
            "ix_atlas_paper_portfolio_signal_call_id",
        }
        missing = expected - dropped
        assert not missing, f"missing index drops on downgrade: {missing}"

    def test_does_not_drop_atlas_tenure_enum(self) -> None:
        """atlas_tenure enum is owned by migration 080 — 084 must NOT
        drop it on downgrade.
        """
        sql_list = _executed_sql_downgrade()
        for sql in sql_list:
            assert not (
                "atlas_tenure" in sql and "DROP TYPE" in sql.upper()
            ), f"downgrade must not DROP TYPE atlas_tenure: {sql!r}"

    def test_does_not_drop_atlas_exit_reason_enum(self) -> None:
        """atlas_exit_reason enum is owned by migration 080 — 084 must NOT
        drop it on downgrade.
        """
        sql_list = _executed_sql_downgrade()
        for sql in sql_list:
            assert not (
                "atlas_exit_reason" in sql and "DROP TYPE" in sql.upper()
            ), f"downgrade must not DROP TYPE atlas_exit_reason: {sql!r}"


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only."""

    def test_migration_applies(self) -> None:
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_paper_portfolio_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_user_lots_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_rls_actually_filters_rows(self) -> None:
        pytest.skip(
            "verify that connecting as a user-facing role with a different JWT "
            "sub does not see another user's rows"
        )

    def test_service_role_bypasses_rls(self) -> None:
        pytest.skip("verify service_role connection sees all rows across users")
