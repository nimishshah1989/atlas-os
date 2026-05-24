"""v6 — atlas_ledger + atlas_ledger_public view (agent ACL surface).

Adds the live ledger table for realized excess + drift Z per cell, plus
the read-only view `atlas_ledger_public` exposed to the
`atlas_agent_readonly` Postgres role per CONTEXT.md "atlas_agent_readonly
ACL" + "Cell deprecation (REVISED post adversarial review)" + "Drift
detector parameters" sections.

Design contract
---------------
- `atlas_ledger` is the live ledger: realized excess return + drift Z per
  signal_call. Written by:
    * Phase 5 ledger writer cron — on signal_call exit, computes
      realized_excess vs benchmark net of friction and inserts a row.
    * Drift detector cron — nightly, updates `drift_z` + `status` for
      each cell aggregate over the rolling window.

- `atlas_ledger_public` is a read-only view that exposes ONLY the columns
  safe for LLM agents to surface in user briefs:
      signal_call_id, realized_excess, realized_at

  The `drift_z` and `status` columns are deliberately hidden from agents:
  they are internal monitoring signals (per CONTEXT.md "Drift detector
  parameters" — Z-score, deprecation status). Surfacing "this cell is
  showing Z=2.7 drift, position will exit soon" in a brief would leak
  internal operational state to end users and contaminate the SEBI-safe
  output surface.

- GRANT is conditional on the role existing (DO block) so the migration
  is idempotent across environments where `atlas_agent_readonly` may not
  yet be provisioned. The base table `atlas_ledger` is NEVER granted to
  the agent role — only the view.

Migration chain note
--------------------
Per eng review §1.5 the logical sequence is:
  080 (foundation) -> 081 (atlas_cell_walkforward_runs + atlas_friction_params)
                   -> 082 (atlas_brief_cache)
                   -> 083 (atlas_ledger + view)

081 is tracked as a separate issue and may land out of order. 082's
`down_revision` is "080"; 083's `down_revision` is "082". When 081 lands
its chain link will be re-pointed by a follow-up.

Revision ID: 083
Revises: 082
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    # Reference the existing atlas_drift_status enum created by migration 080.
    # create_type=False — do NOT re-create the enum.
    drift_status_enum = postgresql.ENUM(
        name="atlas_drift_status",
        schema=_SCHEMA,
        create_type=False,
    )

    # -----------------------------------------------------------------
    # atlas_ledger — live realized excess + drift Z per signal_call
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_ledger",
        sa.Column(
            "signal_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_signal_calls.signal_call_id", ondelete="RESTRICT"
            ),
            primary_key=True,
        ),
        # realized_excess — net excess vs benchmark after friction (bps/pct
        # depending on writer contract; stored as Numeric(10, 4) to preserve
        # 4dp precision per global financial-domain rules).
        sa.Column("realized_excess", sa.Numeric(10, 4), nullable=False),
        sa.Column("realized_at", sa.DateTime(timezone=True), nullable=False),
        # drift_z — rolling Z-score from the drift detector cron. Nullable
        # because freshly-inserted rows have no Z yet until the next nightly
        # detector run aggregates the cell.
        sa.Column("drift_z", sa.Numeric(8, 4), nullable=True),
        # status — drift detector verdict: healthy / drift_warn / deprecated.
        # Enum owned by 080; this column merely references it.
        sa.Column("status", drift_status_enum, nullable=False),
        # provenance_log_id — FK target (atlas_provenance_log) ships in a
        # later issue; nullable + no FK constraint for now. Becomes FK in
        # the migration that adds the provenance log table.
        sa.Column(
            "provenance_log_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
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

    # Index on realized_at — supports drift detector window queries that
    # aggregate the ledger over rolling N-day windows.
    op.create_index(
        "ix_atlas_ledger_realized_at",
        "atlas_ledger",
        ["realized_at"],
        schema=_SCHEMA,
    )

    # Index on status — supports "all drift_warn cells" / "all deprecated
    # cells" lookups from the drift detector + admin UI.
    op.create_index(
        "ix_atlas_ledger_status",
        "atlas_ledger",
        ["status"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # atlas_ledger_public — read-only view for atlas_agent_readonly role
    # -----------------------------------------------------------------
    # Hides drift_z + status (internal monitoring; not for LLM agents to
    # surface in user briefs per CONTEXT.md agent ACL).
    op.execute(
        f"""
        CREATE VIEW {_SCHEMA}.atlas_ledger_public AS
        SELECT signal_call_id, realized_excess, realized_at
        FROM {_SCHEMA}.atlas_ledger
        """
    )

    # Conditional GRANT — only if the atlas_agent_readonly role exists.
    # The role is provisioned by infrastructure (separate from migrations);
    # this DO block keeps the migration idempotent across environments where
    # the role may not yet exist (local dev, fresh staging).
    # DO NOT grant SELECT on the base atlas_ledger to the agent role —
    # only the view. This is the ACL surface boundary.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_agent_readonly') THEN
                EXECUTE 'GRANT SELECT ON {_SCHEMA}.atlas_ledger_public TO atlas_agent_readonly';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Reverse upgrade. Order matters:
    1. REVOKE (conditional — only if role exists)
    2. DROP VIEW (must come before base table — view depends on it)
    3. DROP indexes
    4. DROP TABLE

    Does NOT drop the atlas_drift_status enum (owned by migration 080).
    """
    # 1. Conditional REVOKE — survives missing role.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_agent_readonly') THEN
                EXECUTE 'REVOKE SELECT ON {_SCHEMA}.atlas_ledger_public FROM atlas_agent_readonly';
            END IF;
        END
        $$;
        """
    )

    # 2. DROP VIEW before base table — Postgres rejects dropping a table
    # that has dependent views otherwise.
    op.execute(f"DROP VIEW IF EXISTS {_SCHEMA}.atlas_ledger_public")

    # 3. Drop indexes.
    op.drop_index(
        "ix_atlas_ledger_status",
        "atlas_ledger",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_ledger_realized_at",
        "atlas_ledger",
        schema=_SCHEMA,
    )

    # 4. Drop the base table (FK to atlas_signal_calls handled by
    # ondelete=RESTRICT on the FK definition — no extra step needed).
    op.drop_table("atlas_ledger", schema=_SCHEMA)
