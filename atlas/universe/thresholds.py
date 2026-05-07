"""Atlas threshold catalog seeder.

Seeds ``atlas_thresholds`` with the 35 v0 thresholds from
``docs/04_THRESHOLD_CATALOG.md``. Each insert also records a row in
``atlas_threshold_history`` with ``old_value = NULL`` (the seed insert)
per architecture 5.6.

The catalog values here are the source of truth for v0. Re-running the
seed is idempotent — ON CONFLICT updates ``description``, ``min_allowed``,
``max_allowed`` (catalog-driven metadata) but does NOT change
``threshold_value`` (which the fund manager may have tuned via UI).
"""

from __future__ import annotations

from typing import NamedTuple

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()


class Threshold(NamedTuple):
    key: str
    default: float
    min_allowed: float
    max_allowed: float
    category: str
    methodology_section: str
    units: str
    description: str


# 35 v0 thresholds per `04_THRESHOLD_CATALOG.md`. Values match the catalog's
# Section 1.3 distribution: 2 gates + 2 RS + 3 momentum + 5 risk + 4 volume
# + 1 weinstein + 2 stage1 + 3 sector + 8 regime + 4 fund + 1 decision = 35.
THRESHOLDS: tuple[Threshold, ...] = (
    # --- Pre-classification gates (2) ---
    Threshold(
        "liquidity_min_traded_value_inr",
        50_000_000,
        10_000_000,
        250_000_000,
        "gate",
        "3.3",
        "inr",
        "Minimum trailing 60-day median daily traded value for liquidity gate",
    ),
    Threshold(
        "history_min_trading_days",
        252,
        180,
        504,
        "gate",
        "3.3",
        "days",
        "Minimum trading days of OHLCV history before classification eligibility",
    ),
    # --- RS classification (2) ---
    Threshold(
        "rs_quintile_top",
        0.80,
        0.70,
        0.90,
        "rs",
        "7.1",
        "pctile",
        "Top-quintile cutoff for RS percentile rank within tier",
    ),
    Threshold(
        "rs_quintile_bottom",
        0.20,
        0.10,
        0.30,
        "rs",
        "7.1",
        "pctile",
        "Bottom-quintile cutoff for RS percentile rank within tier",
    ),
    # --- RS momentum classification (3) ---
    Threshold(
        "momentum_flat_band_pct",
        0.02,
        0.01,
        0.05,
        "momentum",
        "7.2",
        "ratio",
        "Maximum |ema_10_ratio - 1| for Flat classification",
    ),
    Threshold(
        "momentum_ema_convergence_pct",
        0.01,
        0.005,
        0.03,
        "momentum",
        "7.2",
        "ratio",
        "Maximum |ema_10_ratio - ema_20_ratio| for Flat (EMAs converged)",
    ),
    Threshold(
        "momentum_breakout_lookback_days",
        20,
        10,
        50,
        "momentum",
        "7.2",
        "days",
        "Lookback window for ema_10 at high/low detection",
    ),
    # --- Risk classification (5) ---
    Threshold(
        "risk_extension_low_max_pct",
        25,
        15,
        35,
        "risk",
        "7.3",
        "percent",
        "Maximum extension % for Low/Normal risk",
    ),
    Threshold(
        "risk_extension_high_min_pct",
        40,
        30,
        60,
        "risk",
        "7.3",
        "percent",
        "Minimum extension % for High risk",
    ),
    Threshold(
        "risk_vol_ratio_low_max",
        1.0,
        0.80,
        1.10,
        "risk",
        "7.3",
        "ratio",
        "Maximum vol_ratio_63 for Low risk",
    ),
    Threshold(
        "risk_vol_ratio_normal_max",
        1.25,
        1.10,
        1.50,
        "risk",
        "7.3",
        "ratio",
        "Maximum vol_ratio_63 for Normal risk",
    ),
    Threshold(
        "risk_vol_ratio_high_min",
        1.6,
        1.4,
        2.0,
        "risk",
        "7.3",
        "ratio",
        "Minimum vol_ratio_63 for High risk",
    ),
    # --- Volume classification (4) ---
    Threshold(
        "volume_accumulation_expansion_min",
        1.2,
        1.05,
        1.5,
        "volume",
        "7.4",
        "ratio",
        "Minimum volume_expansion for Accumulation",
    ),
    Threshold(
        "volume_accumulation_effort_min",
        1.3,
        1.1,
        1.8,
        "volume",
        "7.4",
        "ratio",
        "Minimum effort_ratio_63 for Accumulation",
    ),
    Threshold(
        "volume_distribution_effort_max",
        0.8,
        0.6,
        0.9,
        "volume",
        "7.4",
        "ratio",
        "Maximum effort_ratio_63 for Distribution",
    ),
    Threshold(
        "volume_heavy_distribution_effort_max",
        0.6,
        0.4,
        0.7,
        "volume",
        "7.4",
        "ratio",
        "Maximum effort_ratio_63 for Heavy Distribution",
    ),
    # --- Weinstein gate (1) ---
    Threshold(
        "weinstein_slope_sigma_min",
        -0.5,
        -1.0,
        0.0,
        "gate",
        "7.1",
        "sigma",
        "Minimum 30-week MA slope (σ-normalized) for flat-or-rising condition",
    ),
    # --- Stage-1 base detection (2) ---
    Threshold(
        "stage1_weak_weeks_min",
        8,
        6,
        10,
        "rs",
        "7.1",
        "weeks",
        "Minimum weak-state weeks (out of last 10) for Stage-1 base qualification",
    ),
    Threshold(
        "stage1_ma_flat_sigma_max",
        0.5,
        0.3,
        1.0,
        "rs",
        "7.1",
        "sigma",
        "Maximum |30-week MA slope σ| for flat MA condition in Stage-1 base",
    ),
    # --- Sector classification (3) ---
    Threshold(
        "sector_overweight_participation_min_pct",
        50,
        35,
        70,
        "sector",
        "10.5",
        "percent",
        "Minimum participation_RS for Overweight sector",
    ),
    Threshold(
        "sector_underweight_participation_max_pct",
        30,
        20,
        45,
        "sector",
        "10.5",
        "percent",
        "Maximum participation_RS for Underweight sector",
    ),
    Threshold(
        "sector_avoid_participation_max_pct",
        25,
        15,
        35,
        "sector",
        "10.5",
        "percent",
        "Maximum participation_RS for Avoid sector",
    ),
    # --- Market regime (8) ---
    Threshold(
        "regime_risk_on_breadth_min_pct",
        60,
        50,
        75,
        "regime",
        "11.4",
        "percent",
        "Minimum pct_above_ema_50 for Risk-On regime",
    ),
    Threshold(
        "regime_constructive_breadth_min_pct",
        50,
        40,
        60,
        "regime",
        "11.4",
        "percent",
        "Minimum pct_above_ema_50 for Constructive regime",
    ),
    Threshold(
        "regime_risk_off_breadth_max_pct",
        40,
        25,
        50,
        "regime",
        "11.4",
        "percent",
        "Maximum pct_above_ema_50 for Risk-Off regime",
    ),
    Threshold(
        "regime_risk_on_vix_max",
        18,
        14,
        22,
        "regime",
        "11.4",
        "vix_points",
        "Maximum India VIX for Risk-On regime",
    ),
    Threshold(
        "regime_constructive_vix_max",
        22,
        18,
        28,
        "regime",
        "11.4",
        "vix_points",
        "Maximum India VIX for Constructive regime",
    ),
    Threshold(
        "regime_cautious_vix_max",
        28,
        24,
        35,
        "regime",
        "11.4",
        "vix_points",
        "Maximum India VIX for Cautious regime",
    ),
    Threshold(
        "regime_near_200ema_band_pct",
        2,
        1,
        5,
        "regime",
        "11.4",
        "percent",
        "Width of 'near EMA 200' band for Cautious regime trigger",
    ),
    Threshold(
        "dislocation_vol_multiplier",
        4.0,
        2.5,
        6.0,
        "regime",
        "11.5",
        "ratio",
        "Multiple of 252-day median vol above which dislocation activates",
    ),
    # --- Mutual fund lenses (4) ---
    Threshold(
        "fund_aligned_aum_min_pct",
        70,
        60,
        85,
        "fund",
        "12.2",
        "percent",
        "Minimum AUM in Overweight/Neutral sectors for Aligned",
    ),
    Threshold(
        "fund_avoid_aum_max_pct",
        10,
        5,
        20,
        "fund",
        "12.2",
        "percent",
        "Maximum AUM in Avoid sectors for Aligned",
    ),
    Threshold(
        "fund_strong_holdings_min_pct",
        60,
        50,
        75,
        "fund",
        "12.3",
        "percent",
        "Minimum AUM in Leader/Strong/Emerging stocks for Strong-Holdings",
    ),
    Threshold(
        "fund_weak_holdings_max_pct",
        25,
        15,
        35,
        "fund",
        "12.3",
        "percent",
        "Maximum AUM in Weak/Laggard stocks for Decent classification",
    ),
    # --- Decision engine (1) ---
    Threshold(
        "entry_breakout_proximity_max_pct",
        5,
        2,
        10,
        "decision",
        "13.3",
        "percent",
        "Maximum distance from 20-EMA (%) for breakout entry trigger",
    ),
)


