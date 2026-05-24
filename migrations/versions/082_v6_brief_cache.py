"""v6 — atlas_brief_cache for E2 per-instrument LLM brief storage.

Adds the brief cache table per CONTEXT.md "Brief cache invalidation"
section + eng review §1.3. The cache stores SP07 Hermes-generated
briefs keyed by (instrument_id, date, action, cell_id) so that the
same (instrument, date, action, cell) tuple does not regenerate.

Invalidation contract (CONTEXT.md):
- 24h TTL via `valid_until` (writer sets to `generated_at + interval '24h'`)
- Corporate action invalidates: `invalidated_at` + `invalidated_by_corp_action_id`
- Cell re-fire invalidates: `invalidated_at` set on the prior row, new row inserted

Migration chain note
--------------------
Per eng review §1.5, the logical sequence is:
  080 (foundation) → 081 (atlas_cell_walkforward_runs + atlas_friction_params)
                   → 082 (atlas_brief_cache)

081 is tracked as a separate issue and may land out of order. This
migration uses `down_revision = "080"` so it links cleanly on top of
the foundation. When 081 lands, its `down_revision` is "080" and 082's
`down_revision` will need to be re-pointed to "081" via a single-line
re-revision (no schema changes — just chain linearization).

Revision ID: 082
Revises: 080
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "082"
down_revision = "080"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    # Reference the existing atlas_cell_action enum created by migration 080.
    # create_type=False — do NOT re-create the enum.
    cell_action_enum = postgresql.ENUM(
        name="atlas_cell_action",
        schema=_SCHEMA,
        create_type=False,
    )

    # -----------------------------------------------------------------
    # atlas_brief_cache — per-(instrument, date, action, cell) LLM briefs
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_brief_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # instrument_id is conceptually FK to de_instruments but that table
        # lives in a separate schema/scope — leave as plain UUID NOT NULL.
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("action", cell_action_enum, nullable=False),
        sa.Column(
            "cell_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_cell_definitions.cell_id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        # signal_call_id is nullable: a brief may pre-exist (e.g. composed
        # for a regime/cell update) before any specific signal_call fires.
        sa.Column(
            "signal_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_signal_calls.signal_call_id", ondelete="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column("brief_text", sa.Text(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # valid_until = generated_at + interval '24 hours' (writer-enforced).
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        # invalidated_at — set when a corp action or cell re-fire makes the
        # cached brief stale. Read path filters WHERE invalidated_at IS NULL.
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        # Links to de_corporate_actions when invalidation cause is corp action.
        sa.Column(
            "invalidated_by_corp_action_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # Composite invalidation key per CONTEXT.md brief cache section:
        # one cached brief per (instrument, date, action, cell) tuple.
        sa.UniqueConstraint(
            "instrument_id",
            "date",
            "action",
            "cell_id",
            name="uq_atlas_brief_cache_iid_date_action_cell",
        ),
        schema=_SCHEMA,
    )

    # TTL cleanup index — supports the nightly cleanup cron that prunes
    # rows where valid_until < NOW().
    op.create_index(
        "ix_atlas_brief_cache_valid_until",
        "atlas_brief_cache",
        ["valid_until"],
        schema=_SCHEMA,
    )

    # Invalidation lookup — when a signal_call exits/flips, find all
    # cached briefs referencing it and invalidate them.
    op.create_index(
        "ix_atlas_brief_cache_signal_call_id",
        "atlas_brief_cache",
        ["signal_call_id"],
        schema=_SCHEMA,
    )

    # Hot read path — fast lookup of the current (non-invalidated) brief
    # for a given (instrument, date, action). Partial index so it stays
    # compact as invalidated rows accumulate.
    op.execute(
        f"""
        CREATE INDEX ix_atlas_brief_cache_active
        ON {_SCHEMA}.atlas_brief_cache (instrument_id, date, action)
        WHERE invalidated_at IS NULL
        """
    )


def downgrade() -> None:
    """Reverse upgrade. Drop indexes first (partial index via raw SQL),
    then the table — does NOT drop the atlas_cell_action enum (owned by
    migration 080).
    """
    op.execute(f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_brief_cache_active")
    op.drop_index(
        "ix_atlas_brief_cache_signal_call_id",
        "atlas_brief_cache",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_brief_cache_valid_until",
        "atlas_brief_cache",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_brief_cache", schema=_SCHEMA)
