"""v6 — ETF + MF tables (Phase 8).

Adds the Phase 8 schema:

- ``atlas_etf_signal_calls`` — ETF cell-matrix analog to
  ``atlas_signal_calls`` (full scorecard + matrix per CEO plan §08; same
  trigger-only cadence per CONTEXT.md signal_call_id; same 3-state action
  vocab per R1 post-adversarial revision).

- ``atlas_mf_recommendation_daily`` — per-fund daily quartile + consistency
  per CEO plan §09 MF locked methodology (peer-quartile, monthly cadence,
  consistency window). One row per fund per day.

- ``atlas_mf_switch_rules`` — configuration table for the MF SWITCH
  selection rule per /grill Q11 D5: same-category only; switch when current
  fund is Q3/Q4 AND a Q1/Q2 fund with ≥6mo consistency exists; tie-break
  on lowest expense ratio.

Action vocabulary
-----------------
- ETF uses the same 3-state cell action enum (``atlas_cell_action`` —
  POSITIVE/NEUTRAL/NEGATIVE) as stocks per R1 post-adversarial revision.
  ETFs behave like stocks (price-driven, single instrument, capable of
  the same cell pattern), so they share the cell matrix vocabulary.

- MF uses its own action set (``atlas_mf_recommendation`` —
  BUY/HOLD/SWITCH/AVOID) per CEO plan §09 lock. MF have a fundamentally
  different ranking framework (peer-quartile across category, not a per-
  instrument cell matrix), so the action vocabulary is intentionally
  different. SWITCH has no analog in the stock/ETF cell vocabulary.

Enum references
---------------
Reuses the following enums created by migration 080 (referenced with
``create_type=False`` — do NOT re-create):
- ``atlas_cap_tier``
- ``atlas_tenure``
- ``atlas_cell_action``
- ``atlas_regime_state``
- ``atlas_exit_reason``

Creates the following NEW enums (this migration owns them — drop on
downgrade):
- ``atlas_etf_sub_category`` (broad_market, sectoral)
- ``atlas_mf_quartile`` (Q1..Q4)
- ``atlas_mf_recommendation`` (BUY, HOLD, SWITCH, AVOID)

FK target schemas
-----------------
- ``cell_id`` on ETF signal calls references
  ``atlas.atlas_cell_definitions(cell_id)`` (migration 080) ON DELETE
  RESTRICT — never silently lose an ETF call when the upstream cell is
  deleted (cells get deprecated, not deleted, in steady state).
- ``etf_instrument_id`` / ``mf_instrument_id`` / ``switch_target_iid``
  are plain UUIDs (no FK). They target instrument-master tables across
  ETF / MF schemas resolved at the application layer (same convention
  as ``instrument_id`` in 080 and 084).

Migration chain
---------------
Per the v6 issue queue:
    080 (foundation) -> 082 (brief_cache)
                     -> 083 (ledger)
                     -> 084 (paper_portfolio + user_lots)
                     -> 085 (ETF + MF — this migration)

081 (atlas_cell_walkforward_runs) is tracked as a separate issue and may
land out of order. 085 does NOT depend on 081.

Revision ID: 085
Revises: 084
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"

# ---------------------------------------------------------------------------
# NEW enums owned by this migration (085 creates + drops).
# ---------------------------------------------------------------------------

ETF_SUB_CATEGORY = ("broad_market", "sectoral")
MF_QUARTILE = ("Q1", "Q2", "Q3", "Q4")
MF_RECOMMENDATION = ("BUY", "HOLD", "SWITCH", "AVOID")


def upgrade() -> None:
    bind = op.get_bind()

    # NEW enum types — created once, referenced by columns below.
    for name, values in (
        ("atlas_etf_sub_category", ETF_SUB_CATEGORY),
        ("atlas_mf_quartile", MF_QUARTILE),
        ("atlas_mf_recommendation", MF_RECOMMENDATION),
    ):
        postgresql.ENUM(*values, name=name, schema=_SCHEMA).create(
            bind, checkfirst=True
        )

    # Reference existing enums from migration 080. create_type=False — do
    # NOT re-create.
    cap_tier_enum = postgresql.ENUM(
        name="atlas_cap_tier", schema=_SCHEMA, create_type=False
    )
    tenure_enum = postgresql.ENUM(
        name="atlas_tenure", schema=_SCHEMA, create_type=False
    )
    cell_action_enum = postgresql.ENUM(
        name="atlas_cell_action", schema=_SCHEMA, create_type=False
    )
    regime_state_enum = postgresql.ENUM(
        name="atlas_regime_state", schema=_SCHEMA, create_type=False
    )
    exit_reason_enum = postgresql.ENUM(
        name="atlas_exit_reason", schema=_SCHEMA, create_type=False
    )

    # Reference NEW enums for column definitions. create_type=False — they
    # were just created above by ENUM(...).create(bind).
    etf_sub_category_enum = postgresql.ENUM(
        name="atlas_etf_sub_category", schema=_SCHEMA, create_type=False
    )
    mf_quartile_enum = postgresql.ENUM(
        name="atlas_mf_quartile", schema=_SCHEMA, create_type=False
    )
    mf_recommendation_enum = postgresql.ENUM(
        name="atlas_mf_recommendation", schema=_SCHEMA, create_type=False
    )

    # -----------------------------------------------------------------
    # atlas_etf_signal_calls — ETF analog to atlas_signal_calls.
    # Trigger-only cadence per CONTEXT.md (signal_call_id).
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_etf_signal_calls",
        sa.Column(
            "etf_signal_call_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("etf_instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("etf_sub_category", etf_sub_category_enum, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "cell_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_cell_definitions.cell_id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        # cap_tier_at_trigger denormalized for the composite index (mirrors
        # 080 signal_calls pattern). For ETFs, cap_tier reflects the
        # underlying basket's dominant tier at trigger time.
        sa.Column("cap_tier_at_trigger", cap_tier_enum, nullable=False),
        sa.Column("tenure", tenure_enum, nullable=False),
        sa.Column("action", cell_action_enum, nullable=False),
        sa.Column("confidence_unconditional", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_regime_conditional", sa.Numeric(5, 4), nullable=True),
        sa.Column("regime_state_at_call", regime_state_enum, nullable=False),
        sa.Column(
            "cell_active_in_regime",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("stable_features", postgresql.JSONB(), nullable=True),
        sa.Column("predicted_excess", sa.Numeric(10, 6), nullable=True),
        # Exit tracking — same semantics as 080 atlas_signal_calls.
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("exit_reason", exit_reason_enum, nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        schema=_SCHEMA,
    )

    # Composite index — mirrors 080 signal_calls (/v1/today/buys hot path).
    op.create_index(
        "ix_atlas_etf_signal_calls_date_action_tier",
        "atlas_etf_signal_calls",
        ["date", "action", "cap_tier_at_trigger"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_etf_signal_calls_iid_date",
        "atlas_etf_signal_calls",
        ["etf_instrument_id", "date"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_etf_signal_calls_cell_date",
        "atlas_etf_signal_calls",
        ["cell_id", "date"],
        schema=_SCHEMA,
    )
    # Open-positions partial index — mirrors 080 atlas_signal_calls_open.
    op.execute(
        f"""
        CREATE INDEX ix_atlas_etf_signal_calls_open
        ON {_SCHEMA}.atlas_etf_signal_calls (etf_instrument_id, cell_id, tenure)
        WHERE exit_date IS NULL
        """
    )

    # -----------------------------------------------------------------
    # atlas_mf_recommendation_daily — per-fund quartile + consistency.
    # Locked methodology per CEO plan §09 (peer-quartile, monthly cadence).
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_mf_recommendation_daily",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("mf_instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("peer_quartile", mf_quartile_enum, nullable=False),
        sa.Column(
            "consistency_months",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("nav", sa.Numeric(20, 4), nullable=False),
        # expense_ratio used as tie-break in SWITCH selection per
        # /grill Q11 D5; nullable because data feed may lag for newly
        # listed funds.
        sa.Column("expense_ratio", sa.Numeric(6, 4), nullable=True),
        sa.Column("recommendation", mf_recommendation_enum, nullable=False),
        # If recommendation='SWITCH', this is the target fund identified by
        # the SWITCH-selection routine per atlas_mf_switch_rules.
        sa.Column(
            "switch_target_iid", postgresql.UUID(as_uuid=True), nullable=True
        ),
        # NAV publication can lag the run date — track separately.
        sa.Column("data_as_of", sa.Date(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "date",
            "mf_instrument_id",
            name="uq_atlas_mf_recommendation_daily_date_iid",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_mf_recommendation_daily_date_reco",
        "atlas_mf_recommendation_daily",
        ["date", "recommendation"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_mf_recommendation_daily_iid_date",
        "atlas_mf_recommendation_daily",
        ["mf_instrument_id", "date"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_mf_recommendation_daily_category_date",
        "atlas_mf_recommendation_daily",
        ["category", "date"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # atlas_mf_switch_rules — SWITCH selection configuration.
    # Per /grill Q11 D5: same-category only; SWITCH when current is at/
    # below current_quartile_floor AND a fund at/above
    # target_quartile_ceiling exists with ≥ min_target_consistency_months
    # of consistency; tie-break on lowest expense ratio.
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_mf_switch_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("current_quartile_floor", mf_quartile_enum, nullable=False),
        sa.Column("target_quartile_ceiling", mf_quartile_enum, nullable=False),
        sa.Column(
            "min_target_consistency_months",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("6"),
        ),
        sa.Column(
            "tie_break",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'lowest_expense_ratio'"),
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        schema=_SCHEMA,
    )

    # Partial unique constraint — at most ONE active rule per category.
    # Multiple historical (active=false) rows permitted for audit trail.
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_atlas_mf_switch_rules_category_active
        ON {_SCHEMA}.atlas_mf_switch_rules (category)
        WHERE active = TRUE
        """
    )


