"""Close compute gaps: add state machinery to global_atlas and us_atlas.

Changes:
- global_atlas.atlas_etf_metrics_daily: add extension_pct, avg_volume_20,
  vol_ratio_63, volume_expansion, effort_ratio_63
- us_atlas.atlas_etf_metrics_daily: add volume_expansion, effort_ratio_63
- us_atlas.atlas_etf_states_daily: add rs_state, volume_state, compute_run_id
- global_atlas.atlas_etf_states_daily: CREATE (was missing entirely)
- Seed state thresholds into both schemas (momentum, risk, volume, RS classify)

Revision ID: 059
Revises: 058
Create Date: 2026-05-13
"""

from alembic import op

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # global_atlas.atlas_etf_metrics_daily — add missing primitive columns
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE global_atlas.atlas_etf_metrics_daily
            ADD COLUMN IF NOT EXISTS extension_pct    NUMERIC(10, 8),
            ADD COLUMN IF NOT EXISTS avg_volume_20    NUMERIC(20, 2),
            ADD COLUMN IF NOT EXISTS vol_ratio_63     NUMERIC(10, 8),
            ADD COLUMN IF NOT EXISTS volume_expansion NUMERIC(10, 8),
            ADD COLUMN IF NOT EXISTS effort_ratio_63  NUMERIC(10, 8)
    """)

    # ------------------------------------------------------------------
    # us_atlas.atlas_etf_metrics_daily — add volume analysis columns
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE us_atlas.atlas_etf_metrics_daily
            ADD COLUMN IF NOT EXISTS volume_expansion NUMERIC(10, 8),
            ADD COLUMN IF NOT EXISTS effort_ratio_63  NUMERIC(10, 8)
    """)

    # ------------------------------------------------------------------
    # us_atlas.atlas_etf_states_daily — add missing state columns
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE us_atlas.atlas_etf_states_daily
            ADD COLUMN IF NOT EXISTS rs_state      VARCHAR(30),
            ADD COLUMN IF NOT EXISTS volume_state  VARCHAR(30),
            ADD COLUMN IF NOT EXISTS compute_run_id UUID
    """)

    # ------------------------------------------------------------------
    # global_atlas.atlas_etf_states_daily — create (was missing entirely)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS global_atlas.atlas_etf_states_daily (
            ticker              VARCHAR(20)     NOT NULL,
            date                DATE            NOT NULL,
            rs_state            VARCHAR(30),
            momentum_state      VARCHAR(30),
            risk_state          VARCHAR(30),
            volume_state        VARCHAR(30),
            history_gate_pass   BOOLEAN,
            liquidity_gate_pass BOOLEAN,
            weinstein_gate_pass BOOLEAN,
            compute_run_id      UUID,
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticker, date)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_global_etf_states_date "
        "ON global_atlas.atlas_etf_states_daily (date)"
    )

    # ------------------------------------------------------------------
    # Seed state thresholds — us_atlas
    # All state classifiers (momentum / risk / volume / RS) need these.
    # Values calibrated to India production; may be tuned per-schema later.
    # ------------------------------------------------------------------
    _THRESHOLD_ROWS_US = [
        ("rs_quintile_top", 0.80, "rs", "RS pctile above which = Leader/Strong", None, "ratio", 0.60, 0.95, 0.80),
        ("rs_quintile_bottom", 0.20, "rs", "RS pctile below which = Laggard/Weak", None, "ratio", 0.05, 0.40, 0.20),
        ("momentum_flat_band_pct", 0.02, "momentum", "EMA10 within 2pct of 1.0 = Flat", None, "ratio", 0.01, 0.05, 0.02),
        ("momentum_ema_convergence_pct", 0.01, "momentum", "EMA10-EMA20 within 1pct = converged", None, "ratio", 0.005, 0.03, 0.01),
        ("risk_extension_low_max_pct", 25.0, "risk", "Extension below 25pct = Low risk", None, "pct", 10.0, 40.0, 25.0),
        ("risk_extension_high_min_pct", 40.0, "risk", "Extension above 40pct = High risk", None, "pct", 25.0, 60.0, 40.0),
        ("risk_vol_ratio_low_max", 1.0, "risk", "Vol ratio below 1.0 = Low volatility", None, "ratio", 0.5, 1.5, 1.0),
        ("risk_vol_ratio_normal_max", 1.25, "risk", "Vol ratio below 1.25 = Normal volatility", None, "ratio", 1.0, 1.75, 1.25),
        ("risk_vol_ratio_high_min", 1.6, "risk", "Vol ratio above 1.6 = High volatility", None, "ratio", 1.25, 2.5, 1.6),
        ("volume_accumulation_expansion_min", 1.2, "volume", "Vol expansion >= 1.2 = Accumulation", None, "ratio", 1.0, 1.5, 1.2),
        ("volume_accumulation_effort_min", 1.3, "volume", "Effort ratio >= 1.3 = Accumulation", None, "ratio", 1.0, 1.8, 1.3),
        ("volume_distribution_effort_max", 0.8, "volume", "Effort ratio <= 0.8 = Distribution", None, "ratio", 0.5, 1.0, 0.8),
        ("volume_heavy_distribution_effort_max", 0.6, "volume", "Effort ratio <= 0.6 = Heavy Distribution", None, "ratio", 0.3, 0.8, 0.6),
    ]
    for row in _THRESHOLD_ROWS_US:
        key, val, cat, desc, _, units, mn, mx, dflt = row
        op.execute(
            f"INSERT INTO us_atlas.atlas_thresholds "  # noqa: S608 -- no user input
            f"(threshold_key, threshold_value, category, description, methodology_section, "
            f"units, min_allowed, max_allowed, default_value) "
            f"VALUES ('{key}', {val}, '{cat}', '{desc}', NULL, '{units}', {mn}, {mx}, {dflt}) "
            f"ON CONFLICT (threshold_key) DO NOTHING"
        )

    # ------------------------------------------------------------------
    # Seed state thresholds — global_atlas
    # ------------------------------------------------------------------
    _THRESHOLD_ROWS_GLOBAL = [
        *_THRESHOLD_ROWS_US,
        ("liquidity_gate_min_avg_vol", 10000, "gate", "Min 20-day avg volume (shares)", None, "shares", 1000, 100000, 10000),
    ]
    for row in _THRESHOLD_ROWS_GLOBAL:
        key, val, cat, desc, _, units, mn, mx, dflt = row
        op.execute(
            f"INSERT INTO global_atlas.atlas_thresholds "  # noqa: S608 -- no user input
            f"(threshold_key, threshold_value, category, description, methodology_section, "
            f"units, min_allowed, max_allowed, default_value) "
            f"VALUES ('{key}', {val}, '{cat}', '{desc}', NULL, '{units}', {mn}, {mx}, {dflt}) "
            f"ON CONFLICT (threshold_key) DO NOTHING"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS global_atlas.atlas_etf_states_daily")
    op.execute("""
        ALTER TABLE us_atlas.atlas_etf_states_daily
            DROP COLUMN IF EXISTS rs_state,
            DROP COLUMN IF EXISTS volume_state,
            DROP COLUMN IF EXISTS compute_run_id
    """)
    op.execute("""
        ALTER TABLE us_atlas.atlas_etf_metrics_daily
            DROP COLUMN IF EXISTS volume_expansion,
            DROP COLUMN IF EXISTS effort_ratio_63
    """)
    op.execute("""
        ALTER TABLE global_atlas.atlas_etf_metrics_daily
            DROP COLUMN IF EXISTS extension_pct,
            DROP COLUMN IF EXISTS avg_volume_20,
            DROP COLUMN IF EXISTS vol_ratio_63,
            DROP COLUMN IF EXISTS volume_expansion,
            DROP COLUMN IF EXISTS effort_ratio_63
    """)
