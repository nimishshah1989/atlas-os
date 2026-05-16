from datetime import date, timedelta

import numpy as np
import pandas as pd

from atlas.trading.config import PortfolioConfig
from atlas.trading.genome import GenomeFactory
from atlas.trading.simulator import SimResult, simulate_genome


def _synthetic_df(n_stocks=5, n_days=120) -> pd.DataFrame:
    """Minimal metrics DataFrame matching atlas_stock_metrics_daily schema."""
    dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(n_days)]
    records = []
    rng = np.random.default_rng(42)
    for s in range(n_stocks):
        prices = 100.0 * np.cumprod(1 + rng.normal(0.0005, 0.02, n_days))
        for d_idx, d in enumerate(dates):
            records.append(
                {
                    "instrument_id": s + 1,
                    "date": d,
                    "close": prices[d_idx],
                    "rs_pctile_1w": rng.uniform(0, 1),
                    "rs_pctile_1m": rng.uniform(0, 1),
                    "rs_pctile_3m": rng.uniform(0, 1),
                    "vol_ratio_63": rng.uniform(0.8, 2.2),
                    "ema_20_ratio": rng.uniform(0.97, 1.04),
                }
            )
    return pd.DataFrame(records)


def _regime_df(n_days=120) -> pd.DataFrame:
    """Minimal regime DataFrame matching atlas_market_regime_daily schema."""
    dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(n_days)]
    rng = np.random.default_rng(99)
    return pd.DataFrame(
        [
            {
                "date": d,
                "pct_above_ema_50": rng.uniform(0.30, 0.80),
                "india_vix": rng.uniform(12, 25),
            }
            for d in dates
        ]
    )


def test_simulate_genome_returns_sim_result():
    genome = GenomeFactory.random()
    config = PortfolioConfig()
    df = _synthetic_df()
    rdf = _regime_df()

    start = date(2023, 1, 1)
    split = date(2023, 3, 1)
    end = date(2023, 4, 30)
    windows = [(start, split, split, end)]

    result = simulate_genome(genome, df, rdf, config, windows)

    assert isinstance(result, SimResult)
    assert isinstance(result.sortino_oos, float)
    assert isinstance(result.calmar_oos, float)
    assert isinstance(result.total_trades, int)
    assert result.total_trades >= 0
    assert not np.isnan(result.sortino_oos) or result.sortino_oos == 0.0
    assert isinstance(result.sortino_insample, float)
    assert isinstance(result.max_drawdown, float)
    assert isinstance(result.turnover_pct, float)
    assert result.equity_curve_oos is None or isinstance(result.equity_curve_oos, pd.Series)


def test_simulate_genome_risk_off_full_liquidbees():
    """When regime is always Risk-Off, genome should make zero equity trades."""
    genome = GenomeFactory.random()
    # Set breadth thresholds impossibly high but maintain ordering constraint
    # Layer1Perception.__post_init__ requires risk_on > constructive > cautious
    genome.layer1.regime_risk_on_breadth_pct = 97
    genome.layer1.regime_constructive_breadth_pct = 96
    genome.layer1.regime_cautious_breadth_pct = 95

    config = PortfolioConfig()
    df = _synthetic_df()
    rdf = _regime_df()

    start = date(2023, 1, 1)
    split = date(2023, 3, 1)
    end = date(2023, 4, 30)
    result = simulate_genome(genome, df, rdf, config, [(start, split, split, end)])

    assert result.total_trades == 0


def test_simulate_genome_missing_cts_columns_uses_safe_defaults():
    """metrics_df without cts_stage/ppc/npc/contraction columns doesn't crash."""
    genome = GenomeFactory.random()
    config = PortfolioConfig()
    # Standard metrics_df WITHOUT any CTS columns (backward compat)
    df = _synthetic_df()
    rdf = _regime_df()

    start = date(2023, 1, 1)
    split = date(2023, 3, 1)
    end = date(2023, 4, 30)
    result = simulate_genome(genome, df, rdf, config, [(start, split, split, end)])

    assert isinstance(result, SimResult)
    assert result.total_trades >= 0


def test_simulate_genome_stage3_produces_no_entries():
    """All Stage 3 stocks produce zero entries when require_stage2_for_entry=True."""
    genome = GenomeFactory.random()
    # Force require_stage2_for_entry to True so only Stage 2 can enter
    object.__setattr__(genome.layer1, "require_stage2_for_entry", True)

    config = PortfolioConfig()
    n_stocks, n_days = 5, 120
    df = _synthetic_df(n_stocks=n_stocks, n_days=n_days)
    rdf = _regime_df(n_days=n_days)

    # Set all cts_stage to 3 — no stock should qualify for entry
    df["cts_stage"] = 3

    start = date(2023, 1, 1)
    split = date(2023, 3, 1)
    end = date(2023, 4, 30)
    result = simulate_genome(genome, df, rdf, config, [(start, split, split, end)])

    assert result.total_trades == 0
