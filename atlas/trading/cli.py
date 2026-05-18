"""atlas-lab CLI entry point.

Subcommands:
  backtest     Run V5 baseline backtest against the live DB
  discover     Compute IC for V5 candidate signals
  goal-post    Check goal-post status against the live leaderboard
  states       State classifier subcommands (classify)

Designed to replace the /tmp/baseline_v5_*.py scripts. Pulls universe + regime
from the same atlas.atlas_stock_metrics_daily + atlas.atlas_market_regime_daily
tables used in production.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from atlas.trading.cli_states import (
    _apply_dwell_and_urgency,
    _states_baselines_refresh_cmd,
    _states_tune_cmd,
)
from atlas.trading.lab import run_baseline_v5

log = structlog.get_logger()


_STRATEGY_CONFIGS = {
    "v5": {"weighting": "equal", "trend_filter": False},
    "v5-rp": {"weighting": "inverse_vol", "trend_filter": False},
    "v5-trend": {"weighting": "equal", "trend_filter": True},
    "v5-rp-trend": {"weighting": "inverse_vol", "trend_filter": True},
}


def _load_data(
    start: date, end: date, universe: str = "stocks_nifty500"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load metrics + regime DataFrames from the live DB.

    Universes:
      stocks_nifty500     — public.de_equity_ohlcv + atlas.atlas_stock_metrics_daily
      etfs_indian         — public.de_etf_ohlcv (ret_12m + realized_vol computed on-the-fly)
      mf_equity_largecap  — DEFERRED. Needs per-fund benchmark mapping
                            (atlas_universe_funds.benchmark_code differs per scheme)
                            and a 252d default horizon, not the 63d default. The lab's
                            "compare against a single Nifty 500 benchmark" approach
                            doesn't apply to MFs — funds compete within categories,
                            not against a broad index. Tracked as Chunk 7-followup.
    """
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise SystemExit("ATLAS_DB_URL is not set. Source .env first.")
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)

    with eng.connect() as c:
        if universe == "etfs_indian":
            # ETF data: ticker is the natural key; convert to instrument_id-like
            # string so the rest of the lab pipeline is universe-agnostic.
            metrics = pd.read_sql(
                text("""
                SELECT p.ticker AS instrument_id, p.date,
                       p.close, p.high, p.low,
                       NULL::numeric AS ret_12m,
                       NULL::numeric AS realized_vol_63
                FROM public.de_etf_ohlcv p
                WHERE p.date BETWEEN :s AND :e
                  AND p.close IS NOT NULL
            """),
                c,
                params={"s": start, "e": end},
            )
            # ret_12m + realized_vol_63 computed on-the-fly from close (no metrics table)
            metrics["date"] = pd.to_datetime(metrics["date"])
            metrics = metrics.sort_values(["instrument_id", "date"]).reset_index(drop=True)
            metrics["ret_12m"] = metrics.groupby("instrument_id")["close"].pct_change(252)
            # 63-day realized vol = stdev of daily log returns × sqrt(252)
            log_ret = (
                metrics.groupby("instrument_id")["close"]
                .apply(lambda s: pd.Series(np.log(s / s.shift(1)).rolling(63).std() * np.sqrt(252)))
                .reset_index(drop=True)
            )
            metrics["realized_vol_63"] = log_ret
        else:
            metrics = pd.read_sql(
                text("""
                SELECT m.instrument_id::text AS instrument_id, m.date,
                       COALESCE(p.close_adj, p.close) AS close,
                       p.high, p.low, p.volume,
                       m.ret_12m, m.realized_vol_63
                FROM atlas.atlas_stock_metrics_daily m
                JOIN public.de_equity_ohlcv p
                    ON p.instrument_id=m.instrument_id AND p.date=m.date
                WHERE m.date BETWEEN :s AND :e
                  AND COALESCE(p.close_adj, p.close) IS NOT NULL
            """),
                c,
                params={"s": start, "e": end},
            )
        regime = pd.read_sql(
            text("""
            SELECT date, nifty500_close
            FROM atlas.atlas_market_regime_daily
            WHERE date BETWEEN :s AND :e
        """),
            c,
            params={"s": start, "e": end},
        )
    return metrics, regime