def populate_thresholds(engine: Engine | None = None) -> int:
    """Seed the 35 thresholds. Idempotent — preserves any tuned values.

    On first run: inserts all rows + audit log entries with ``old_value=NULL``.
    On re-run: updates metadata (description, min/max, units, category) but
    keeps ``threshold_value`` as-is (the fund manager may have tuned it).
    """
    eng = engine or get_engine()
    if len(THRESHOLDS) != 35:
        raise AssertionError(f"Threshold catalog has {len(THRESHOLDS)} entries, expected 35")

    insert_threshold_sql = text("""
        INSERT INTO atlas.atlas_thresholds
            (threshold_key, threshold_value, category, description,
             methodology_section, units, min_allowed, max_allowed,
             default_value, last_modified_by, is_active)
        VALUES
            (:key, :default, :category, :description,
             :methodology_section, :units, :min_allowed, :max_allowed,
             :default, 'system', TRUE)
        ON CONFLICT (threshold_key) DO UPDATE SET
            -- Keep tuned threshold_value; update metadata only
            description = EXCLUDED.description,
            methodology_section = EXCLUDED.methodology_section,
            units = EXCLUDED.units,
            min_allowed = EXCLUDED.min_allowed,
            max_allowed = EXCLUDED.max_allowed,
            default_value = EXCLUDED.default_value,
            last_modified_at = NOW()
    """)
    insert_history_sql = text("""
        INSERT INTO atlas.atlas_threshold_history
            (threshold_key, old_value, new_value, changed_by, change_reason,
             triggered_reclassify)
        VALUES (:key, NULL, :new_value, 'system',
                'Initial seed at Atlas-M1', FALSE)
    """)

    inserted = 0
    with eng.begin() as conn:
        # First, find which keys already exist — we only audit-log seed entries
        existing_keys: set[str] = {
            r[0]
            for r in conn.execute(text("SELECT threshold_key FROM atlas.atlas_thresholds")).all()
        }

        for t in THRESHOLDS:
            conn.execute(
                insert_threshold_sql,
                {
                    "key": t.key,
                    "default": t.default,
                    "category": t.category,
                    "description": t.description,
                    "methodology_section": t.methodology_section,
                    "units": t.units,
                    "min_allowed": t.min_allowed,
                    "max_allowed": t.max_allowed,
                },
            )
            if t.key not in existing_keys:
                conn.execute(
                    insert_history_sql,
                    {
                        "key": t.key,
                        "new_value": t.default,
                    },
                )
                inserted += 1

    log.info(
        "thresholds_seeded",
        total_in_catalog=len(THRESHOLDS),
        newly_inserted=inserted,
        already_existed=len(THRESHOLDS) - inserted,
    )
    return len(THRESHOLDS)
