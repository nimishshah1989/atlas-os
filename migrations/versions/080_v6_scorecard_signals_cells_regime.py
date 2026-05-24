"""v6 — atlas_scorecard_daily + atlas_signal_calls + atlas_cell_definitions + atlas_regime_daily.

First v6 migration on the existing 079 chain (Path A per /grill-with-docs
Q10). Adds the four foundation tables for v6 data model + the canonical
v6 enum types.

Action vocabulary is **3 cell states** (POSITIVE / NEUTRAL / NEGATIVE)
per R1 post-adversarial revision. Display labels (BUY/ACCUMULATE/HOLD/
WATCH/AVOID/SELL) are rendered in the API layer based on user ownership,
NOT validated as separate cells.

Schema source: eng review §1.3 + CONTEXT.md (signal_call_id, cell
deprecation, rule_dsl shape, regime classifier, 24-framework discovery).

Revision ID: 080
Revises: 079
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"

# ---------------------------------------------------------------------------
# v6 canonical enums
# ---------------------------------------------------------------------------

CAP_TIER = ("Small", "Mid", "Large")
FAMILY_STATE = ("R", "A", "G")
CELL_ACTION = ("POSITIVE", "NEUTRAL", "NEGATIVE")
TENURE = ("1m", "3m", "6m", "12m")
REGIME_STATE = ("Risk-On", "Elevated", "Below-Trend", "Risk-Off")
DRIFT_STATUS = ("healthy", "drift_warn", "deprecated")
EXIT_REASON = (
    "tenure_expiry",
    "cell_flip_to_negative",
    "user_close",
    "delisting",
    "cell_deprecated",
)


def _create_enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, schema=_SCHEMA, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # Enum types — created once, referenced by columns
    for name, values in (
        ("atlas_cap_tier", CAP_TIER),
        ("atlas_family_state", FAMILY_STATE),
        ("atlas_cell_action", CELL_ACTION),
        ("atlas_tenure", TENURE),
        ("atlas_regime_state", REGIME_STATE),
        ("atlas_drift_status", DRIFT_STATUS),
        ("atlas_exit_reason", EXIT_REASON),
    ):
        postgresql.ENUM(*values, name=name, schema=_SCHEMA).create(bind, checkfirst=True)

    # -----------------------------------------------------------------
    # atlas_regime_daily — daily market regime state
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_regime_daily",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("date", sa.Date(), nullable=False, unique=True),
        sa.Column(
            "state",
            _create_enum("atlas_regime_state", REGIME_STATE),
            nullable=False,
        ),
        # Driver attributions (per CONTEXT.md regime classifier section)
        sa.Column("smallcap_rs_z", sa.Numeric(10, 4), nullable=True),
        sa.Column("breadth_pct_above_200dma", sa.Numeric(6, 4), nullable=True),
        sa.Column("vix_percentile", sa.Numeric(6, 4), nullable=True),
        sa.Column("cross_sectional_dispersion", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_regime_daily_date",
        "atlas_regime_daily",
        ["date"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # atlas_scorecard_daily — wide per-instrument scorecard (5-family R/A/G)
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_scorecard_daily",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "cap_tier",
            _create_enum("atlas_cap_tier", CAP_TIER),
            nullable=False,
        ),
        # 5-family R/A/G states — drive the scorecard card UI
        sa.Column(
            "family_trend",
            _create_enum("atlas_family_state", FAMILY_STATE),
            nullable=False,
        ),
        sa.Column(
            "family_volatility",
            _create_enum("atlas_family_state", FAMILY_STATE),
            nullable=False,
        ),
        sa.Column(
            "family_volume",
            _create_enum("atlas_family_state", FAMILY_STATE),
            nullable=False,
        ),
        sa.Column(
            "family_path",
            _create_enum("atlas_family_state", FAMILY_STATE),
            nullable=False,
        ),
        sa.Column(
            "family_sector",
            _create_enum("atlas_family_state", FAMILY_STATE),
            nullable=False,
        ),
        # Methodology-locked features (first-class columns for direct queryability)
        # Other features (per Phase 0.5g 24-framework discovery + library expansion)
        # live in features JSONB below.
        sa.Column("rs_residual_6m", sa.Numeric(12, 6), nullable=True),
        sa.Column("log_med_tv_60d", sa.Numeric(12, 6), nullable=True),
        sa.Column("realized_vol_60d", sa.Numeric(10, 6), nullable=True),
        sa.Column("formation_max_dd", sa.Numeric(8, 6), nullable=True),
        sa.Column("listing_age_days", sa.Integer(), nullable=True),
        sa.Column("log_price", sa.Numeric(10, 6), nullable=True),
        # Extended feature library — JSONB for dynamic feature additions
        # per CONTEXT.md "24-framework discovery model" + continuous
        # improvement workstream.
        sa.Column("features", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "data_completeness",
            sa.Numeric(4, 3),
            nullable=False,
            server_default=sa.text("1.000"),
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
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
        sa.UniqueConstraint(
            "date", "instrument_id", name="uq_atlas_scorecard_daily_date_iid"
        ),
        sa.CheckConstraint(
            "data_completeness BETWEEN 0 AND 1",
            name="ck_atlas_scorecard_daily_completeness_range",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_scorecard_daily_iid_date",
        "atlas_scorecard_daily",
        ["instrument_id", "date"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_scorecard_daily_date",
        "atlas_scorecard_daily",
        ["date"],
        schema=_SCHEMA,
    )

    # -----------------------------------------------------------------
    # atlas_cell_definitions — per-(cap_tier × action × tenure) rules
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_cell_definitions",
        sa.Column(
            "cell_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cap_tier",
            _create_enum("atlas_cap_tier", CAP_TIER),
            nullable=False,
        ),
        # action is POSITIVE / NEUTRAL / NEGATIVE per R1 collapse
        sa.Column(
            "action",
            _create_enum("atlas_cell_action", CELL_ACTION),
            nullable=False,
        ),
        sa.Column(
            "tenure",
            _create_enum("atlas_tenure", TENURE),
            nullable=False,
        ),
        # rule_dsl: Pydantic CellRule serialized as JSONB (validated on insert
        # via SQLAlchemy event listener — see atlas/decisions/ when wired up).
        sa.Column("rule_dsl", postgresql.JSONB(), nullable=False),
        # Methodology metrics (populated by atlas/discovery/ walk-forward run)
        sa.Column("confidence_unconditional", sa.Numeric(5, 4), nullable=True),
        sa.Column("friction_adjusted_excess", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "confidence_by_regime",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column("stable_features", postgresql.JSONB(), nullable=True),
        sa.Column(
            "methodology_lock_ref",
            sa.String(length=64),
            nullable=False,
            comment="SHA or date stamp of locking experiment",
        ),
        sa.Column("rule_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "drift_status",
            _create_enum("atlas_drift_status", DRIFT_STATUS),
            nullable=False,
            server_default="healthy",
        ),
        # walkforward_run_id FK added by migration 081 (atlas_cell_walkforward_runs)
        sa.Column(
            "walkforward_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "validated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "deprecated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        schema=_SCHEMA,
    )
    # Partial unique constraint: a (cap_tier, action, tenure) tuple can have
    # at most ONE active (non-deprecated) cell definition. Multiple
    # deprecated cells with the same key are permitted (historical archive).
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_atlas_cell_definitions_active
        ON {_SCHEMA}.atlas_cell_definitions (cap_tier, action, tenure)
        WHERE deprecated_at IS NULL
        """
    )

    # -----------------------------------------------------------------
    # atlas_signal_calls — tall event table (trigger-only per CONTEXT.md)
    # -----------------------------------------------------------------
    op.create_table(
        "atlas_signal_calls",
        sa.Column(
            "signal_call_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scorecard_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_scorecard_daily.id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "cell_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{_SCHEMA}.atlas_cell_definitions.cell_id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        # cap_tier_at_trigger denormalized for /v1/today/buys composite index
        # (per eng review §4 Finding 4.A). Per CONTEXT.md, exit semantics
        # use the cell rule, not today's cap_tier — so trigger-time tier is
        # the contract.
        sa.Column(
            "cap_tier_at_trigger",
            _create_enum("atlas_cap_tier", CAP_TIER),
            nullable=False,
        ),
        sa.Column(
            "tenure",
            _create_enum("atlas_tenure", TENURE),
            nullable=False,
        ),
        sa.Column(
            "action",
            _create_enum("atlas_cell_action", CELL_ACTION),
            nullable=False,
        ),
        sa.Column("confidence_unconditional", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_regime_conditional", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "regime_state_at_call",
            _create_enum("atlas_regime_state", REGIME_STATE),
            nullable=False,
        ),
        sa.Column(
            "cell_active_in_regime",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("stable_features", postgresql.JSONB(), nullable=True),
        sa.Column("predicted_excess", sa.Numeric(10, 6), nullable=True),
        # Exit tracking — signal_call rows stay "open" until exit_date set.
        # Per CONTEXT.md, exit triggers on: tenure_expiry / cell_flip_to_negative
        # (the cell state collapse) / user_close / delisting / cell_deprecated.
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_price", sa.Numeric(20, 4), nullable=True),
        sa.Column(
            "exit_reason",
            _create_enum("atlas_exit_reason", EXIT_REASON),
            nullable=True,
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        schema=_SCHEMA,
    )
    # Indexes — query patterns from eng review §1.4 API contracts
    op.create_index(
        "ix_atlas_signal_calls_date_action_tier",
        "atlas_signal_calls",
        ["date", "action", "cap_tier_at_trigger"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_signal_calls_iid_date",
        "atlas_signal_calls",
        ["instrument_id", "date"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_atlas_signal_calls_cell_date",
        "atlas_signal_calls",
        ["cell_id", "date"],
        schema=_SCHEMA,
    )
    # Open-positions partial index — supports "active signal calls" queries
    # used by brief cache invalidation (CONTEXT.md brief cache section).
    op.execute(
        f"""
        CREATE INDEX ix_atlas_signal_calls_open
        ON {_SCHEMA}.atlas_signal_calls (instrument_id, cell_id, tenure)
        WHERE exit_date IS NULL
        """
    )


def downgrade() -> None:
    """Reverse upgrade. Drop in FK-dependency order (signal_calls before
    scorecard_daily + cell_definitions; regime_daily independent).

    Note: this DOES drop the tables; for a post-launch downgrade with
    production data, use the data-export-first pattern documented in
    migration 087 (v5 deprecation) — but at this stage (pre-Phase-3 ship)
    the tables are empty and drop is safe.
    """
    # Drop tables in reverse FK order
    op.drop_index("ix_atlas_signal_calls_open", schema=_SCHEMA)
    op.drop_index("ix_atlas_signal_calls_cell_date", "atlas_signal_calls", schema=_SCHEMA)
    op.drop_index("ix_atlas_signal_calls_iid_date", "atlas_signal_calls", schema=_SCHEMA)
    op.drop_index(
        "ix_atlas_signal_calls_date_action_tier",
        "atlas_signal_calls",
        schema=_SCHEMA,
    )
    op.drop_table("atlas_signal_calls", schema=_SCHEMA)

    op.drop_index("uq_atlas_cell_definitions_active", schema=_SCHEMA)
    op.drop_table("atlas_cell_definitions", schema=_SCHEMA)

    op.drop_index("ix_atlas_scorecard_daily_date", "atlas_scorecard_daily", schema=_SCHEMA)
    op.drop_index(
        "ix_atlas_scorecard_daily_iid_date", "atlas_scorecard_daily", schema=_SCHEMA
    )
    op.drop_table("atlas_scorecard_daily", schema=_SCHEMA)

    op.drop_index("ix_atlas_regime_daily_date", "atlas_regime_daily", schema=_SCHEMA)
    op.drop_table("atlas_regime_daily", schema=_SCHEMA)

    # Drop enums (after tables that reference them)
    bind = op.get_bind()
    for name in (
        "atlas_exit_reason",
        "atlas_drift_status",
        "atlas_regime_state",
        "atlas_tenure",
        "atlas_cell_action",
        "atlas_family_state",
        "atlas_cap_tier",
    ):
        postgresql.ENUM(name=name, schema=_SCHEMA).drop(bind, checkfirst=True)