def _backtest_cmd(args: argparse.Namespace) -> int:
    cfg = _STRATEGY_CONFIGS.get(args.strategy)
    if cfg is None:
        log.error("unknown_strategy", strategy=args.strategy, available=list(_STRATEGY_CONFIGS))
        return 1

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    log.info("loading_data", start=start.isoformat(), end=end.isoformat(), universe=args.universe)
    metrics, regime = _load_data(start, end, args.universe)
    log.info("data_loaded", rows=len(metrics))

    result = run_baseline_v5(
        metrics,
        regime,
        top_n=args.top_n,
        rebalance_days=args.rebalance_days,
        weighting=str(cfg["weighting"]),  # type: ignore[arg-type]
        trend_filter=bool(cfg["trend_filter"]),
    )

    output = {
        "strategy_name": result.strategy_name,
        "alpha_oos": result.alpha_oos,
        "port_annual_return": result.port_annual_return,
        "bench_annual_return": result.bench_annual_return,
        "port_max_drawdown": result.port_max_drawdown,
        "bench_max_drawdown": result.bench_max_drawdown,
        "hit_rate": result.hit_rate,
        "information_ratio": result.information_ratio,
        "alpha_t_stat": result.alpha_t_stat,
        "n_periods": result.n_periods,
        "n_trades": result.n_trades,
        "yearly": result.yearly,
    }
    if args.format == "json":
        print(json.dumps(output, indent=2, default=str))
    else:
        print(f"=== {result.strategy_name} ===")
        print(f"  alpha_oos:        {result.alpha_oos:+.2%}")
        print(f"  port annual:      {result.port_annual_return:+.2%}")
        print(f"  bench annual:     {result.bench_annual_return:+.2%}")
        print(f"  port max DD:      {result.port_max_drawdown:.2%}")
        print(f"  bench max DD:     {result.bench_max_drawdown:.2%}")
        print(f"  hit rate:         {result.hit_rate:.1%}")
        print(f"  IR:               {result.information_ratio:+.3f}")
        print(f"  alpha t-stat:     {result.alpha_t_stat:+.2f}")
        print(f"  periods:          {result.n_periods}  trades: {result.n_trades}")
        print()
        print("=== YEARLY (alpha / DD vs bench DD) ===")
        for y in result.yearly:
            mark_a = "+" if y["alpha"] > 0 else "-"
            mark_d = "+" if y["max_drawdown"] <= y["benchmark_max_drawdown"] else "-"
            print(
                f"  {y['year']}: alpha {y['alpha']:+.2%} {mark_a}  "
                f"DD {y['max_drawdown']:.2%} vs {y['benchmark_max_drawdown']:.2%} {mark_d}"
            )
    return 0


def _discover_cmd(args: argparse.Namespace) -> int:
    """Compute IC/IR/Q5-Q1 for each candidate V5 signal and persist to atlas_signal_ic.

    Reuses atlas/intelligence/validation/{forward_returns, ic_engine, persistence}.
    Reuses atlas/trading/data_loader.compute_* for signal computation.
    """
    from atlas.intelligence.validation.forward_returns import (
        compute_forward_returns,
        load_price_matrix,
    )
    from atlas.intelligence.validation.ic_engine import compute_ic_over_window
    from atlas.intelligence.validation.persistence import persist_ic_result
    from atlas.trading.data_loader import (
        compute_beta_alpha_63d,
        compute_mom_low_vol,
        compute_natr_14,
    )

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    horizon = int(args.horizon)

    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise SystemExit("ATLAS_DB_URL is not set")
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)

    log.info("loading_prices", start=str(start), end=str(end))
    prices_wide = load_price_matrix(eng, start_date=start, end_date=end)
    if prices_wide.empty:
        log.error("no_price_data", start=str(start), end=str(end))
        return 1

    fwd = compute_forward_returns(prices_wide, periods=[horizon])
    returns_wide = fwd[f"return_{horizon}d"]

    metrics, _regime_unused = _load_data(start, end, args.universe)
    df = metrics.sort_values(["date", "instrument_id"])
    instruments = sorted(df["instrument_id"].unique())
    dates_list = sorted(df["date"].unique())

    def _pivot(col: str) -> np.ndarray:  # type: ignore[name-defined]
        import numpy as np

        pivoted = df.pivot(index="instrument_id", columns="date", values=col)
        return pivoted.reindex(index=instruments, columns=dates_list).values.astype(np.float32)

    close = _pivot("close")
    high = _pivot("high")
    low = _pivot("low")
    ret_12m = _pivot("ret_12m")
    realized_vol = _pivot("realized_vol_63")

    with eng.connect() as c:
        n500 = pd.read_sql(
            text("""
            SELECT date, nifty500_close FROM atlas.atlas_market_regime_daily
            WHERE date BETWEEN :s AND :e ORDER BY date
        """),
            c,
            params={"s": start, "e": end},
        )
    n500["date"] = pd.to_datetime(n500["date"])
    n500 = n500.set_index("date").reindex(pd.to_datetime(dates_list)).ffill().bfill()
    import numpy as np

    n500_arr = n500["nifty500_close"].astype(np.float64).to_numpy()

    signals = {
        "natr_14": compute_natr_14(high, low, close),
        "beta_alpha_63d": compute_beta_alpha_63d(close, n500_arr),
        "mom_low_vol": compute_mom_low_vol(ret_12m, realized_vol),
    }

    out = []
    for name, signal_arr in signals.items():
        factor_long = (
            pd.DataFrame(signal_arr.T, index=pd.to_datetime(dates_list), columns=instruments)
            .stack()
            .to_frame("factor")
        )
        factor_long.index = factor_long.index.set_names(["date", "instrument_id"])

        result = compute_ic_over_window(factor_long, returns_wide)
        log.info(
            "ic_computed",
            signal=name,
            mean_ic=result.mean_ic,
            ic_std=result.ic_std,
            n=result.n_observations,
        )

        persist_ic_result(
            eng,
            signal_name=name,
            timeframe="daily",
            forward_period_days=horizon,
            rolling_window="full",
            as_of=end,
            result=result,
            quantile_spread_ann=0.0,
            turnover_monthly=0.0,
        )
        out.append(
            {
                "signal": name,
                "mean_ic": result.mean_ic,
                "ic_std": result.ic_std,
                "ic_t_stat": result.ic_t_stat,
                "ic_ir": (result.mean_ic / result.ic_std) if result.ic_std > 0 else 0.0,
                "n_observations": result.n_observations,
            }
        )

    print(
        json.dumps(
            {"horizon_days": horizon, "as_of": str(end), "signals": out}, indent=2, default=str
        )
    )
    return 0


