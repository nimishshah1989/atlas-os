"""Atlas Strategy Lab — 8 new tables for genome-based portfolio simulation.

Tables (all in ``atlas`` schema, matching the convention from migration 004):
1. atlas_strategy_genomes — evolution population (active, promoted, killed, archived)
2. atlas_strategy_performance_daily — daily metrics (Sortino, Calmar, alpha, drawdown, heat)
3. atlas_strategy_positions_daily — daily holdings per genome (entry_date, tax_status)
4. atlas_strategy_leaderboard — top genomes by Sortino/Calmar
5. atlas_strategy_insights — nightly parameter importance + top deltas
6. atlas_universe_membership_daily — daily Nifty 500 membership (was_member flag)
7. atlas_strategy_evolution_log — event history (born, killed, promoted, mutated, crossover)
8. atlas_portfolio_config — active portfolio configuration + candidate approval

Revision ID: 067
Revises: 066
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None

# Single source of truth for the schema name in this migration. Atlas's data
# tables live in the ``atlas`` schema per migration 004 / atlas.config.SCHEMA_NAME.
_SCHEMA = "atlas"


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "atlas_strategy_genomes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("parent_ids", ARRAY(UUID(as_uuid=True)), nullable=True),
        sa.Column("genome_json", JSONB, nullable=False),
        sa.Column("born_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("kill_reason", sa.Text, nullable=True),
        sa.Column("generation", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','promoted','killed','archived')", name="ck_genomes_status"),
        schema=_SCHEMA,
    )
    op.create_index("ix_genomes_status", "atlas_strategy_genomes", ["status"], schema=_SCHEMA)
    op.create_index("ix_genomes_generation", "atlas_strategy_genomes", ["generation"], schema=_SCHEMA)

    op.create_table(
        "atlas_strategy_performance_daily",
        sa.Column(
            "genome_id",
            UUID(as_uuid=True),
            sa.ForeignKey("atlas.atlas_strategy_genomes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("sortino_insample", sa.Numeric(10, 4), nullable=True),
        sa.Column("sortino_oos", sa.Numeric(10, 4), nullable=True),
        sa.Column("calmar_oos", sa.Numeric(10, 4), nullable=True),
        sa.Column("alpha_vs_nifty500", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(10, 4), nullable=True),
        sa.Column("portfolio_heat", sa.Numeric(10, 4), nullable=True),
        sa.Column("ltcg_exemption_used", sa.Numeric(20, 4), nullable=True),
        sa.Column("total_trades", sa.Integer, nullable=True),
        sa.Column("turnover_pct", sa.Numeric(10, 4), nullable=True),
        sa.PrimaryKeyConstraint("genome_id", "date"),
        schema=_SCHEMA,
    )
    op.create_index("ix_perf_daily_date", "atlas_strategy_performance_daily", ["date"], schema=_SCHEMA)
    op.create_index("ix_perf_genome_id", "atlas_strategy_performance_daily", ["genome_id"], schema=_SCHEMA)

    op.create_table(
        "atlas_strategy_positions_daily",
        sa.Column(
            "genome_id",
            UUID(as_uuid=True),
            sa.ForeignKey("atlas.atlas_strategy_genomes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column(
            "instrument_id",
            UUID(as_uuid=True),
            # No FK: trading bounded context must not reference atlas.compute tables.
            # instrument_id values are validated at write time by the simulation layer.
            nullable=False,
            index=True,
        ),
        sa.Column("position_type", sa.Text, nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("shares", sa.Numeric(20, 4), nullable=False),
        sa.Column("current_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(20, 4), nullable=False),
        sa.Column("holding_days", sa.Integer, nullable=False),
        sa.Column("tax_status", sa.Text, nullable=False),
        sa.Column("entry_signals", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("genome_id", "date", "instrument_id"),
        sa.CheckConstraint("position_type IN ('equity','liquidbees')", name="ck_positions_type"),
        sa.CheckConstraint("tax_status IN ('stcg','ltcg_eligible','liquidbees')", name="ck_positions_tax"),
        schema=_SCHEMA,
    )
    op.create_index("ix_positions_daily_date", "atlas_strategy_positions_daily", ["date"], schema=_SCHEMA)
    op.create_index("ix_positions_genome_id", "atlas_strategy_positions_daily", ["genome_id"], schema=_SCHEMA)
    op.create_index("ix_positions_instrument_id", "atlas_strategy_positions_daily", ["instrument_id"], schema=_SCHEMA)

    op.create_table(
        "atlas_strategy_leaderboard",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column(
            "genome_id",
            UUID(as_uuid=True),
            sa.ForeignKey("atlas.atlas_strategy_genomes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("strategy_name", sa.Text, nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        # NOT NULL: a genome that makes the leaderboard must have been evaluated.
        sa.Column("sortino_oos", sa.Numeric(10, 4), nullable=False),
        sa.Column("calmar_oos", sa.Numeric(10, 4), nullable=False),
        sa.Column("alpha_30d", sa.Numeric(10, 4), nullable=True),
        sa.Column("regime_breakdown", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        # tournament.promote_to_leaderboard upserts via ON CONFLICT (genome_id);
        # the UNIQUE constraint is what makes that idempotent. Without it the
        # second promotion of a genome would crash the nightly chain.
        sa.UniqueConstraint("genome_id", name="uq_leaderboard_genome_id"),
        schema=_SCHEMA,
    )
    op.create_index("ix_leaderboard_rank", "atlas_strategy_leaderboard", ["rank"], schema=_SCHEMA)

    op.create_table(
        "atlas_strategy_insights",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("insight_bullets", JSONB, nullable=False),
        sa.Column("parameter_importance", JSONB, nullable=True),
        sa.Column("top_genome_deltas", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema=_SCHEMA,
    )

    op.create_table(
        "atlas_universe_membership_daily",
        sa.Column(
            "instrument_id",
            UUID(as_uuid=True),
            # No FK: same bounded-context rule as positions_daily.
            nullable=False,
            index=True,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("universe", sa.Text, nullable=False),
        sa.Column("was_member", sa.Boolean, nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("instrument_id", "date", "universe"),
        schema=_SCHEMA,
    )
    op.create_index("ix_universe_membership_date_universe", "atlas_universe_membership_daily", ["date", "universe"], schema=_SCHEMA)
    op.create_index("ix_membership_instrument_id", "atlas_universe_membership_daily", ["instrument_id"], schema=_SCHEMA)

    op.create_table(
        "atlas_strategy_evolution_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "genome_id",
            UUID(as_uuid=True),
            sa.ForeignKey("atlas.atlas_strategy_genomes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("parent_ids", ARRAY(UUID(as_uuid=True)), nullable=True),
        sa.Column("final_sortino", sa.Numeric(10, 4), nullable=True),
        sa.Column("final_calmar", sa.Numeric(10, 4), nullable=True),
        sa.Column("kill_reason", sa.Text, nullable=True),
        sa.Column("generation", sa.Integer, nullable=True),
        sa.Column("parameter_delta", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "event_type IN ('born','killed','promoted','demoted','mutated','crossover')",
            name="ck_evolution_event_type",
        ),
        schema=_SCHEMA,
    )
    op.create_index("ix_evolution_log_event_at", "atlas_strategy_evolution_log", ["event_at"], schema=_SCHEMA)
    op.create_index("ix_evolution_log_event_type", "atlas_strategy_evolution_log", ["event_type"], schema=_SCHEMA)
    op.create_index("ix_evolution_genome_id", "atlas_strategy_evolution_log", ["genome_id"], schema=_SCHEMA)

    op.create_table(
        "atlas_portfolio_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("config_json", JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("label", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema=_SCHEMA,
    )
    op.create_index("ix_portfolio_config_is_active", "atlas_portfolio_config", ["is_active"], schema=_SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_portfolio_config_is_active", table_name="atlas_portfolio_config", schema=_SCHEMA)
    op.drop_index("ix_evolution_log_event_type", table_name="atlas_strategy_evolution_log", schema=_SCHEMA)
    op.drop_index("ix_evolution_log_event_at", table_name="atlas_strategy_evolution_log", schema=_SCHEMA)
    op.drop_index("ix_evolution_genome_id", table_name="atlas_strategy_evolution_log", schema=_SCHEMA)
    op.drop_index("ix_universe_membership_date_universe", table_name="atlas_universe_membership_daily", schema=_SCHEMA)
    op.drop_index("ix_membership_instrument_id", table_name="atlas_universe_membership_daily", schema=_SCHEMA)
    op.drop_index("ix_leaderboard_rank", table_name="atlas_strategy_leaderboard", schema=_SCHEMA)
    op.drop_index("ix_positions_daily_date", table_name="atlas_strategy_positions_daily", schema=_SCHEMA)
    op.drop_index("ix_positions_instrument_id", table_name="atlas_strategy_positions_daily", schema=_SCHEMA)
    op.drop_index("ix_positions_genome_id", table_name="atlas_strategy_positions_daily", schema=_SCHEMA)
    op.drop_index("ix_perf_daily_date", table_name="atlas_strategy_performance_daily", schema=_SCHEMA)
    op.drop_index("ix_perf_genome_id", table_name="atlas_strategy_performance_daily", schema=_SCHEMA)
    op.drop_index("ix_genomes_generation", table_name="atlas_strategy_genomes", schema=_SCHEMA)
    op.drop_index("ix_genomes_status", table_name="atlas_strategy_genomes", schema=_SCHEMA)

    for table in [
        "atlas_portfolio_config",
        "atlas_strategy_evolution_log",
        "atlas_universe_membership_daily",
        "atlas_strategy_insights",
        "atlas_strategy_leaderboard",
        "atlas_strategy_positions_daily",
        "atlas_strategy_performance_daily",
        "atlas_strategy_genomes",
    ]:
        op.drop_table(table, schema=_SCHEMA)
