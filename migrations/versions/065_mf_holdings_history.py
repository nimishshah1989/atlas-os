"""mf_holdings_history: fund holdings changes + decision scores

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
        sa.Column("from_date", sa.Date, nullable=True),
        sa.Column("to_date", sa.Date, nullable=False),
        sa.Column("instrument_id", sa.Text, nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False),
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="atlas",
    )
    op.create_index(
        "idx_fund_holdings_changes_fund_period",
        "atlas_fund_holdings_changes",
        ["mstar_id", "to_date"],
        schema="atlas",
    )
    op.create_index(
        "idx_fund_holdings_changes_outcome_1m",
        "atlas_fund_holdings_changes",
        ["to_date"],
        postgresql_where=sa.text("outcome_quality_1m IS NULL"),
        schema="atlas",
    )
    op.create_index(
        "idx_fund_holdings_changes_outcome_3m",
        "atlas_fund_holdings_changes",
        ["to_date"],
        postgresql_where=sa.text("outcome_quality_3m IS NULL"),
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="atlas",
    )
    op.create_index(
        "idx_fund_decision_scores_fund_period",
        "atlas_fund_decision_scores",
        ["mstar_id", "period_date"],
        unique=True,
        schema="atlas",
    )

    op.execute("""
        INSERT INTO atlas.atlas_thresholds (
            threshold_key, threshold_value, category, description,
            min_allowed, max_allowed, default_value,
            last_modified_by, is_active
        )
        VALUES
            ('holdings_weight_change_min_pct', 0.25, 'funds',
             'Min |weight_delta| (%) to classify as increase/decrease vs noise',
             0.05, 2.0, 0.25, 'migration_065', true),
            ('decision_score_sharp_threshold', 65.0, 'funds',
             'signal_score >= this → Sharp decision state',
             50.0, 90.0, 65.0, 'migration_065', true),
            ('decision_score_poor_threshold', 40.0, 'funds',
             'signal_score < this → Poor decision state',
             10.0, 50.0, 40.0, 'migration_065', true)
        ON CONFLICT (threshold_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM atlas.atlas_thresholds WHERE threshold_key IN ("
               "'holdings_weight_change_min_pct','decision_score_sharp_threshold',"
               "'decision_score_poor_threshold')")
    op.drop_table("atlas_fund_decision_scores", schema="atlas")
    op.drop_table("atlas_fund_holdings_changes", schema="atlas")