def _compute_features_for_stock(g: pd.DataFrame) -> pd.DataFrame:
    """Compute the 18 feature columns the classifier needs for one stock's OHLCV.

    Input: DataFrame with columns instrument_id, date, close, high, low,
    volume (plus optional ret_12m, realized_vol_63).
    Output: DataFrame with all feature columns the classifier needs, indexed
    by the same row order. NaN where the rolling window is not yet full.
    """
    from atlas.intelligence.states.features import (
        atr_14 as calc_atr_14,
    )
    from atlas.intelligence.states.features import (
        distribution_days_25d,
        slope,
        sma,
    )

    g = g.sort_values("date").reset_index(drop=True)
    out = g[["instrument_id", "date", "close"]].copy()
    out["sma_50"] = sma(g["close"], 50)
    out["sma_150"] = sma(g["close"], 150)
    out["sma_200"] = sma(g["close"], 200)
    out["sma_50_slope"] = slope(g["close"], 50)
    out["sma_150_slope"] = slope(g["close"], 150)
    out["sma_200_slope"] = slope(g["close"], 30)  # theta_slope_days=30
    out["atr_14"] = calc_atr_14(g["high"], g["low"], g["close"])
    out["atr_14_50d_avg"] = out["atr_14"].rolling(50, min_periods=50).mean()

    vol_col = (
        g["volume"] if "volume" in g.columns else pd.Series([float("nan")] * len(g), index=g.index)
    )
    out["volume"] = vol_col
    out["volume_50d_avg"] = vol_col.rolling(50, min_periods=50).mean()
    # Exclude today from the 60d max so the breakout rule
    # "close >= theta_base_breakout * max_close_60d" can fire when today
    # makes a new high. Including today made the rule trivially false for
    # quiet-grinder uptrends (today == max → close >= 1.02×close is impossible).
    out["max_close_60d"] = g["close"].shift(1).rolling(60, min_periods=60).max()
    out["distribution_days_25d"] = distribution_days_25d(g["close"], vol_col).fillna(0)
    out["distribution_days_5d"] = (
        ((g["close"].pct_change() <= -0.002) & (vol_col > vol_col.shift(1)))
        .rolling(5, min_periods=1)
        .sum()
        .fillna(0)
        .astype("Int64")
    )

    # Raw 12m return; cross-sectional rank computed at panel level.
    out["ret_12m_raw"] = g["close"] / g["close"].shift(252) - 1

    # Days since most recent 252d rolling low.
    rolling_min = g["close"].rolling(252, min_periods=252).min()
    is_low = (g["close"] == rolling_min).astype(int)
    idx_series = pd.Series(range(len(g)))
    last_low_idx = idx_series.where(is_low.eq(1)).ffill().fillna(0).astype(int)
    out["low_252_age_days"] = (idx_series - last_low_idx).astype("Int64")

    # 50d avg ₹ volume as liquidity proxy.
    out["liquidity_score"] = (g["close"] * vol_col).rolling(50, min_periods=50).mean()
    out["data_gap_count"] = 0  # Phase 1 placeholder
    return out


