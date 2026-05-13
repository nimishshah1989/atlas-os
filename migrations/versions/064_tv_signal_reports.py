"""tv_signal_reports: TV alert registry, signal reports, alert feed

Revision ID: 064
Revises: 063
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tv_alert_registry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("chart_type", sa.String(20), nullable=False),
        sa.Column("condition_tier", sa.Integer, nullable=False),
        sa.Column("condition_code", sa.String(50), nullable=False),
        sa.Column("tv_alert_id", sa.String(100)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("layout_id", sa.String(50), nullable=False),
        sa.Column("webhook_url", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_tv_alert_registry_ticker", "tv_alert_registry", ["ticker"])
    op.create_index("idx_tv_alert_registry_active", "tv_alert_registry", ["is_active"])

    op.create_table(
        "tv_signal_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column(
            "instrument_id",
            UUID(as_uuid=True),
            sa.ForeignKey("atlas.atlas_universe_stocks.instrument_id"),
            nullable=True,
            index=True,
        ),
        sa.Column("exchange", sa.String(10), nullable=False, server_default="NSE"),
        sa.Column("company_name", sa.String(200)),
        sa.Column("sector", sa.String(100)),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("condition_tier", sa.Integer, nullable=False),
        sa.Column("condition_code", sa.String(50), nullable=False),
        sa.Column("condition_label", sa.String(200), nullable=False),
        sa.Column("chart_type", sa.String(20), nullable=False),
        sa.Column("trigger_price", sa.Numeric(20, 4)),
        sa.Column("trigger_volume", sa.BigInteger),
        sa.Column("volume_vs_avg", sa.Numeric(10, 4)),
        sa.Column("confirmation_level", sa.String(20), nullable=False),
        sa.Column("conviction_score", sa.Numeric(5, 2)),
        sa.Column("conviction_trend", sa.String(10)),
        sa.Column("cts_state", sa.String(50)),
        sa.Column("rs_rank", sa.Integer),
        sa.Column("rs_rank_total", sa.Integer),
        sa.Column("rs_percentile", sa.Numeric(5, 2)),
        sa.Column("sector_regime", sa.String(50)),
        sa.Column("market_regime", sa.String(50)),
        sa.Column("rsi_14", sa.Numeric(6, 2)),
        sa.Column("macd_signal", sa.String(10)),
        sa.Column("ema_alignment", sa.String(20)),
        sa.Column("hh_hl_state", sa.String(20)),
        sa.Column("pattern_label", sa.String(100)),
        sa.Column("perf_1m", sa.Numeric(10, 4)),
        sa.Column("perf_3m", sa.Numeric(10, 4)),
        sa.Column("perf_6m", sa.Numeric(10, 4)),
        sa.Column("perf_ytd", sa.Numeric(10, 4)),
        sa.Column("perf_vs_nifty_1m", sa.Numeric(10, 4)),
        sa.Column("perf_vs_nifty_ytd", sa.Numeric(10, 4)),
        sa.Column("chart_daily_url", sa.String(500)),
        sa.Column("chart_weekly_url", sa.String(500)),
        sa.Column("chart_vs_sector_url", sa.String(500)),
        sa.Column("screenshot_daily", sa.String(500)),
        sa.Column("screenshot_weekly", sa.String(500)),
        sa.Column("screenshot_sector", sa.String(500)),
        sa.Column("narrative", sa.Text),
        sa.Column("report_html", sa.Text),
        sa.Column("verdict", sa.String(20)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("reviewed_by", sa.String(100)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_tv_signal_reports_ticker", "tv_signal_reports", ["ticker"])
    op.create_index(
        "idx_tv_signal_reports_triggered_at",
        "tv_signal_reports",
        ["triggered_at"],
        postgresql_ops={"triggered_at": "DESC"},
    )
    op.create_index("idx_tv_signal_reports_tier", "tv_signal_reports", ["condition_tier"])
    op.create_index("idx_tv_signal_reports_confirmation", "tv_signal_reports", ["confirmation_level"])
    # Dedup UNIQUE: prevents TV webhook retries from creating duplicate reports within same hour
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX idx_tv_signal_dedup "
            "ON tv_signal_reports (ticker, condition_code, chart_type, date_trunc('hour', triggered_at))"
        )
    )

    op.create_table(
        "atlas_signal_alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", UUID(as_uuid=True), sa.ForeignKey("tv_signal_reports.id"), index=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("alert_type", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.String(500)),
        sa.Column("is_read", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_atlas_signal_alerts_created",
        "atlas_signal_alerts",
        ["created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index("idx_atlas_signal_alerts_read", "atlas_signal_alerts", ["is_read"])


def downgrade() -> None:
    op.drop_table("atlas_signal_alerts")
    op.drop_table("tv_signal_reports")
    op.drop_table("tv_alert_registry")
