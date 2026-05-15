"""mf_holdings_history: fund holdings changes and decision scores

Revision ID: 065
Revises: 064
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atlas_fund_holdings_changes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mstar_id", sa.String(32), nullable=False, index=True),
        sa.Column("from_date", sa.Date, nullable=True, comment="NULL for first-ever portfolio observation (no prior snapshot to diff from)"),
        sa.Column("to_date", sa.Date, nullable=False),
        sa.Column("instrument_id", sa.Text, nullable=False, index=True),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("weight_before", sa.Numeric(10, 4), nullable=False),
        sa.Column("weight_after", sa.Numeric(10, 4), nullable=False),
        sa.Column("weight_delta", sa.Numeric(10, 4), nullable=False),
        sa.Column("rs_state_at_action", sa.String(20), nullable=True),
        sa.Column("momentum_state_at_action", sa.String(20), nullable=True),
        sa.Column("signal_quality", sa.String(10), nullable=True),
        sa.Column("outcome_rs_state_1m", sa.String(20), nullable=True),
        sa.Column("outcome_ret_1m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_quality_1m", sa.String(10), nullable=True),
        sa.Column("outcome_rs_state_3m", sa.String(20), nullable=True),
        sa.Column("outcome_ret_3m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_quality_3m", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "action IN ('entry','exit','increase','decrease')",
            name="chk_afhc_action",
        ),
        sa.CheckConstraint(
            "signal_quality IN ('high','low','neutral') OR signal_quality IS NULL",
            name="chk_afhc_signal_quality",
        ),
        sa.CheckConstraint(
            "outcome_quality_1m IN ('good','bad','neutral') OR outcome_quality_1m IS NULL",
            name="chk_afhc_outcome_quality_1m",
        ),
        sa.CheckConstraint(
            "outcome_quality_3m IN ('good','bad','neutral') OR outcome_quality_3m IS NULL",
            name="chk_afhc_outcome_quality_3m",
        ),
        sa.UniqueConstraint("mstar_id", "to_date", "instrument_id", name="uq_afhc_mstar_date_instrument"),
        schema="atlas",
    )
    op.create_index(
        "idx_afhc_mstar_to_date",
        "atlas_fund_holdings_changes",
        ["mstar_id", "to_date"],
        schema="atlas",
    )
    op.create_index(
        "idx_afhc_mstar_from_to",
        "atlas_fund_holdings_changes",
        ["mstar_id", "from_date", "to_date"],
        schema="atlas",
    )
    op.create_index(
        "idx_afhc_instrument_to_date",
        "atlas_fund_holdings_changes",
        ["instrument_id", "to_date"],
        schema="atlas",
    )

    op.create_table(
        "atlas_fund_decision_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mstar_id", sa.String(32), nullable=False, index=True),
        sa.Column("period_date", sa.Date, nullable=False),
        sa.Column("entries_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("exits_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("increases_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("decreases_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("quality_entries_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("quality_exits_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("signal_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_entries_pct_1m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_exits_pct_1m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_score_1m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_entries_pct_3m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_exits_pct_3m", sa.Numeric(10, 4), nullable=True),
        sa.Column("outcome_score_3m", sa.Numeric(10, 4), nullable=True),
        sa.Column("decision_state", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("mstar_id", "period_date", name="uq_afds_mstar_period"),
        schema="atlas",
    )
    op.create_index(
        "idx_afds_period_date",
        "atlas_fund_decision_scores",
        ["period_date"],
        schema="atlas",
    )

    op.execute(sa.text("""
        INSERT INTO atlas.atlas_thresholds (
            threshold_key, threshold_value, category, description,
            min_allowed, max_allowed, default_value,
            last_modified_by, is_active
        )
        VALUES
            ('holdings_weight_change_min_pct',  0.25, 'mf_holdings', 'Min absolute weight delta to classify as increase/decrease', 0.01, 5.0, 0.25, 'migration_065', true),
            ('decision_score_sharp_threshold', 65.0, 'mf_holdings', 'Signal score >= this => Sharp decision state', 50.0, 95.0, 65.0, 'migration_065', true),
            ('decision_score_poor_threshold',  40.0, 'mf_holdings', 'Signal score < this => Poor decision state',  5.0,  50.0, 40.0, 'migration_065', true),
            ('decision_score_min_decisions',    3.0, 'mf_holdings', 'Min entry+exit count to compute signal_score for a period', 1.0, 20.0, 3.0, 'migration_065', true)
        ON CONFLICT (threshold_key) DO NOTHING
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DELETE FROM atlas.atlas_threshold_history
        WHERE threshold_key IN (
            'holdings_weight_change_min_pct',
            'decision_score_sharp_threshold',
            'decision_score_poor_threshold'
        )
    """))
    op.execute(sa.text("""
        DELETE FROM atlas.atlas_thresholds
        WHERE threshold_key IN (
            'holdings_weight_change_min_pct',
            'decision_score_sharp_threshold',
            'decision_score_poor_threshold',
            'decision_score_min_decisions'
        )
    """))
    op.drop_table("atlas_fund_decision_scores", schema="atlas")
    op.drop_table("atlas_fund_holdings_changes", schema="atlas")
