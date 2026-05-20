"""SDE Phase 0 factor catalog and generation.

Each catalog entry maps a single instrument's OHLCV frame (date-indexed,
columns open/high/low/close/volume) to a Series of factor values.
generate_factors runs the whole catalog across an OHLCV panel and returns,
per factor, a (date, instrument_id) MultiIndex frame with one 'factor'
column — the shape ic_engine.compute_ic_over_window expects.

The catalog is a curated, countable seed library across the standard
families: momentum, mean-reversion, volatility, volume, range, and
return-distribution. ~20 factors keeps the search space small enough to
honestly account for in the IC interpretation.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pandas_ta as ta  # type: ignore[import-untyped]
import structlog

log = structlog.get_logger()


def _ret(df: pd.DataFrame) -> pd.Series:  # type: ignore[type-arg]
    s: pd.Series = df["close"]  # type: ignore[assignment]
    return s.pct_change()


def _s(df: pd.DataFrame, col: str) -> pd.Series:  # type: ignore[type-arg]
    """Extract a column as pd.Series (narrows DataFrame | Series | Unknown)."""
    result: pd.Series = df[col]  # type: ignore[assignment]
    return result


# name -> function(single-instrument OHLCV frame) -> Series
FACTOR_CATALOG: dict[str, Callable[[pd.DataFrame], pd.Series]] = {  # type: ignore[type-arg]
    # momentum
    "roc_63": lambda df: ta.roc(_s(df, "close"), length=63),  # type: ignore[attr-defined]
    "roc_126": lambda df: ta.roc(_s(df, "close"), length=126),  # type: ignore[attr-defined]
    "roc_252": lambda df: ta.roc(_s(df, "close"), length=252),  # type: ignore[attr-defined]
    "rsi_14": lambda df: ta.rsi(_s(df, "close"), length=14),  # type: ignore[attr-defined]
    "ema_ratio_50": lambda df: _s(df, "close") / ta.ema(_s(df, "close"), length=50) - 1.0,  # type: ignore[attr-defined]
    # mean-reversion
    "rsi_3": lambda df: ta.rsi(_s(df, "close"), length=3),  # type: ignore[attr-defined]
    "dist_sma_20": lambda df: _s(df, "close") / ta.sma(_s(df, "close"), length=20) - 1.0,  # type: ignore[attr-defined]
    "dist_sma_200": lambda df: _s(df, "close") / ta.sma(_s(df, "close"), length=200) - 1.0,  # type: ignore[attr-defined]
    # volatility
    "atr_pct_14": lambda df: ta.atr(_s(df, "high"), _s(df, "low"), _s(df, "close"), length=14)  # type: ignore[attr-defined]
    / _s(df, "close"),
    "natr_14": lambda df: ta.natr(_s(df, "high"), _s(df, "low"), _s(df, "close"), length=14),  # type: ignore[attr-defined]
    "vol_21": lambda df: _ret(df).rolling(21).std(),
    "vol_63": lambda df: _ret(df).rolling(63).std(),
    # volume
    "vol_ratio_20": lambda df: _s(df, "volume") / _s(df, "volume").rolling(20).mean(),
    "obv_chg_21": lambda df: ta.obv(_s(df, "close"), _s(df, "volume")).pct_change(21),  # type: ignore[attr-defined]
    "mfi_14": lambda df: ta.mfi(  # type: ignore[attr-defined]
        _s(df, "high"), _s(df, "low"), _s(df, "close"), _s(df, "volume"), length=14
    ),
    "cmf_20": lambda df: ta.cmf(  # type: ignore[attr-defined]
        _s(df, "high"), _s(df, "low"), _s(df, "close"), _s(df, "volume"), length=20
    ),
    # range / price location
    "prox_52w_high": lambda df: _s(df, "close") / _s(df, "close").rolling(252).max(),
    "prox_52w_low": lambda df: _s(df, "close") / _s(df, "close").rolling(252).min(),
    # return distribution
    "skew_63": lambda df: _ret(df).rolling(63).skew(),
    "kurt_63": lambda df: _ret(df).rolling(63).kurt(),
}


def generate_factors(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Run the factor catalog across an OHLCV panel.

    panel: long DataFrame with date, instrument_id, open/high/low/close/volume.
    Returns dict[factor_name -> DataFrame], each indexed by a
    (date, instrument_id) MultiIndex with a single 'factor' column.
    """
    collected: dict[str, list[pd.DataFrame]] = {name: [] for name in FACTOR_CATALOG}
    for iid, group in panel.groupby("instrument_id", sort=False):
        idf = group.sort_values("date").set_index("date")
        for name, fn in FACTOR_CATALOG.items():
            series = fn(idf)
            if series is None:
                continue
            frame = pd.DataFrame({"factor": pd.Series(series.to_numpy(), index=idf.index)})
            frame["instrument_id"] = iid
            collected[name].append(frame)

    result: dict[str, pd.DataFrame] = {}
    for name, frames in collected.items():
        if not frames:
            result[name] = pd.DataFrame(
                {"factor": pd.Series(dtype="float64")},
                index=pd.MultiIndex.from_arrays([[], []], names=["date", "instrument_id"]),
            )
            continue
        df = pd.concat(frames)
        df = df.set_index("instrument_id", append=True)
        df.index = df.index.set_names(["date", "instrument_id"])
        result[name] = df[["factor"]].dropna()  # type: ignore[assignment]

    log.info("sde_factors_generated", n_factors=len(result))
    return result


def liquidity_mask(panel: pd.DataFrame, *, floor_inr: float = 5e7, window: int = 60) -> pd.Series:  # type: ignore[type-arg]
    """Per-(date, instrument) boolean: trailing `window`-day median traded
    value (close * volume) is at or above the floor.

    Uses rolling median as the robust liquidity measure — one high-volume day
    should not qualify an otherwise illiquid instrument.
    Returned as a boolean Series on a (date, instrument_id) MultiIndex.
    This is the point-in-time liquidity gate — it drops days where a kept
    instrument was temporarily illiquid (e.g. early in its listed history).
    """
    df = panel.sort_values(["instrument_id", "date"]).copy()
    df["traded_value"] = df["close"] * df["volume"]
    df["median_tv"] = df.groupby("instrument_id")["traded_value"].transform(
        lambda s: s.rolling(window, min_periods=window // 2).median()
    )
    indexed = df.set_index(["date", "instrument_id"])
    return (indexed["median_tv"] >= floor_inr).fillna(False)
