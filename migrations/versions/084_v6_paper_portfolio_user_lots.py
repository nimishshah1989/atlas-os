"""v6 — atlas_paper_portfolio + atlas_user_lots (E1 paper portfolio + manual lots).

Adds the E1 paper-portfolio surface (tracked per authenticated user, mirrors
every POSITIVE signal trigger at T+1 open) and the manual-lot entry table
for users without broker integration. E3 tax-aware surfacing of real
holdings is deferred to v7 per outside-voice T7 — v6 stores lots but does
NOT use them for tax-context resolution.

Design contract
---------------
- `atlas_paper_portfolio` rows are written by the portfolio writer cron
  whenever a new POSITIVE `atlas_signal_calls` row appears. Uniqueness key
  per CEO plan §E1 (locked /grill Q11 D11):
        (user_id, instrument_id, cell_id, tenure, entry_date)
  This prevents the writer from double-inserting the same trigger for the
  same user on the same day.

- Partial index `WHERE exit_date IS NULL` powers the "open positions for
  user X" hot read path per CONTEXT.md signal_call_id cadence section.

- `atlas_user_lots` is a thin minimal-fields lot table. Quantity +
  cost_basis are stored as Numeric (financial-domain rule: no float for
  money). `is_realized` flips true when the user records a sale; the
  resolver that surfaces tax-aware nudges lives in v7.

Row-Level Security
------------------
Both tables enable RLS with a single FOR ALL policy each, scoping access
to `request.jwt.claims ->> 'sub' = user_id`. Supabase / FastAPI sets the
JWT claim via `SET request.jwt.claims = '...'` on each request when the
user-facing role connects. Service-role connections (cron writers) use
the postgres / service_role role which bypasses RLS by default.

FK target schemas
-----------------
- `signal_call_id` references `atlas.atlas_signal_calls(signal_call_id)`
  (migration 080) ON DELETE RESTRICT — never silently lose a tracked
  portfolio entry when the upstream call row is deleted.
- `cell_id` references `atlas.atlas_cell_definitions(cell_id)` (migration
  080) ON DELETE RESTRICT — same rationale.
- `user_id` and `instrument_id` are plain UUIDs (no FK). `user_id`
  targets `auth.users` which lives in a different Postgres schema owned
  by Supabase; we do NOT create a cross-schema FK to avoid coupling
  migrations to the auth schema lifecycle. `instrument_id` targets
  multiple instrument-master tables across stocks / etfs / mfs and is
  resolved at the application layer.

Enum references
---------------
Reuses `atlas_tenure` + `atlas_exit_reason` enums created by migration
080. Both are referenced with `create_type=False` — do NOT re-create.

Migration chain
---------------
Per eng review §1.5:
    080 (foundation) -> 082 (atlas_brief_cache)
                     -> 083 (atlas_ledger + view)
                     -> 084 (atlas_paper_portfolio + atlas_user_lots)

081 is tracked as a separate issue and may land out of order. When 081
lands, no re-pointing is needed for 084 — this migration depends only on
080's enums + table targets.

Revision ID: 084
Revises: 083
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    # Reference existing enums from migration 080. create_type=False — do
    # NOT re-create.
    tenure_enum = postgresql.ENUM(
        name="atlas_tenure",
        schema=_SCHEMA,
        create_type=False,
    )
    exit_reason_enum = postgresql.ENUM(
        name="atlas_exit_reason",
        schema=_SCHEMA,
        create_type=False,
    )

    # -----------------------------------------------------------------
    # atlas_paper_portfolio — per-user paper portfolio tracking every
    # POSITIVE signal trigger (E1).
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_paper_portfolio",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # user_id — Supabase auth.users.id. Stored as plain UUID (no FK)
        # because auth schema is owned by Supabase, not atlas migrations.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "signal_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_signal_calls.signal_call_id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "cell_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_cell_definitions.cell_id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column("tenure", tenure_enum, nullable=False),
        # entry_date — T+1 open per CEO plan §E1 (writer fills the value).
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 4), nullable=False),
        # exit_* columns populate when the cell exit fires.
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("exit_reason", exit_reason_enum, nullable=True),
        # excess_return — net excess vs benchmark at exit (computed by the
        # ledger writer; Numeric(10, 4) for 4dp precision per
        # financial-domain rules).
        sa.Column("excess_return", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "instrument_id",
            "cell_id",
            "tenure",
            "entry_date",
            name="uq_atlas_paper_portfolio_user_inst_cell_tenure_date",
        ),
        schema=_SCHEMA,
    )

    # Partial index — "open positions for user X" hot read path. Per
    # CONTEXT.md signal_call_id cadence section + eng review §1.3.
    op.execute(
        f"""
        CREATE INDEX ix_atlas_paper_portfolio_user_open
        ON {_SCHEMA}.atlas_paper_portfolio (user_id)
        WHERE exit_date IS NULL
        """
    )

    # Index on signal_call_id — for cell-exit cascade queries (when a
    # signal_call exits, find every paper-portfolio row that referenced
    # it and write the exit fields).
    op.create_index(
        "ix_atlas_paper_portfolio_signal_call_id",
        "atlas_paper_portfolio",
        ["signal_call_id"],
        schema=_SCHEMA,
    )

    # Index on entry_date — for chronological / daily-batch queries.
    op.create_index(
        "ix_atlas_paper_portfolio_entry_date",
        "atlas_paper_portfolio",
        ["entry_date"],
        schema=_SCHEMA,
    )

    # Index on exit_date — for "recently closed" queries (e.g. ledger
    # daily roll-up).
    op.create_index(
        "ix_atlas_paper_portfolio_exit_date",
        "atlas_paper_portfolio",
        ["exit_date"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # atlas_user_lots — minimal real-holding entry (E3 deferred to v7)
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_user_lots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_date", sa.Date(), nullable=False),
        # Numeric for both quantity + cost_basis: quantity for fractional
        # MF units, cost_basis as ₹ per unit (no float on money).
        sa.Column("quantity", sa.Numeric(20, 4), nullable=False),
        sa.Column("cost_basis", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "is_realized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("realized_date", sa.Date(), nullable=True),
        sa.Column("realized_price", sa.Numeric(20, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        schema=_SCHEMA,
    )

    # Composite index — fast (user_id, instrument_id) lookup per CEO plan
    # §E1 archived E3-v7 section ("show me all lots of TCS this user
    # holds").
    op.create_index(
        "ix_atlas_user_lots_user_instrument",
        "atlas_user_lots",
        ["user_id", "instrument_id"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # Row-Level Security — per-user isolation on both tables.
    # -----------------------------------------------------------------
    # Service-role connections bypass RLS (they connect as postgres /
    # service_role). User-facing role gets a single FOR ALL policy that
    # checks the JWT sub claim against user_id.
    op.execute(f"ALTER TABLE {_SCHEMA}.atlas_paper_portfolio ENABLE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY paper_portfolio_user_isolation
        ON {_SCHEMA}.atlas_paper_portfolio
        FOR ALL
        USING (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')::uuid)
        WITH CHECK (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')::uuid);
        """
    )

    op.execute(f"ALTER TABLE {_SCHEMA}.atlas_user_lots ENABLE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY user_lots_user_isolation
        ON {_SCHEMA}.atlas_user_lots
        FOR ALL
        USING (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')::uuid)
        WITH CHECK (user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')::uuid);
        """
    )


def downgrade() -> None:
    """Reverse upgrade. Order matters:

    1. DROP POLICY (must come before DISABLE / DROP TABLE — policies are
       attached to the table).
    2. DISABLE ROW LEVEL SECURITY.
    3. DROP indexes (partial index via raw SQL; ordinary indexes via
       drop_index).
    4. DROP tables.

    Does NOT drop the atlas_tenure or atlas_exit_reason enums — both are
    owned by migration 080.
    """
    # 1. Drop policies first.
    op.execute(
        f"DROP POLICY IF EXISTS user_lots_user_isolation ON {_SCHEMA}.atlas_user_lots;"
    )
    op.execute(
        f"DROP POLICY IF EXISTS paper_portfolio_user_isolation ON {_SCHEMA}.atlas_paper_portfolio;"
    )

    # 2. Disable RLS.
    op.execute(f"ALTER TABLE {_SCHEMA}.atlas_user_lots DISABLE ROW LEVEL SECURITY;")
    op.execute(
        f"ALTER TABLE {_SCHEMA}.atlas_paper_portfolio DISABLE ROW LEVEL SECURITY;"
    )

    # 3a. Drop atlas_user_lots indexes.
    op.drop_index(
        "ix_atlas_user_lots_user_instrument",
        "atlas_user_lots",
        schema=_SCHEMA,
    )

    # 3b. Drop atlas_paper_portfolio indexes.
    op.drop_index(
        "ix_atlas_paper_portfolio_exit_date",
        "atlas_paper_portfolio",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_paper_portfolio_entry_date",
        "atlas_paper_portfolio",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_paper_portfolio_signal_call_id",
        "atlas_paper_portfolio",
        schema=_SCHEMA,
    )
    # Partial index created via raw SQL — drop via raw SQL too.
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_paper_portfolio_user_open"
    )

    # 4. Drop tables.
    op.drop_table("atlas_user_lots", schema=_SCHEMA)
    op.drop_table("atlas_paper_portfolio", schema=_SCHEMA)
