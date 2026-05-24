"""v6 — atlas_drift_event_log (G5 audit trail).

Adds the write-once audit row per drift event per CONTEXT.md "Cell
deprecation (REVISED post adversarial review)" + "Drift detector
parameters" sections (post-adversarial review G5 + Gemini).

Every drift evaluation that crosses threshold writes a row. Maintainer
actions (clear_warn, set_deprecated) also write rows. The row is the
permanent record SEBI inspection asks for: "show me, for cell X, every
time you flagged drift, what Z it crossed at, what window you measured
over, who acted, and what run produced the signal."

Tables
------
- ``atlas_drift_event_log`` — write-once audit log. UPDATE and DELETE
  rejected by a plpgsql trigger. Indexed by (cell_id, ts DESC),
  (ts DESC), and (action, ts DESC).

New enum
--------
- ``atlas_drift_action`` — ('flag', 'clear', 'deprecate').
  Owned by this migration (created + dropped here).

  - 'flag'       — cron set drift_warn (system action)
  - 'clear'      — maintainer cleared a false-positive
  - 'deprecate'  — maintainer set deprecated_at

Reused enum
-----------
- ``atlas_drift_status`` from migration 080 (referenced with
  ``create_type=False`` — do NOT re-create, do NOT drop on downgrade).
  Used for ``status_before`` and ``status_after``.

FK relationships
----------------
- ``cell_id`` → ``atlas.atlas_cell_definitions(cell_id)``
  ON DELETE RESTRICT. A cell with audit rows MUST NOT be deletable —
  the audit trail outlives the cell definition.

- ``provenance_log_id`` → ``atlas.atlas_provenance_log(run_id)``
  ON DELETE SET NULL. A provenance row may be purged independently
  (e.g. retention sweep); the audit event survives with the link
  nulled.

Write-once enforcement
----------------------
A plpgsql trigger function ``atlas.deny_update_delete_drift_event()``
raises an exception on any UPDATE or DELETE. The trigger fires BEFORE
UPDATE OR DELETE on each row, so the operation is rejected before any
write side-effect. INSERTs are the only valid mutation. Same pattern
as ``atlas_provenance_log`` (migration 087).

CHECK constraints
-----------------
- ``realized_window_start <= realized_window_end`` — catches inverted
  windows at write time.
- ``n_realized >= 0`` — defensive guard against bad upstream counts.

Migration chain
---------------
    080 (foundation) -> 082 (brief_cache)
                     -> 083 (ledger)
                     -> 084 (paper_portfolio + user_lots)
                     -> 085 (ETF + MF)
                     -> 086 (macro overlay)
                     -> 087 (provenance log)
                     -> 088 (drift event log — this migration)

Revision ID: 088
Revises: 087
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"

# ---------------------------------------------------------------------------
# NEW enum owned by this migration (088 creates + drops).
# ---------------------------------------------------------------------------

DRIFT_ACTION = ("flag", "clear", "deprecate")


def upgrade() -> None:
    bind = op.get_bind()

    # -----------------------------------------------------------------
    # NEW enum — atlas_drift_action.
    # -----------------------------------------------------------------
    postgresql.ENUM(*DRIFT_ACTION, name="atlas_drift_action", schema=_SCHEMA).create(
        bind, checkfirst=True
    )

    # Reference existing enum from migration 080. create_type=False —
    # do NOT re-create.
    drift_status_enum = postgresql.ENUM(
        name="atlas_drift_status", schema=_SCHEMA, create_type=False
    )

    # Reference the NEW enum for column definitions. create_type=False —
    # it was just created above by ENUM(...).create(bind).
    drift_action_enum = postgresql.ENUM(
        name="atlas_drift_action", schema=_SCHEMA, create_type=False
    )

    # -----------------------------------------------------------------
    # atlas_drift_event_log — write-once audit log.
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_drift_event_log",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cell_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_cell_definitions.cell_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # Drift Z-score at the time of event. Numeric for exact decimal
        # storage — never Float for any model output that audits depend on.
        sa.Column("z_score", sa.Numeric(8, 4), nullable=False),
        # Rolling window the Z was computed over. Inclusive on both ends.
        sa.Column("realized_window_start", sa.Date(), nullable=False),
        sa.Column("realized_window_end", sa.Date(), nullable=False),
        # Cell's friction-adjusted locked excess and bootstrap SD across
        # walk-forward windows (per CONTEXT.md σ_predicted source).
        sa.Column("predicted_excess", sa.Numeric(10, 6), nullable=False),
        sa.Column("sigma_predicted", sa.Numeric(10, 6), nullable=False),
        sa.Column("n_realized", sa.Integer(), nullable=False),
        # Drift state transition — both reference the 080-owned enum.
        sa.Column("status_before", drift_status_enum, nullable=False),
        sa.Column("status_after", drift_status_enum, nullable=False),
        # Action vocabulary: 'flag' | 'clear' | 'deprecate'.
        sa.Column("action", drift_action_enum, nullable=False),
        # 'system' for cron-driven events; opaque user_id text for
        # maintainer-driven events (clear, deprecate).
        sa.Column(
            "actor",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'system'"),
        ),
        # Link to the run that produced the realized data. SET NULL on
        # provenance delete — the audit row survives.
        sa.Column(
            "provenance_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_provenance_log.run_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        # CHECKs — catch malformed inputs at write time.
        sa.CheckConstraint(
            "realized_window_start <= realized_window_end",
            name="ck_atlas_drift_event_log_window_order",
        ),
        sa.CheckConstraint(
            "n_realized >= 0",
            name="ck_atlas_drift_event_log_n_realized_non_negative",
        ),
        schema=_SCHEMA,
    )

    # Indexes — per-cell history + chronological + per-action queries.
    op.create_index(
        "ix_atlas_drift_event_log_cell_id_ts_desc",
        "atlas_drift_event_log",
        ["cell_id", sa.text("ts DESC")],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_drift_event_log_ts_desc",
        "atlas_drift_event_log",
        [sa.text("ts DESC")],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_drift_event_log_action_ts_desc",
        "atlas_drift_event_log",
        ["action", sa.text("ts DESC")],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # Write-once enforcement — plpgsql trigger denying UPDATE + DELETE.
    # Same pattern as 087 (atlas_provenance_log).
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION atlas.deny_update_delete_drift_event()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'atlas_drift_event_log is write-once; UPDATE/DELETE not permitted (tg_op=%)',
                TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER deny_update_delete_atlas_drift_event_log
        BEFORE UPDATE OR DELETE ON atlas.atlas_drift_event_log
        FOR EACH ROW EXECUTE FUNCTION atlas.deny_update_delete_drift_event();
        """
    )