def downgrade() -> None:
    """Reverse upgrade. Drop order:

    1. Partial / unique indexes created via raw SQL.
    2. Named indexes via op.drop_index.
    3. Tables in FK-dependency order (none of these tables FK to each
       other; only atlas_etf_signal_calls FKs out to
       atlas.atlas_cell_definitions from migration 080).
    4. NEW enums owned by this migration.

    Does NOT drop the existing enums owned by migration 080
    (atlas_cap_tier, atlas_tenure, atlas_cell_action, atlas_regime_state,
    atlas_exit_reason).
    """
    # 1a. Partial index on atlas_mf_switch_rules — created via raw SQL.
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.uq_atlas_mf_switch_rules_category_active"
    )
    # 1b. Partial open-positions index on atlas_etf_signal_calls — raw SQL.
    op.execute(f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_etf_signal_calls_open")

    # 2. Named indexes — atlas_mf_recommendation_daily.
    op.drop_index(
        "ix_atlas_mf_recommendation_daily_category_date",
        "atlas_mf_recommendation_daily",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_mf_recommendation_daily_iid_date",
        "atlas_mf_recommendation_daily",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_mf_recommendation_daily_date_reco",
        "atlas_mf_recommendation_daily",
        schema=_SCHEMA,
    )

    # 2b. Named indexes — atlas_etf_signal_calls.
    op.drop_index(
        "ix_atlas_etf_signal_calls_cell_date",
        "atlas_etf_signal_calls",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_etf_signal_calls_iid_date",
        "atlas_etf_signal_calls",
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_atlas_etf_signal_calls_date_action_tier",
        "atlas_etf_signal_calls",
        schema=_SCHEMA,
    )

    # 3. Drop tables.
    op.drop_table("atlas_mf_switch_rules", schema=_SCHEMA)
    op.drop_table("atlas_mf_recommendation_daily", schema=_SCHEMA)
    op.drop_table("atlas_etf_signal_calls", schema=_SCHEMA)

    # 4. Drop NEW enums owned by this migration. Do NOT drop enums owned
    # by 080.
    bind = op.get_bind()
    for name in (
        "atlas_mf_recommendation",
        "atlas_mf_quartile",
        "atlas_etf_sub_category",
    ):
        postgresql.ENUM(name=name, schema=_SCHEMA).drop(bind, checkfirst=True)
