"""Signal validation CLI orchestrator — SP01 Task 8.

Wires: factor loader → price matrix → forward returns → IC engine
       → (optional) persistence → markdown tearsheet.

Usage::

    python scripts/run_signal_validation.py \\
        --signal decision_state \\
        --periods 5,21 \\
        --rolling-window 3M \\
        --start 2024-10-01 \\
        --end 2025-01-31 \\
        --output /tmp/tearsheet.md

Exit codes:
    0 — success
    2 — unsupported signal name
    3 — no data for the requested date range
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.db import get_engine  # noqa: E402
from atlas.intelligence.validation.factor_loader import load_decision_state_factor  # noqa: E402
from atlas.intelligence.validation.forward_returns import (  # noqa: E402
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import (  # noqa: E402
    ICResult,
    compute_ic_over_window,
    compute_quantile_spread,
    compute_turnover,
)
from atlas.intelligence.validation.persistence import persist_ic_result  # noqa: E402
from atlas.intelligence.validation.report import build_tearsheet_markdown  # noqa: E402

log = structlog.get_logger()

_SUPPORTED_SIGNALS = {"decision_state"}

_WINDOW_TRADING_DAYS: dict[str, int] = {
    "3M": 63,
    "6M": 126,
    "12M": 252,
    "24M": 504,
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run SP01 signal validation and emit a markdown tearsheet."
    )
    p.add_argument("--signal", required=True, help="Signal name (currently: decision_state)")
    p.add_argument(
        "--periods",
        required=True,
        help="Comma-separated forward return periods in trading days, e.g. 5,21",
    )
    p.add_argument(
        "--rolling-window",
        default="6M",
        choices=list(_WINDOW_TRADING_DAYS.keys()),
        dest="rolling_window",
        help="Rolling IC window size (default: 6M)",
    )
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD (inclusive)")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD (inclusive)")
    p.add_argument("--output", required=True, help="Path to write markdown tearsheet")
    p.add_argument(
        "--persist",
        action="store_true",
        default=False,
        help="Persist IC results to atlas.atlas_signal_ic (default: off)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # --- validate signal name ---
    if args.signal not in _SUPPORTED_SIGNALS:
        log.error("unsupported_signal", signal=args.signal, supported=list(_SUPPORTED_SIGNALS))
        return 2

    # --- parse args ---
    try:
        periods: list[int] = [int(p.strip()) for p in args.periods.split(",") if p.strip()]
    except ValueError:
        log.error("invalid_periods", raw=args.periods)
        return 2

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    window_days = _WINDOW_TRADING_DAYS[args.rolling_window]
    output_path = Path(args.output)

    log.info(
        "signal_validation_start",
        signal=args.signal,
        periods=periods,
        rolling_window=args.rolling_window,
        window_days=window_days,
        start=args.start,
        end=args.end,
        persist=args.persist,
    )

    engine = get_engine()

    # Trim the load range to the minimum needed for the LATEST rolling window.
    # The user-supplied --start/--end is a search range; the actual IC is
    # computed on the last `window_days` dates within that range. Loading the
    # full multi-year range hits Supabase pooler statement_timeout on heavy
    # joined queries (and is wasteful — we discard everything before the
    # window anyway). Add a safety buffer for non-trading days + max forward
    # period needed for lookahead.
    max_period = max(periods)
    buffer_calendar_days = int((window_days + max_period) * 1.6) + 30
    load_start = max(start_date, end_date - timedelta(days=buffer_calendar_days))
    log.info(
        "load_range_trimmed",
        original_start=str(start_date),
        load_start=str(load_start),
        end=str(end_date),
        buffer_calendar_days=buffer_calendar_days,
    )

    # Step 1: Load factor
    factor = load_decision_state_factor(engine, start_date=load_start, end_date=end_date)
    if factor.empty:
        log.error("no_factor_data", start=str(load_start), end=args.end)
        return 3

    # Step 2: Load price matrix and compute forward returns
    prices = load_price_matrix(engine, start_date=load_start, end_date=end_date)
    if prices.empty:
        log.error("no_price_data", start=str(load_start), end=args.end)
        return 3

    forward_returns = compute_forward_returns(prices, periods=periods)

    # Step 3+4: For each period take the LAST window_days dates; compute IC
    import pandas as pd  # local import avoids top-level unused-import when pd only needed here

    all_dates: pd.DatetimeIndex = (
        factor.index.get_level_values("date").unique().sort_values()  # type: ignore[assignment]
    )
    if len(all_dates) == 0:
        log.error("no_dates_in_factor")
        return 3

    # Determine the window slice: last window_days dates available in factor
    window_dates: pd.DatetimeIndex = (
        all_dates[-window_days:] if len(all_dates) >= window_days else all_dates
    )
    window_factor = factor.loc[window_dates]

    as_of_ts = pd.Timestamp(str(window_dates[-1]))
    as_of: date = as_of_ts.date()  # type: ignore[assignment]
    window_start_str = str(pd.Timestamp(str(window_dates[0])).date())

    log.info(
        "window_selected",
        n_dates=len(window_dates),
        window_start=window_start_str,
        window_end=str(as_of),
    )

    results_by_period: dict[int, tuple[ICResult, float, float]] = {}

    for period_days in periods:
        col = f"return_{period_days}d"
        if col not in forward_returns.columns.get_level_values("period"):
            log.warning("period_missing_in_forward_returns", period=period_days)
            ic_result = ICResult(
                mean_ic=float("nan"),
                ic_std=float("nan"),
                ic_t_stat=float("nan"),
                n_observations=0,
            )
            results_by_period[period_days] = (ic_result, float("nan"), float("nan"))
            continue

        # Slice the returns for this period into a plain wide DataFrame
        returns_for_period = forward_returns[col]  # type: ignore[assignment]

        # Restrict to window dates
        returns_window = returns_for_period.loc[returns_for_period.index.intersection(window_dates)]

        ic_result = compute_ic_over_window(window_factor, returns_window)
        raw_spread = compute_quantile_spread(window_factor, returns_window)

        # Step 4: Annualize spread
        spread_ann = (
            raw_spread * (252.0 / period_days) if raw_spread == raw_spread else float("nan")
        )

        turnover = compute_turnover(window_factor)

        log.info(
            "period_ic_computed",
            period_days=period_days,
            mean_ic=ic_result.mean_ic,
            ic_t_stat=ic_result.ic_t_stat,
            spread_ann=spread_ann,
            turnover=turnover,
            n_obs=ic_result.n_observations,
        )

        results_by_period[period_days] = (ic_result, spread_ann, turnover)

        # Step 5: Persist if requested
        if args.persist:
            persist_ic_result(
                engine,
                signal_name=args.signal,
                timeframe=args.rolling_window,
                forward_period_days=period_days,
                rolling_window=args.rolling_window,
                as_of=as_of,
                result=ic_result,
                quantile_spread_ann=spread_ann,
                turnover_monthly=turnover,
            )

    if not results_by_period:
        log.error("no_results_computed")
        return 3

    # Step 6: Build and write markdown
    md = build_tearsheet_markdown(
        signal_name=args.signal,
        rolling_window=args.rolling_window,
        as_of=as_of,
        results_by_period=results_by_period,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")

    log.info("tearsheet_written", path=str(output_path), bytes=len(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