def downgrade() -> None:
    """Reverse upgrade. Drop order:

    1. Trigger on the target table.
    2. plpgsql function backing the trigger.
    3. Named indexes.
    4. The atlas_drift_event_log table itself (drops embedded FKs and
       CHECK constraints with it).
    5. The atlas_drift_action enum (owned by this migration).
       Do NOT drop atlas_drift_status — owned by migration 080.
    """
    # 1. Drop trigger on atlas_drift_event_log.
    op.execute(
        "DROP TRIGGER IF EXISTS deny_update_delete_atlas_drift_event_log "
        "ON atlas.atlas_drift_event_log;"
    )

    # 2. Drop plpgsql function.
    op.execute("DROP FUNCTION IF EXISTS atlas.deny_update_delete_drift_event();")

    # 3. Drop indexes.
    op.drop_index(
        "ix_atlas_drift_event_log_action_ts_desc",
        "atlas_drift_event_log",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_drift_event_log_ts_desc",
        "atlas_drift_event_log",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_drift_event_log_cell_id_ts_desc",
        "atlas_drift_event_log",
        schema=_SCHEMA,
    )

    # 4. Drop the table — embedded FKs and CHECK constraints go with it.
    op.drop_table("atlas_drift_event_log", schema=_SCHEMA)

    # 5. Drop NEW enum owned by this migration. Do NOT drop
    # atlas_drift_status — owned by 080.
    bind = op.get_bind()
    postgresql.ENUM(name="atlas_drift_action", schema=_SCHEMA).drop(
        bind, checkfirst=True
    )
