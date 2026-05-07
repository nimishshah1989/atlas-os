"""Benchmark cache materialisation + tier mapping.

Per architecture §5.2: load all 9 benchmark price series once per pipeline
run, compute returns/EMAs/vol up-front, hold in memory, merge onto every stock.
This is the central trick that turns 750 individual benchmark joins into one
shared in-memory frame.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.compute.primitives import WINDOWS, add_emas, add_realized_vol, add_returns

log = structlog.get_logger()


TIER_BENCHMARK: Mapping[str, str] = {
    "Large": "NIFTY100",
    "Mid": "MIDCAP150",
    "Small": "SMALLCAP250",
    "Micro": "MICROCAP_CUSTOM",
}
"""Methodology §6.2 tier → benchmark mapping. Codes match
``atlas_benchmark_master.benchmark_code`` populated by
``atlas.universe.benchmarks.populate_benchmark_master``."""


GOLD_BENCHMARK = "GOLD"
"""Numéraire for gold-denominated RS variants (methodology §7.6).
Code matches ``atlas_benchmark_master.benchmark_code = 'GOLD'`` whose
underlying source is ``de_etf_ohlcv:GOLDBEES``."""


def load_benchmark_master(engine: Engine) -> pd.DataFrame:
    """Read active benchmarks (code + source_table + source_identifier)."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT benchmark_code, benchmark_type, source_table, source_identifier
            FROM atlas.atlas_benchmark_master
            WHERE is_active = TRUE
            """,
            conn,
        )


def _load_one_benchmark_prices(
    engine: Engine,
    *,
    source_table: str,
    source_identifier: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Load price series for one benchmark from its source table.

    Maps the three flavours of source table (``de_index_prices``,
    ``de_etf_ohlcv``, ``de_global_prices``) to a uniform ``(date, close)`` frame.
    """
    keymap = {
        "de_index_prices": "index_code",
        "de_etf_ohlcv": "ticker",
        "de_global_prices": "ticker",
    }
    if source_table not in keymap:
        raise ValueError(f"Unknown benchmark source_table: {source_table}")

    sql = (
        f"SELECT date, close FROM public.{source_table} "
        f"WHERE {keymap[source_table]} = %(code)s "
        f"AND date BETWEEN %(start)s AND %(end)s "
        f"ORDER BY date"
    )
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            sql,
            conn,
            params={"code": source_identifier, "start": start, "end": end},
        )


def materialize_benchmark_cache(
    engine: Engine,
    *,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Build the per-run benchmark cache.

    Returns a long-format DataFrame:

        benchmark_code, date, close,
        ret_1d, ret_1w, ..., ret_12m_1m,
        ema_10_benchmark, ema_20_benchmark, ema_50_benchmark, ema_200_benchmark,
        realized_vol_63

    All windows / EMAs are computed before merging onto stocks. The frame is
    long-format because pandas merges on ``(date, benchmark_code)`` are clean;
    we pivot wide only when absolutely needed (e.g., RS-vs-multiple-benchmarks).
    """
    master = load_benchmark_master(engine)
    log.info("benchmark_master_loaded", count=len(master))

    pieces: list[pd.DataFrame] = []
    for row in master.itertuples(index=False):
        prices = _load_one_benchmark_prices(
            engine,
            source_table=row.source_table,
            source_identifier=row.source_identifier,
            start=start,
            end=end,
        )
        if prices.empty:
            log.warning(
                "benchmark_prices_empty",
                benchmark_code=row.benchmark_code,
                source=row.source_identifier,
            )
            continue
        prices["benchmark_code"] = row.benchmark_code
        pieces.append(prices)

    cache = pd.concat(pieces, ignore_index=True)
    cache["date"] = pd.to_datetime(cache["date"]).dt.date

    cache = add_returns(
        cache,
        group_col="benchmark_code",
        price_col="close",
        windows=WINDOWS,
    )
    cache = add_emas(
        cache,
        group_col="benchmark_code",
        price_col="close",
        lengths=(10, 20, 50, 200),
        suffix="benchmark",
    )
    cache = add_realized_vol(
        cache,
        group_col="benchmark_code",
        return_col="ret_1d",
        window=63,
    )

    log.info(
        "benchmark_cache_built",
        rows=len(cache),
        benchmarks=cache["benchmark_code"].nunique(),
    )
    return cache


def merge_tier_benchmark(
    stocks: pd.DataFrame,
    benchmark_cache: pd.DataFrame,
    *,
    tier_col: str = "tier",
) -> pd.DataFrame:
    """Attach each stock's tier benchmark return/EMA columns by date.

    Each stock has a single tier-benchmark (Large→NIFTY100, etc.). Merge is
    on ``(date, benchmark_code)`` after mapping the tier.
    """
    out = stocks.copy()
    out["benchmark_code"] = out[tier_col].map(TIER_BENCHMARK)

    bench_cols = ["benchmark_code", "date"] + [
        c for c in benchmark_cache.columns if c.startswith(("ret_", "ema_", "realized_vol_"))
    ]
    bench_subset = benchmark_cache[bench_cols].copy()

    rename = {c: c.replace("_benchmark", "") for c in bench_subset.columns if c.startswith("ema_")}
    bench_subset = bench_subset.rename(columns=rename)
    bench_subset = bench_subset.rename(
        columns={
            **{f"ret_{n}": f"ret_{n}_benchmark" for n in WINDOWS},
            "ret_1d": "ret_1d_benchmark",
            "realized_vol_63": "realized_vol_63_benchmark",
            **{f"ema_{n}": f"ema_{n}_benchmark" for n in (10, 20, 50, 200)},
        }
    )

    out = out.merge(bench_subset, on=["benchmark_code", "date"], how="left")
    return out


def add_relative_strength(
    df: pd.DataFrame,
    *,
    windows: Mapping[str, int] = WINDOWS,
) -> pd.DataFrame:
    """``rs_<window>_tier = ret_<window> - ret_<window>_benchmark`` for each window.

    Methodology §7.1. Decimal arithmetic; ratio variant lives in M3 if needed.
    """
    out = df.copy()
    for name in windows:
        ret_col = f"ret_{name}"
        bench_col = f"ret_{name}_benchmark"
        if ret_col in out.columns and bench_col in out.columns:
            out[f"rs_{name}_tier"] = out[ret_col] - out[bench_col]
    return out


def add_vol_ratio(
    df: pd.DataFrame,
    *,
    stock_vol_col: str = "realized_vol_63",
    bench_vol_col: str = "realized_vol_63_benchmark",
    out_col: str = "vol_ratio_63",
) -> pd.DataFrame:
    """``vol_ratio_63 = stock_vol_63 / benchmark_vol_63`` per methodology §7.3."""
    out = df.copy()
    out[out_col] = out[stock_vol_col] / out[bench_vol_col]
    return out
