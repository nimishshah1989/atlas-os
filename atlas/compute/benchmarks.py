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

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.compute.primitives import (
    WINDOWS,
    add_emas,
    add_max_drawdown,
    add_realized_vol,
    add_returns,
)

log = structlog.get_logger()


TIER_BENCHMARK: Mapping[str, str] = {
    "Large": "NIFTY50",
    "Mid": "MIDCAP150",
    "Small": "SMALLCAP250",
    "Micro": "MICROCAP_CUSTOM",
}
"""Methodology §6.2 tier → benchmark mapping. Codes match
``atlas_benchmark_master.benchmark_code`` populated by
``atlas.universe.benchmarks.populate_benchmark_master``.

Large-tier anchors to **Nifty 50** per the CONTEXT.md baseline lock (ADR-0001);
Nifty 100 is reserved for the Calls Performance anchor only."""


GOLD_BENCHMARK = "GOLD"
"""Numéraire for gold-denominated RS variants (methodology §7.6).
Code matches ``atlas_benchmark_master.benchmark_code = 'GOLD'`` whose
underlying source is ``de_etf_ohlcv:GOLDBEES``."""


_VALID_SCHEMAS = frozenset({"atlas", "us_atlas", "global_atlas"})


def load_benchmark_master(engine: Engine, schema: str = "atlas") -> pd.DataFrame:
    """Read active benchmarks (code + source_table + source_identifier)."""
    if schema not in _VALID_SCHEMAS:
        raise ValueError(
            f"load_benchmark_master: schema must be one of {_VALID_SCHEMAS}, got {schema!r}"
        )
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            f"SELECT benchmark_code, benchmark_type, source_table, source_identifier "  # noqa: S608 -- schema validated against _VALID_SCHEMAS whitelist above
            f"FROM {schema}.atlas_benchmark_master WHERE is_active = TRUE",
            conn,
        )


_INDIA_SOURCE_TABLES: Mapping[str, str] = {
    "de_index_prices": "index_code",
    "de_etf_ohlcv": "ticker",
    "de_global_prices": "ticker",
}


def _load_one_benchmark_prices(
    engine: Engine,
    *,
    source_table: str,
    source_identifier: str,
    start: date,
    end: date,
    schema: str = "atlas",
) -> pd.DataFrame:
    """Load price series for one benchmark from its source table.

    India path: source_table is one of de_index_prices / de_etf_ohlcv /
    de_global_prices — loaded from the ``public`` schema with the matching
    key column.

    US/Global path: source_table is ``stock_ohlcv`` — loaded from
    ``{schema}.stock_ohlcv`` using ``ticker`` as the key column.
    """
    # Strip optional schema prefix ("global_atlas.stock_ohlcv" → "stock_ohlcv")
    # so seed data and runtime dispatch stay decoupled.
    table_name = source_table.rsplit(".", 1)[-1]

    if table_name in _INDIA_SOURCE_TABLES:
        key_col = _INDIA_SOURCE_TABLES[table_name]
        sql = (
            f"SELECT date, close FROM public.{table_name} "  # noqa: S608 -- table_name validated against _INDIA_SOURCE_TABLES whitelist above
            f"WHERE {key_col} = %(code)s "
            f"AND date BETWEEN %(start)s AND %(end)s "
            f"ORDER BY date"
        )
    elif table_name == "stock_ohlcv":
        if schema not in _VALID_SCHEMAS:
            raise ValueError(
                "_load_one_benchmark_prices: schema must be one of "
                f"{_VALID_SCHEMAS}, got {schema!r}"
            )
        sql = (
            f"SELECT date, close FROM {schema}.stock_ohlcv "  # noqa: S608 -- schema validated against _VALID_SCHEMAS whitelist; table_name is literal 'stock_ohlcv'
            f"WHERE ticker = %(code)s "
            f"AND date BETWEEN %(start)s AND %(end)s "
            f"ORDER BY date"
        )
    else:
        raise ValueError(f"Unknown benchmark source_table: {source_table!r}")

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
    schema: str = "atlas",
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
    master = load_benchmark_master(engine, schema=schema)
    log.info("benchmark_master_loaded", count=len(master), schema=schema)

    pieces: list[pd.DataFrame] = []
    for _, row in master.iterrows():
        prices = _load_one_benchmark_prices(
            engine,
            source_table=str(row["source_table"]),
            source_identifier=str(row["source_identifier"]),
            start=start,
            end=end,
            schema=schema,
        )
        if prices.empty:
            log.warning(
                "benchmark_prices_empty",
                benchmark_code=row["benchmark_code"],
                source=row["source_identifier"],
            )
            continue
        prices["benchmark_code"] = row["benchmark_code"]
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
    cache = add_max_drawdown(
        cache,
        group_col="benchmark_code",
        return_col="ret_1d",
        window=252,
    )

    log.info(
        "benchmark_cache_built",
        rows=len(cache),
        benchmarks=cache["benchmark_code"].nunique(),
    )
    return cache


_BENCHMARK_CACHE_COLUMNS = (
    "benchmark_code",
    "date",
    "close",
    "ret_1d",
    "ret_1w",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "ret_12m_1m",
    "ema_10",
    "ema_20",
    "realized_vol_63",
)


def persist_benchmark_cache(engine: Engine, cache: pd.DataFrame, schema: str = "atlas") -> int:
    """Write the in-memory benchmark cache to ``{schema}.atlas_benchmark_returns_cache``.

    Called once per pipeline run after ``materialize_benchmark_cache``.
    Renames ema_10_benchmark/ema_20_benchmark to the DB column names.
    """
    if schema not in _VALID_SCHEMAS:
        raise ValueError(
            f"persist_benchmark_cache: schema must be one of {_VALID_SCHEMAS}, got {schema!r}"
        )
    df = cache.rename(columns={"ema_10_benchmark": "ema_10", "ema_20_benchmark": "ema_20"})
    df = df.reindex(columns=list(_BENCHMARK_CACHE_COLUMNS)).dropna(subset=["ret_1d"])
    if df.empty:
        return 0
    n = bulk_upsert(
        engine,
        table=f"{schema}.atlas_benchmark_returns_cache",
        columns=list(_BENCHMARK_CACHE_COLUMNS),
        rows=df_to_pg_rows(df),
        pk_columns=["benchmark_code", "date"],
    )
    log.info("benchmark_cache_persisted", rows=n, schema=schema)
    return n


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
    """``rs_<window>_tier = (1 + ret_<window>) / (1 + ret_<window>_benchmark) - 1``.

    Methodology §7.1, relative (price-ratio) form — standardized in M3
    (ADR-0002, superseding the prior excess form ``ret - bench``). Vectorized
    column arithmetic. Within a (date, tier) group the benchmark return is
    constant, so this is monotonic in the instrument return — within-tier ranks,
    states, and scoring are unchanged vs the old excess form.
    """
    out = df.copy()
    for name in windows:
        ret_col = f"ret_{name}"
        bench_col = f"ret_{name}_benchmark"
        if ret_col in out.columns and bench_col in out.columns:
            out[f"rs_{name}_tier"] = (1 + out[ret_col]) / (1 + out[bench_col]) - 1
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
    # guard: zero benchmark vol (holiday runs / early history) → NA, not inf
    out[out_col] = out[stock_vol_col] / out[bench_vol_col].replace(0, pd.NA)
    return out