def _states_classify_cmd(args: argparse.Namespace) -> int:
    """Compute V1 state classification for the date range and persist to DB."""
    from datetime import timedelta

    from atlas.intelligence.states.classifier import classify_state_panel
    from atlas.intelligence.states.persistence import persist_state_panel
    from atlas.intelligence.states.thresholds import load_active_thresholds

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    fetch_start = start - timedelta(days=400)

    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise SystemExit("ATLAS_DB_URL is not set. Source .env first.")
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)

    thresholds = load_active_thresholds(eng)
    log.info(
        "states_classify_start",
        start=str(start),
        end=str(end),
        n_thresholds=len(thresholds),
    )

    metrics, _regime = _load_data(fetch_start, end, args.universe)
    log.info("states_classify_loaded_data", rows=len(metrics))
    if metrics.empty:
        log.error("no_data", start=str(fetch_start), end=str(end))
        return 1

    # Compute features per stock over the full lookback window.
    feature_dfs = []
    for _iid, group in metrics.groupby("instrument_id"):
        feature_dfs.append(_compute_features_for_stock(group))
    features = pd.concat(feature_dfs, ignore_index=True)

    # Cross-sectional rs_rank_12m: rank ret_12m_raw within each date cohort.
    features["rs_rank_12m"] = features.groupby("date")["ret_12m_raw"].rank(pct=True).fillna(0.5)

    # Filter to the target date range before classification.
    features["date"] = pd.to_datetime(features["date"]).dt.date
    features = features[features["date"].between(start, end)].reset_index(drop=True)
    if features.empty:
        log.error("no_features_in_window", start=str(start), end=str(end))
        return 1

    log.info("states_classify_classifying", rows=len(features))
    panel = classify_state_panel(features, thresholds, args.classifier_version)

    panel = _apply_dwell_and_urgency(panel, eng)

    n = persist_state_panel(eng, panel)
    log.info("states_classify_persisted", n_rows=n)
    print(
        f"States classified: {n} rows persisted with"
        f" classifier_version={args.classifier_version}"
    )
    return 0


def _goal_post_cmd(args: argparse.Namespace) -> int:
    """Read live leaderboard + validation, print pass/fail JSON for the goal post."""
    from atlas.trading.goal_post import check_goal_post

    result = check_goal_post(rank=args.rank)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["met"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas-lab", description="Atlas Strategy Lab CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", help="Run V5 baseline backtest")
    bt.add_argument(
        "--strategy", required=True, choices=list(_STRATEGY_CONFIGS), help="Strategy variant"
    )
    bt.add_argument("--start", required=True, help="ISO date YYYY-MM-DD")
    bt.add_argument("--end", required=True, help="ISO date YYYY-MM-DD")
    bt.add_argument(
        "--universe", default="stocks_nifty500", help="Universe id (currently only stocks_nifty500)"
    )
    bt.add_argument("--top-n", type=int, default=20, help="Top-N cohort size")
    bt.add_argument("--rebalance-days", type=int, default=21, help="Hold period")
    bt.add_argument("--format", choices=("text", "json"), default="text")
    bt.set_defaults(func=_backtest_cmd)

    disc = sub.add_parser("discover", help="Compute IC for V5 candidate signals and persist")
    disc.add_argument("--universe", default="stocks_nifty500")
    disc.add_argument("--start", required=True, help="ISO date YYYY-MM-DD")
    disc.add_argument("--end", required=True, help="ISO date YYYY-MM-DD")
    disc.add_argument("--horizon", type=int, default=63, help="Forward-return horizon in days")
    disc.set_defaults(func=_discover_cmd)

    gp = sub.add_parser("goal-post", help="Check goal-post status from live DB")
    gp.add_argument("--rank", type=int, default=1, help="Leaderboard rank to evaluate")
    gp.set_defaults(func=_goal_post_cmd)

    states_p = sub.add_parser("states", help="State classifier subcommands")
    states_sub = states_p.add_subparsers(dest="states_cmd", required=True)
    states_classify = states_sub.add_parser("classify", help="Compute V1 state classification")
    states_classify.add_argument("--start", required=True, help="ISO date YYYY-MM-DD")
    states_classify.add_argument("--end", required=True, help="ISO date YYYY-MM-DD")
    states_classify.add_argument("--universe", default="stocks_nifty500")
    states_classify.add_argument("--classifier-version", default="v1.0")
    states_classify.set_defaults(func=_states_classify_cmd)

    states_baselines = states_sub.add_parser(
        "baselines-refresh", help="Recompute cohort dwell baselines"
    )
    states_baselines.set_defaults(func=_states_baselines_refresh_cmd)

    states_tune = states_sub.add_parser(
        "tune", help="IC-tune state-engine thresholds against forward returns"
    )
    states_tune.add_argument("--start", required=True, help="ISO date YYYY-MM-DD")
    states_tune.add_argument("--end", required=True, help="ISO date YYYY-MM-DD")
    states_tune.add_argument(
        "--as-of",
        default=None,
        help="As-of date for persisted threshold row; defaults to --end",
    )
    states_tune.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute IC and report optimal values without persisting to DB",
    )
    states_tune.add_argument("--format", choices=("text", "json"), default="text")
    states_tune.set_defaults(func=_states_tune_cmd)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
