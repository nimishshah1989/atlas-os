# allow-large: replay of seven migrations
"""v6 — replay tables from 082-088 that never landed on Supabase atlas-os.

Idempotent. Re-applies the table-creation portions of migrations 082-088 using
CREATE TABLE IF NOT EXISTS semantics so it is safe to run against any
environment, including one where the tables already exist from a prior run.

WHY THIS EXISTS
---------------
The live Supabase atlas-os DB was stamped to alembic_version=093 via the
089→090→091→092→093 path without ever running 082-088. Those seven migrations
were written and tested on the local chain (which diverged at 080 into a
parallel sequence) but were never applied against this DB. This migration
replays every schema object they would have created.

OBJECTS CREATED
---------------
Tables (12):
  atlas_brief_cache                     (from 082)
  atlas_ledger                          (from 083)
  atlas_paper_portfolio                 (from 084)
  atlas_user_lots                       (from 084)
  atlas_etf_signal_calls                (from 085)
  atlas_mf_recommendation_daily        (from 085)
  atlas_mf_switch_rules                 (from 085)
  atlas_macro_features_daily            (from 086)
  atlas_macro_recommendation_daily      (from 086)
  atlas_provenance_log                  (from 087)
  atlas_drift_event_log                 (from 088)

Views (1):
  atlas_ledger_public                   (from 083)

Enums (4):
  atlas_etf_sub_category                (from 085, new)
  atlas_mf_quartile                     (from 085, new)
  atlas_mf_recommendation               (from 085, new)
  atlas_drift_action                    (from 088, new)

Policies (2):
  paper_portfolio_user_isolation        (from 084)
  user_lots_user_isolation              (from 084)

Triggers + functions (2):
  deny_update_delete_atlas_provenance_log   (from 087)
  deny_update_delete_atlas_drift_event_log  (from 088)

Retroactive FK constraints (2):
  fk_atlas_ledger_provenance_log_id             (from 087)
  fk_atlas_macro_features_daily_provenance_log_id (from 087)

OUT OF SCOPE
------------
- 089 v5-deprecation ALTER TABLE statements (separate concern; may have run
  via a different path, and are not safe to replay here).
- Seed data for atlas_mf_switch_rules (reserved for migration 095).

Revision ID: 094
Revises: 093
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op

revision = "094"
down_revision = "093"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_enum_if_not_exists(name: str, *values: str) -> None:
    """Create a Postgres ENUM in atlas schema only if it does not already exist."""
    values_sql = ", ".join(f"'{v}'" for v in values)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = '{name}' AND n.nspname = '{_SCHEMA}'
            ) THEN
                EXECUTE 'CREATE TYPE {_SCHEMA}.{name} AS ENUM ({values_sql})';
            END IF;
        END
        $$;
        """
    )


def _create_policy_if_not_exists(
    policy_name: str,
    table_name: str,
    for_clause: str,
    using_expr: str,
    with_check_expr: str,
) -> None:
    """Create a RLS policy only if it does not already exist."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE policyname = '{policy_name}'
                  AND tablename  = '{table_name}'
                  AND schemaname = '{_SCHEMA}'
            ) THEN
                EXECUTE $policy$
                    CREATE POLICY {policy_name}
                    ON {_SCHEMA}.{table_name}
                    {for_clause}
                    USING ({using_expr})
                    WITH CHECK ({with_check_expr})
                $policy$;
            END IF;
        END
        $$;
        """
    )


def _add_fk_if_not_exists(
    fk_name: str,
    source_table: str,
    source_col: str,
    target_table: str,
    target_col: str,
    on_delete: str,
) -> None:
    """Add a foreign key constraint only if it does not already exist."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE c.conname = '{fk_name}'
                  AND t.relname = '{source_table}'
                  AND n.nspname = '{_SCHEMA}'
            ) THEN
                EXECUTE $fk$
                    ALTER TABLE {_SCHEMA}.{source_table}
                    ADD CONSTRAINT {fk_name}
                    FOREIGN KEY ({source_col})
                    REFERENCES {_SCHEMA}.{target_table} ({target_col})
                    ON DELETE {on_delete}
                $fk$;
            END IF;
        END
        $$;
        """
    )


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # =========================================================================
    # 082 — atlas_brief_cache
    # =========================================================================
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_brief_cache (
            id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            instrument_id                   UUID NOT NULL,
            date                            DATE NOT NULL,
            action                          {_SCHEMA}.atlas_cell_action NOT NULL,
            cell_id                         UUID NOT NULL
                REFERENCES {_SCHEMA}.atlas_cell_definitions (cell_id)
                ON DELETE RESTRICT,
            signal_call_id                  UUID
                REFERENCES {_SCHEMA}.atlas_signal_calls (signal_call_id)
                ON DELETE CASCADE,
            brief_text                      TEXT NOT NULL,
            generated_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            valid_until                     TIMESTAMPTZ NOT NULL,
            invalidated_at                  TIMESTAMPTZ,
            invalidated_by_corp_action_id   UUID,
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_atlas_brief_cache_iid_date_action_cell
                UNIQUE (instrument_id, date, action, cell_id)
        );
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_brief_cache_valid_until
        ON {_SCHEMA}.atlas_brief_cache (valid_until);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_brief_cache_signal_call_id
        ON {_SCHEMA}.atlas_brief_cache (signal_call_id);
        """
    )
    # Partial index — hot read path for active (non-invalidated) briefs.
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_brief_cache_active
        ON {_SCHEMA}.atlas_brief_cache (instrument_id, date, action)
        WHERE invalidated_at IS NULL;
        """
    )

    # =========================================================================
    # 083 — atlas_ledger + atlas_ledger_public view
    # =========================================================================
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_ledger (
            signal_call_id      UUID PRIMARY KEY
                REFERENCES {_SCHEMA}.atlas_signal_calls (signal_call_id)
                ON DELETE RESTRICT,
            realized_excess     NUMERIC(10, 4) NOT NULL,
            realized_at         TIMESTAMPTZ NOT NULL,
            drift_z             NUMERIC(8, 4),
            status              {_SCHEMA}.atlas_drift_status NOT NULL,
            provenance_log_id   UUID,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_ledger_realized_at
        ON {_SCHEMA}.atlas_ledger (realized_at);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_ledger_status
        ON {_SCHEMA}.atlas_ledger (status);
        """
    )

    # View — CREATE OR REPLACE is idempotent.
    op.execute(
        f"""
        CREATE OR REPLACE VIEW {_SCHEMA}.atlas_ledger_public AS
        SELECT signal_call_id, realized_excess, realized_at
        FROM {_SCHEMA}.atlas_ledger;
        """
    )

    # Conditional GRANT — only if the atlas_agent_readonly role exists.
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

    # =========================================================================
    # 084 — atlas_paper_portfolio + atlas_user_lots + RLS
    # =========================================================================
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_paper_portfolio (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL,
            signal_call_id  UUID NOT NULL
                REFERENCES {_SCHEMA}.atlas_signal_calls (signal_call_id)
                ON DELETE RESTRICT,
            instrument_id   UUID NOT NULL,
            cell_id         UUID NOT NULL
                REFERENCES {_SCHEMA}.atlas_cell_definitions (cell_id)
                ON DELETE RESTRICT,
            tenure          {_SCHEMA}.atlas_tenure NOT NULL,
            entry_date      DATE NOT NULL,
            entry_price     NUMERIC(20, 4) NOT NULL,
            exit_date       DATE,
            exit_price      NUMERIC(20, 4),
            exit_reason     {_SCHEMA}.atlas_exit_reason,
            excess_return   NUMERIC(10, 4),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_atlas_paper_portfolio_user_inst_cell_tenure_date
                UNIQUE (user_id, instrument_id, cell_id, tenure, entry_date)
        );
        """
    )

    # Partial index — "open positions for user X".
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_paper_portfolio_user_open
        ON {_SCHEMA}.atlas_paper_portfolio (user_id)
        WHERE exit_date IS NULL;
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_paper_portfolio_signal_call_id
        ON {_SCHEMA}.atlas_paper_portfolio (signal_call_id);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_paper_portfolio_entry_date
        ON {_SCHEMA}.atlas_paper_portfolio (entry_date);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_paper_portfolio_exit_date
        ON {_SCHEMA}.atlas_paper_portfolio (exit_date);
        """
    )

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_user_lots (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL,
            instrument_id   UUID NOT NULL,
            lot_date        DATE NOT NULL,
            quantity        NUMERIC(20, 4) NOT NULL,
            cost_basis      NUMERIC(20, 4) NOT NULL,
            is_realized     BOOLEAN NOT NULL DEFAULT FALSE,
            realized_date   DATE,
            realized_price  NUMERIC(20, 4),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_user_lots_user_instrument
        ON {_SCHEMA}.atlas_user_lots (user_id, instrument_id);
        """
    )

    # RLS — ALTER TABLE ENABLE ROW LEVEL SECURITY is idempotent.
    op.execute(f"ALTER TABLE {_SCHEMA}.atlas_paper_portfolio ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {_SCHEMA}.atlas_user_lots ENABLE ROW LEVEL SECURITY;")

    _jwt_sub_expr = (
        "(current_setting('request.jwt.claims', true)::jsonb ->> 'sub')::uuid"
    )
    _create_policy_if_not_exists(
        policy_name="paper_portfolio_user_isolation",
        table_name="atlas_paper_portfolio",
        for_clause="FOR ALL",
        using_expr=f"user_id = {_jwt_sub_expr}",
        with_check_expr=f"user_id = {_jwt_sub_expr}",
    )
    _create_policy_if_not_exists(
        policy_name="user_lots_user_isolation",
        table_name="atlas_user_lots",
        for_clause="FOR ALL",
        using_expr=f"user_id = {_jwt_sub_expr}",
        with_check_expr=f"user_id = {_jwt_sub_expr}",
    )

    # =========================================================================
    # 085 — atlas_etf_signal_calls + atlas_mf_recommendation_daily +
    #         atlas_mf_switch_rules + 3 new enums
    # =========================================================================
    _create_enum_if_not_exists("atlas_etf_sub_category", "broad_market", "sectoral")
    _create_enum_if_not_exists("atlas_mf_quartile", "Q1", "Q2", "Q3", "Q4")
    _create_enum_if_not_exists("atlas_mf_recommendation", "BUY", "HOLD", "SWITCH", "AVOID")

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_etf_signal_calls (
            etf_signal_call_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            etf_instrument_id               UUID NOT NULL,
            etf_sub_category                {_SCHEMA}.atlas_etf_sub_category NOT NULL,
            date                            DATE NOT NULL,
            cell_id                         UUID NOT NULL
                REFERENCES {_SCHEMA}.atlas_cell_definitions (cell_id)
                ON DELETE RESTRICT,
            cap_tier_at_trigger             {_SCHEMA}.atlas_cap_tier NOT NULL,
            tenure                          {_SCHEMA}.atlas_tenure NOT NULL,
            action                          {_SCHEMA}.atlas_cell_action NOT NULL,
            confidence_unconditional        NUMERIC(5, 4) NOT NULL,
            confidence_regime_conditional   NUMERIC(5, 4),
            regime_state_at_call            {_SCHEMA}.atlas_regime_state NOT NULL,
            cell_active_in_regime           BOOLEAN NOT NULL DEFAULT TRUE,
            stable_features                 JSONB,
            predicted_excess                NUMERIC(10, 6),
            exit_date                       DATE,
            exit_price                      NUMERIC(20, 4),
            exit_reason                     {_SCHEMA}.atlas_exit_reason,
            computed_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_etf_signal_calls_date_action_tier
        ON {_SCHEMA}.atlas_etf_signal_calls (date, action, cap_tier_at_trigger);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_etf_signal_calls_iid_date
        ON {_SCHEMA}.atlas_etf_signal_calls (etf_instrument_id, date);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_etf_signal_calls_cell_date
        ON {_SCHEMA}.atlas_etf_signal_calls (cell_id, date);
        """
    )
    # Partial index — open ETF positions.
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_etf_signal_calls_open
        ON {_SCHEMA}.atlas_etf_signal_calls (etf_instrument_id, cell_id, tenure)
        WHERE exit_date IS NULL;
        """
    )

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_mf_recommendation_daily (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date                DATE NOT NULL,
            mf_instrument_id    UUID NOT NULL,
            category            VARCHAR(64) NOT NULL,
            peer_quartile       {_SCHEMA}.atlas_mf_quartile NOT NULL,
            consistency_months  INTEGER NOT NULL DEFAULT 0,
            nav                 NUMERIC(20, 4) NOT NULL,
            expense_ratio       NUMERIC(6, 4),
            recommendation      {_SCHEMA}.atlas_mf_recommendation NOT NULL,
            switch_target_iid   UUID,
            data_as_of          DATE NOT NULL,
            computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_atlas_mf_recommendation_daily_date_iid
                UNIQUE (date, mf_instrument_id)
        );
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_mf_recommendation_daily_date_reco
        ON {_SCHEMA}.atlas_mf_recommendation_daily (date, recommendation);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_mf_recommendation_daily_iid_date
        ON {_SCHEMA}.atlas_mf_recommendation_daily (mf_instrument_id, date);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_mf_recommendation_daily_category_date
        ON {_SCHEMA}.atlas_mf_recommendation_daily (category, date);
        """
    )

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_mf_switch_rules (
            id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            category                        VARCHAR(64) NOT NULL,
            current_quartile_floor          {_SCHEMA}.atlas_mf_quartile NOT NULL,
            target_quartile_ceiling         {_SCHEMA}.atlas_mf_quartile NOT NULL,
            min_target_consistency_months   INTEGER NOT NULL DEFAULT 6,
            tie_break                       VARCHAR(32) NOT NULL DEFAULT 'lowest_expense_ratio',
            active                          BOOLEAN NOT NULL DEFAULT TRUE,
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # Partial unique index — one active rule per category.
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_atlas_mf_switch_rules_category_active
        ON {_SCHEMA}.atlas_mf_switch_rules (category)
        WHERE active = TRUE;
        """
    )

    # =========================================================================
    # 086 — atlas_macro_features_daily + atlas_macro_recommendation_daily
    # =========================================================================
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_macro_features_daily (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date                    DATE NOT NULL,
            regime_state            {_SCHEMA}.atlas_regime_state NOT NULL,
            equity_vs_debt_spread   NUMERIC(10, 6),
            gold_trend              NUMERIC(10, 6),
            inr_usd_trend           NUMERIC(10, 6),
            cross_asset_dispersion  NUMERIC(10, 6),
            vix_level               NUMERIC(8, 4),
            g_sec_10y_yield         NUMERIC(6, 4),
            crude_brent_inr         NUMERIC(12, 4),
            provenance_log_id       UUID,
            computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_atlas_macro_features_daily_date UNIQUE (date)
        );
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_macro_features_daily_date_desc
        ON {_SCHEMA}.atlas_macro_features_daily (date DESC);
        """
    )

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_macro_recommendation_daily (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date                DATE NOT NULL,
            regime_state        {_SCHEMA}.atlas_regime_state NOT NULL,
            equity_pct_low      NUMERIC(5, 2) NOT NULL,
            equity_pct_high     NUMERIC(5, 2) NOT NULL,
            debt_pct_low        NUMERIC(5, 2) NOT NULL,
            debt_pct_high       NUMERIC(5, 2) NOT NULL,
            gold_pct_low        NUMERIC(5, 2) NOT NULL,
            gold_pct_high       NUMERIC(5, 2) NOT NULL,
            cash_pct_low        NUMERIC(5, 2) NOT NULL,
            cash_pct_high       NUMERIC(5, 2) NOT NULL,
            drivers             JSONB,
            methodology_ref     VARCHAR(64),
            macro_features_id   UUID
                REFERENCES {_SCHEMA}.atlas_macro_features_daily (id)
                ON DELETE SET NULL,
            computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_atlas_macro_reco_equity_low_le_high
                CHECK (equity_pct_low <= equity_pct_high),
            CONSTRAINT ck_atlas_macro_reco_debt_low_le_high
                CHECK (debt_pct_low <= debt_pct_high),
            CONSTRAINT ck_atlas_macro_reco_gold_low_le_high
                CHECK (gold_pct_low <= gold_pct_high),
            CONSTRAINT ck_atlas_macro_reco_cash_low_le_high
                CHECK (cash_pct_low <= cash_pct_high),
            CONSTRAINT ck_atlas_macro_reco_equity_low_range
                CHECK (equity_pct_low >= 0 AND equity_pct_low <= 100),
            CONSTRAINT ck_atlas_macro_reco_equity_high_range
                CHECK (equity_pct_high >= 0 AND equity_pct_high <= 100),
            CONSTRAINT ck_atlas_macro_reco_debt_low_range
                CHECK (debt_pct_low >= 0 AND debt_pct_low <= 100),
            CONSTRAINT ck_atlas_macro_reco_debt_high_range
                CHECK (debt_pct_high >= 0 AND debt_pct_high <= 100),
            CONSTRAINT ck_atlas_macro_reco_gold_low_range
                CHECK (gold_pct_low >= 0 AND gold_pct_low <= 100),
            CONSTRAINT ck_atlas_macro_reco_gold_high_range
                CHECK (gold_pct_high >= 0 AND gold_pct_high <= 100),
            CONSTRAINT ck_atlas_macro_reco_cash_low_range
                CHECK (cash_pct_low >= 0 AND cash_pct_low <= 100),
            CONSTRAINT ck_atlas_macro_reco_cash_high_range
                CHECK (cash_pct_high >= 0 AND cash_pct_high <= 100),
            CONSTRAINT uq_atlas_macro_recommendation_daily_date UNIQUE (date)
        );
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_macro_recommendation_daily_date_desc
        ON {_SCHEMA}.atlas_macro_recommendation_daily (date DESC);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_macro_recommendation_daily_regime_state
        ON {_SCHEMA}.atlas_macro_recommendation_daily (regime_state);
        """
    )

    # =========================================================================
    # 087 — atlas_provenance_log + write-once trigger + retroactive FKs
    # =========================================================================
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_provenance_log (
            run_id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ts                          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            input_dataset_sha256        CHAR(64) NOT NULL,
            universe_definition_sha256  CHAR(64) NOT NULL,
            code_commit_sha             VARCHAR(40) NOT NULL,
            friction_params_row_ids     JSONB,
            output_table                VARCHAR(64) NOT NULL,
            output_row_range            JSONB NOT NULL,
            run_type                    VARCHAR(32) NOT NULL,
            actor                       VARCHAR(64) NOT NULL DEFAULT 'system',
            notes                       TEXT,
            CONSTRAINT ck_atlas_provenance_log_input_dataset_sha256_hex
                CHECK (input_dataset_sha256 ~ '^[a-f0-9]{{64}}$'),
            CONSTRAINT ck_atlas_provenance_log_universe_definition_sha256_hex
                CHECK (universe_definition_sha256 ~ '^[a-f0-9]{{64}}$'),
            CONSTRAINT ck_atlas_provenance_log_code_commit_sha_non_empty
                CHECK (length(code_commit_sha) > 0)
        );
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_provenance_log_ts_desc
        ON {_SCHEMA}.atlas_provenance_log (ts DESC);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_provenance_log_output_table_ts_desc
        ON {_SCHEMA}.atlas_provenance_log (output_table, ts DESC);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_provenance_log_run_type_ts_desc
        ON {_SCHEMA}.atlas_provenance_log (run_type, ts DESC);
        """
    )

    # Write-once trigger function — CREATE OR REPLACE is idempotent.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION atlas.deny_update_delete_provenance()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'atlas_provenance_log is write-once; UPDATE/DELETE not permitted (tg_op=%)',
                TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    # Drop trigger before recreating so IF NOT EXISTS is not needed (not available in old PG).
    op.execute(
        """
        DROP TRIGGER IF EXISTS deny_update_delete_atlas_provenance_log
        ON atlas.atlas_provenance_log;
        """
    )
    op.execute(
        """
        CREATE TRIGGER deny_update_delete_atlas_provenance_log
        BEFORE UPDATE OR DELETE ON atlas.atlas_provenance_log
        FOR EACH ROW EXECUTE FUNCTION atlas.deny_update_delete_provenance();
        """
    )

    # Retroactive FK: atlas_ledger.provenance_log_id → atlas_provenance_log.run_id
    _add_fk_if_not_exists(
        fk_name="fk_atlas_ledger_provenance_log_id",
        source_table="atlas_ledger",
        source_col="provenance_log_id",
        target_table="atlas_provenance_log",
        target_col="run_id",
        on_delete="SET NULL",
    )
    # Retroactive FK: atlas_macro_features_daily.provenance_log_id → atlas_provenance_log.run_id
    _add_fk_if_not_exists(
        fk_name="fk_atlas_macro_features_daily_provenance_log_id",
        source_table="atlas_macro_features_daily",
        source_col="provenance_log_id",
        target_table="atlas_provenance_log",
        target_col="run_id",
        on_delete="SET NULL",
    )

    # =========================================================================
    # 088 — atlas_drift_event_log + write-once trigger + atlas_drift_action enum
    # =========================================================================
    _create_enum_if_not_exists("atlas_drift_action", "flag", "clear", "deprecate")

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA}.atlas_drift_event_log (
            event_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cell_id                 UUID NOT NULL
                REFERENCES {_SCHEMA}.atlas_cell_definitions (cell_id)
                ON DELETE RESTRICT,
            ts                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            z_score                 NUMERIC(8, 4) NOT NULL,
            realized_window_start   DATE NOT NULL,
            realized_window_end     DATE NOT NULL,
            predicted_excess        NUMERIC(10, 6) NOT NULL,
            sigma_predicted         NUMERIC(10, 6) NOT NULL,
            n_realized              INTEGER NOT NULL,
            status_before           {_SCHEMA}.atlas_drift_status NOT NULL,
            status_after            {_SCHEMA}.atlas_drift_status NOT NULL,
            action                  {_SCHEMA}.atlas_drift_action NOT NULL,
            actor                   VARCHAR(64) NOT NULL DEFAULT 'system',
            provenance_log_id       UUID
                REFERENCES {_SCHEMA}.atlas_provenance_log (run_id)
                ON DELETE SET NULL,
            notes                   TEXT,
            CONSTRAINT ck_atlas_drift_event_log_window_order
                CHECK (realized_window_start <= realized_window_end),
            CONSTRAINT ck_atlas_drift_event_log_n_realized_non_negative
                CHECK (n_realized >= 0)
        );
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_drift_event_log_cell_id_ts_desc
        ON {_SCHEMA}.atlas_drift_event_log (cell_id, ts DESC);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_drift_event_log_ts_desc
        ON {_SCHEMA}.atlas_drift_event_log (ts DESC);
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_atlas_drift_event_log_action_ts_desc
        ON {_SCHEMA}.atlas_drift_event_log (action, ts DESC);
        """
    )

    # Write-once trigger function — CREATE OR REPLACE is idempotent.
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
        DROP TRIGGER IF EXISTS deny_update_delete_atlas_drift_event_log
        ON atlas.atlas_drift_event_log;
        """
    )
    op.execute(
        """
        CREATE TRIGGER deny_update_delete_atlas_drift_event_log
        BEFORE UPDATE OR DELETE ON atlas.atlas_drift_event_log
        FOR EACH ROW EXECUTE FUNCTION atlas.deny_update_delete_drift_event();
        """
    )


# ---------------------------------------------------------------------------
# downgrade — drop in reverse dependency order
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # =========================================================================
    # 088 — remove drift_event_log
    # =========================================================================
    op.execute(
        """
        DROP TRIGGER IF EXISTS deny_update_delete_atlas_drift_event_log
        ON atlas.atlas_drift_event_log;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS atlas.deny_update_delete_drift_event();")

    op.execute(
        f"""
        DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_drift_event_log_action_ts_desc;
        """
    )
    op.execute(
        f"""
        DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_drift_event_log_ts_desc;
        """
    )
    op.execute(
        f"""
        DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_drift_event_log_cell_id_ts_desc;
        """
    )

    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_drift_event_log;")

    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'atlas_drift_action' AND n.nspname = '{_SCHEMA}'
            ) THEN
                DROP TYPE {_SCHEMA}.atlas_drift_action;
            END IF;
        END
        $$;
        """
    )

    # =========================================================================
    # 087 — remove provenance_log + retro FKs
    # =========================================================================
    # Drop retro FKs first (they reference atlas_provenance_log).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE c.conname = 'fk_atlas_macro_features_daily_provenance_log_id'
                  AND t.relname = 'atlas_macro_features_daily'
                  AND n.nspname = '{_SCHEMA}'
            ) THEN
                ALTER TABLE {_SCHEMA}.atlas_macro_features_daily
                DROP CONSTRAINT fk_atlas_macro_features_daily_provenance_log_id;
            END IF;
        END
        $$;
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE c.conname = 'fk_atlas_ledger_provenance_log_id'
                  AND t.relname = 'atlas_ledger'
                  AND n.nspname = '{_SCHEMA}'
            ) THEN
                ALTER TABLE {_SCHEMA}.atlas_ledger
                DROP CONSTRAINT fk_atlas_ledger_provenance_log_id;
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS deny_update_delete_atlas_provenance_log
        ON atlas.atlas_provenance_log;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS atlas.deny_update_delete_provenance();")

    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_provenance_log_run_type_ts_desc;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_provenance_log_output_table_ts_desc;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_provenance_log_ts_desc;"
    )

    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_provenance_log;")

    # =========================================================================
    # 086 — remove macro tables
    # =========================================================================
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_macro_recommendation_daily_regime_state;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_macro_recommendation_daily_date_desc;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_macro_features_daily_date_desc;"
    )
    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_macro_recommendation_daily;")
    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_macro_features_daily;")

    # =========================================================================
    # 085 — remove ETF + MF tables + new enums
    # =========================================================================
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.uq_atlas_mf_switch_rules_category_active;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_mf_recommendation_daily_category_date;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_mf_recommendation_daily_iid_date;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_mf_recommendation_daily_date_reco;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_etf_signal_calls_open;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_etf_signal_calls_cell_date;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_etf_signal_calls_iid_date;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_etf_signal_calls_date_action_tier;"
    )

    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_mf_switch_rules;")
    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_mf_recommendation_daily;")
    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_etf_signal_calls;")

    for enum_name in ("atlas_mf_recommendation", "atlas_mf_quartile", "atlas_etf_sub_category"):
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_type t
                    JOIN pg_namespace n ON n.oid = t.typnamespace
                    WHERE t.typname = '{enum_name}' AND n.nspname = '{_SCHEMA}'
                ) THEN
                    DROP TYPE {_SCHEMA}.{enum_name};
                END IF;
            END
            $$;
            """
        )

    # =========================================================================
    # 084 — remove paper_portfolio + user_lots + RLS
    # =========================================================================
    op.execute(
        f"DROP POLICY IF EXISTS user_lots_user_isolation ON {_SCHEMA}.atlas_user_lots;"
    )
    op.execute(
        f"DROP POLICY IF EXISTS paper_portfolio_user_isolation ON {_SCHEMA}.atlas_paper_portfolio;"
    )
    op.execute(f"ALTER TABLE {_SCHEMA}.atlas_user_lots DISABLE ROW LEVEL SECURITY;")
    op.execute(
        f"ALTER TABLE {_SCHEMA}.atlas_paper_portfolio DISABLE ROW LEVEL SECURITY;"
    )

    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_user_lots_user_instrument;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_paper_portfolio_exit_date;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_paper_portfolio_entry_date;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_paper_portfolio_signal_call_id;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_paper_portfolio_user_open;"
    )

    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_user_lots;")
    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_paper_portfolio;")

    # =========================================================================
    # 083 — remove ledger + view
    # =========================================================================
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
    op.execute(f"DROP VIEW IF EXISTS {_SCHEMA}.atlas_ledger_public;")
    op.execute(f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_ledger_status;")
    op.execute(f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_ledger_realized_at;")
    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_ledger;")

    # =========================================================================
    # 082 — remove brief_cache
    # =========================================================================
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_brief_cache_active;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_brief_cache_signal_call_id;"
    )
    op.execute(
        f"DROP INDEX IF EXISTS {_SCHEMA}.ix_atlas_brief_cache_valid_until;"
    )
    op.execute(f"DROP TABLE IF EXISTS {_SCHEMA}.atlas_brief_cache;")
