"""Every ``atlas_global.technical_daily`` number for ONE instrument, as a pure frame.

No database, no arguments beyond the bars: :func:`metric_frame` takes an instrument's OHLCV,
SPY's close and a daily risk-free series and returns one row per session with every metric
column the DDL declares. :mod:`compute_technicals` does the I/O around it. Keeping the math
here is what makes "recompute the stored rows and diff" a real test rather than a tautology
— the test calls this function, the writer calls this function, and nothing else computes a
technical.

Reuse, not reinvention
----------------------
``scripts/foundation/technicals.py`` is market-agnostic and already the SINGLE definition of
EMA / RSI / ATR / Bollinger / 52-week position / calendar-anchored returns (all TA-Lib, per
the locked decision in docs/atlas-data-foundation.md §4). It is imported, not copied. What
is added here is what India has no column for: 24m/36m/YTD returns, relative-form RS, the
liquidity counters and the risk block.

Two deliberate departures, both visible:

* **RS is the RELATIVE form** ``(1+r_i)/(1+r_b) − 1`` (ADR-0002), computed here.
  ``technicals.compute_relative_strength`` still returns the EXCESS form ``r_i − r_b`` — the
  ADR standardised ``atlas/compute/benchmarks.py``, not this module, and changing India's
  function would silently move India's stored ``rs_*`` columns. So the four lines are
  written here instead. The two forms share a sign and are monotone in ``r_i`` within a
  date, so no ranking changes; the magnitudes do.
* **The risk block calls the library where the library has the window, and pandas where
  pandas does.** ``empyrical.roll_max_drawdown`` IS the rolling drawdown — the vectorised
  form this module used to hand-write — so it is imported. Volatility, downside risk, beta,
  Sharpe and Sortino have no ``roll_`` form that beats ``Series.rolling``: pandas runs those
  reductions in C, propagates NaN where empyrical's wrappers need ``fillna(0)``, and each is
  a one-line statement of the empyrical formula the docstring names.
  ``tests/integration/global_market/test_compute_technicals_db.py`` asserts equality against
  empyrical itself on REAL bars, so neither path can drift from the definition.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "foundation"))  # India's pure technicals

if TYPE_CHECKING:
    # Static analysis resolves the sibling tree by package path (the repo root is on
    # extraPaths); at runtime the scripts run as files, so the sys.path append above does the
    # same job. `_gdb` reaches India's `_db` exactly this way.
    from scripts.foundation import technicals as T
else:
    import technicals as T

from empyrical.stats import DAILY, annualization_factor, roll_max_drawdown


def as_series(value: object) -> pd.Series:
    """Narrow a pandas result that IS a Series but is annotated wider.

    Two of pandas' own annotations are looser than its behaviour: ``DataFrame.__getitem__``
    is Series-or-DataFrame (a list key selects columns), and the ``Rolling`` reductions are
    declared as returning an ndarray though a Series in gives a Series out. Narrowing in one
    named place keeps the module honestly typed without a cast — or a silencing comment — at
    every use, and the name says which of the two it is doing.
    """
    return cast(pd.Series, value)


def series(frame: pd.DataFrame, column: str) -> pd.Series:
    """One column of a frame, as a Series."""
    return as_series(frame[column])


def as_dates(index: pd.Index) -> np.ndarray:
    """A session index as an array of ``datetime.date`` — the whole index at once.

    ``DatetimeIndex.date`` is generated at runtime by pandas' field-accessor factory, so a
    type checker cannot see it. The numpy cast is the same whole-array conversion and IS
    visible, and doing it in one named place keeps the cast out of every call site.
    """
    return index.to_numpy().astype("datetime64[D]").astype(object)


# Trading days a year — empyrical's own constant, so the annualisation here and the
# annualisation in the cross-check can never be two different numbers.
ANNUALISATION = annualization_factor(DAILY, None)
ROOT_ANNUALISATION = float(np.sqrt(ANNUALISATION))

# Window definitions. These are the SCHEMA's own vocabulary — the column is called
# vol_63d_ann because it is 63 sessions — not tunable methodology, so they live in code
# beside the columns they fill rather than in atlas_thresholds.
SESSION_RETURNS: dict[str, int] = {"1d": 1, "1w": 5}  # a day and a week ARE sessions
CALENDAR_RETURNS: dict[str, int] = {"1m": 1, "3m": 3, "6m": 6, "12m": 12, "24m": 24, "36m": 36}
RS_WINDOWS: tuple[str, ...] = ("1w", "1m", "3m", "6m", "12m", "24m")
PEER_WINDOWS: tuple[str, ...] = RS_WINDOWS  # rs_*_peer — see metric_frame's docstring
VOL_SESSIONS: dict[str, int] = {"20d": 20, "63d": 63, "252d": 252}
ADV_MEAN_SESSIONS = 20
ADV_MEDIAN_SESSIONS = 60
DOWNSIDE_SESSIONS = 63
DRAWDOWN_SESSIONS: dict[str, int] = {"12m": 252, "36m": 756}
BETA_SESSIONS = 252
RATIO_SESSIONS = 252  # Sharpe / Sortino "12m"
CALMAR_SESSIONS = 756  # Calmar "36m"

TREND_COLUMNS = (
    [f"ema_{p}" for p in T.EMA_PERIODS]
    + [f"above_ema_{p}" for p in T.EMA_PERIODS]
    + ["rsi_2", "rsi_14", "atr_14", "atr_14_pct", "bb_width"]
    + ["vol_ratio_30d", "vol_ratio_60d", "pos_52w", "ibs"]
)
RETURN_COLUMNS = (
    [f"ret_{w}" for w in SESSION_RETURNS]
    + [f"ret_{w}" for w in CALENDAR_RETURNS]
    + ["ret_ytd"]
    + [f"rs_{w}_spy" for w in RS_WINDOWS]
    + [f"rs_{w}_peer" for w in PEER_WINDOWS]
)
RISK_COLUMNS = (
    [f"vol_{w}_ann" for w in VOL_SESSIONS]
    + ["downside_dev_63d"]
    + [f"mdd_{w}" for w in DRAWDOWN_SESSIONS]
    + ["beta_spy_252", "corr_spy_252", "sharpe_12m", "sortino_12m", "calmar_36m"]
)
METRIC_COLUMNS = TREND_COLUMNS + RETURN_COLUMNS + RISK_COLUMNS
LIQUIDITY_COLUMNS = ["adv_usd_20d_mean", "adv_usd_60d_median", "zero_volume_days_60d"]
LIQUIDITY_KEY = ("instrument_id", "date")


# ── liquidity: the ADV$ window, over the whole universe in one pass ──


def rolling_liquidity(
    bars: pd.DataFrame, window: pd.DatetimeIndex, min_observations: int
) -> pd.DataFrame:
    """The ADV$ block for a WHOLE universe at once, keyed by (instrument_id, date).

    ``bars`` is long — instrument_id, date, traded, zero_volume — and every instrument is
    REINDEXED onto ``window`` before the roll, so a name that missed a session still gets a
    window of sixty SESSIONS and not sixty of its own rows. Only the pairs that actually have
    a bar come back, which is what the aggregate this replaced grouped by.

    ``median`` is ``percentile_cont(0.5)``: both average the two middle values of an even
    window, so even the interpolation rule is the one ``build_universe_snapshot`` uses. And
    pandas' rolling reductions skip NaN while counting only real observations towards
    ``min_periods``, which is what ``avg`` / ``count`` / ``percentile_cont`` did on a partial
    window — so the NULLs land where the ``>= min_obs`` guard used to put them.
    """
    empty = pd.DataFrame(columns=pd.Index(LIQUIDITY_COLUMNS), dtype="float64")  # -> all-NULL
    if bars.empty or window.empty:
        return empty
    dated = bars.assign(date=pd.DatetimeIndex(pd.to_datetime(series(bars, "date"))))
    dated = dated.loc[dated["date"].isin(pd.Series(window))]
    if dated.empty:
        return empty
    traded = dated.pivot(index="date", columns="instrument_id", values="traded").reindex(window)
    zero = dated.pivot(index="date", columns="instrument_id", values="zero_volume")
    zero = zero.reindex(window).astype("float64")  # a gap is NaN, which rolling sum skips
    columns = {
        "adv_usd_20d_mean": traded.rolling(ADV_MEAN_SESSIONS, min_periods=1).mean(),
        "adv_usd_60d_median": traded.rolling(
            ADV_MEDIAN_SESSIONS, min_periods=min_observations
        ).median(),
        "zero_volume_days_60d": zero.rolling(ADV_MEDIAN_SESSIONS, min_periods=1).sum(),
    }
    day, instrument = np.nonzero(traded.notna().to_numpy())
    return pd.DataFrame(
        {name: rolled.to_numpy()[day, instrument] for name, rolled in columns.items()},
        index=pd.MultiIndex.from_arrays(
            # `datetime.date`, as technical_daily.date is — the frame joins onto stored rows.
            [traded.columns[instrument], as_dates(traded.index)[day]],
            names=LIQUIDITY_KEY,
        ),
    )


# ── the risk block: empyrical's formulas, on a rolling window ──


def rolling_annual_volatility(returns: pd.Series, window: int) -> pd.Series:
    """``empyrical.annual_volatility`` = ``nanstd(r, ddof=1) * sqrt(252)``, rolled."""
    return as_series(returns.rolling(window, min_periods=window).std(ddof=1)) * ROOT_ANNUALISATION


def rolling_downside_risk(excess: pd.Series, window: int) -> pd.Series:
    """``empyrical.downside_risk`` = ``sqrt(mean(min(r - mar, 0)^2)) * sqrt(252)``, rolled.

    ``excess`` is already ``r - required_return``; the mean is over the WHOLE window
    (ddof 0, upside days entering as zeros), which is what empyrical does.
    """
    squared = as_series(excess.clip(upper=0.0)) ** 2
    mean = as_series(squared.rolling(window, min_periods=window).mean())
    return as_series(mean**0.5) * ROOT_ANNUALISATION


def rolling_max_drawdown(close: pd.Series, window: int) -> pd.Series:
    """``empyrical.roll_max_drawdown`` over a trailing window of ``window`` RETURNS.

    The library owns the window: ``roll_max_drawdown`` is empyrical's own vectorised rolling
    form of ``max_drawdown``, so there is nothing here to reproduce. Two mechanical joins to
    make, and only two: it takes RETURNS (the NaN-seeded first one is dropped — empyrical
    seeds its drawdown with the value BEFORE the first return, which is exactly the window's
    own starting price), and it returns a TAIL-ALIGNED array of length ``n - window + 1``
    that is put back on the session index here.
    """
    returns = close.pct_change().iloc[1:]
    out = pd.Series(np.nan, index=close.index, dtype="float64")
    if len(returns) >= window:
        rolled = np.asarray(roll_max_drawdown(returns, window=window), dtype="float64")
        out.loc[returns.index[-len(rolled) :]] = rolled
    return out


def rolling_annual_return(close: pd.Series, window: int) -> pd.Series:
    """``empyrical.annual_return`` = ``prod(1 + r) ** (252 / n) - 1``, rolled.

    Over a window of ``close.pct_change()`` the product of ``(1 + r)`` telescopes to
    ``c_t / c_{t-window}``, which is India's :func:`technicals.trailing_return` — so the
    window return is read straight off the two closes and no product is ever formed. The
    log/exp detour this used to take was guarding against an underflow that cannot happen.
    """
    return as_series((1.0 + T.trailing_return(close, window)) ** (ANNUALISATION / window) - 1.0)


def rolling_beta(returns: pd.Series, market: pd.Series, window: int) -> pd.Series:
    """``empyrical.beta`` = ``cov(r, m) / var(m)``, rolled.

    empyrical divides two ddof-0 means; pandas' cov/var are both ddof-1. The ratio is
    identical (the same 1/(n−1) cancels), and a full window has no NaN to make them differ.
    """
    covariance = as_series(returns.rolling(window, min_periods=window).cov(market))
    variance = as_series(market.rolling(window, min_periods=window).var())
    return covariance / variance.where(variance > 0)


def rolling_sharpe(excess: pd.Series, window: int) -> pd.Series:
    """``empyrical.sharpe_ratio`` = ``mean(r - rf) / std(r - rf, ddof=1) * sqrt(252)``."""
    rolled = excess.rolling(window, min_periods=window)
    deviation = as_series(rolled.std(ddof=1))
    mean = as_series(rolled.mean())
    return mean / deviation.where(deviation > 0) * ROOT_ANNUALISATION


def rolling_sortino(excess: pd.Series, window: int) -> pd.Series:
    """``empyrical.sortino_ratio`` = ``mean(r - mar) * 252 / downside_risk(r, mar)``."""
    downside = rolling_downside_risk(excess, window)
    numerator = as_series(excess.rolling(window, min_periods=window).mean()) * ANNUALISATION
    return numerator / downside.where(downside > 0)


def risk_frame(close: pd.Series, market_close: pd.Series, risk_free: pd.Series) -> pd.DataFrame:
    """The whole risk group for one instrument.

    ``market_close`` and ``risk_free`` are already reindexed onto ``close``'s sessions.
    ``risk_free`` is a DAILY rate; where it is NaN (no macro row for the day) the Sharpe and
    Sortino windows containing that day are NaN — never zero, which would quietly claim the
    T-bill paid nothing.
    """
    returns = close.pct_change()
    market_returns = market_close.pct_change()
    excess = returns - risk_free
    out = pd.DataFrame(index=close.index)
    for name, window in VOL_SESSIONS.items():
        out[f"vol_{name}_ann"] = rolling_annual_volatility(returns, window)
    # The standalone downside deviation is the plain one (MAR = 0, empyrical's default): it
    # is a property of the price series, so it stays computable when macro_daily is empty.
    # Sortino below is the risk-free-relative one, which is why it needs the rate.
    out["downside_dev_63d"] = rolling_downside_risk(returns, DOWNSIDE_SESSIONS)
    # One pass per DISTINCT window: mdd_36m and Calmar's drawdown are both 756 sessions,
    # and computing that series twice was a third of this function's cost for one number.
    drawdowns = {
        w: rolling_max_drawdown(close, w) for w in {*DRAWDOWN_SESSIONS.values(), CALMAR_SESSIONS}
    }
    for name, window in DRAWDOWN_SESSIONS.items():
        out[f"mdd_{name}"] = drawdowns[window]
    out["beta_spy_252"] = rolling_beta(returns, market_returns, BETA_SESSIONS)
    out["corr_spy_252"] = returns.rolling(BETA_SESSIONS, min_periods=BETA_SESSIONS).corr(
        market_returns
    )
    out["sharpe_12m"] = rolling_sharpe(excess, RATIO_SESSIONS)
    out["sortino_12m"] = rolling_sortino(excess, RATIO_SESSIONS)
    # Calmar carries NO risk-free term (empyrical: annual_return / |max_drawdown|), so it
    # survives an empty macro_daily — a computable number is not withheld for a missing
    # input it never had. Undefined when the window never drew down.
    drawdown = drawdowns[CALMAR_SESSIONS]
    out["calmar_36m"] = (
        rolling_annual_return(close, CALMAR_SESSIONS) / drawdown.where(drawdown < 0).abs()
    )
    return out


# ── trend, returns and relative strength ──


def trend_frame(bars: pd.DataFrame) -> pd.DataFrame:
    """EMAs, above-flags, RSI 2 + 14, ATR, Bollinger width, volume ratios, 52w, IBS."""
    close, high, low = series(bars, "close"), series(bars, "high"), series(bars, "low")
    tech = T.compute_price_technicals(close)  # EMA x6 + RSI-14 + India's return windows
    out = pd.DataFrame(index=bars.index)
    for period in T.EMA_PERIODS:
        out[f"ema_{period}"] = tech[f"ema_{period}"]
    for period in T.EMA_PERIODS:
        out[f"above_ema_{period}"] = (close > tech[f"ema_{period}"]).where(
            tech[f"ema_{period}"].notna()
        )
    out["rsi_2"] = T.rsi(close, 2)
    out["rsi_14"] = tech[f"rsi_{T.RSI_PERIOD}"]
    volatility = T.compute_volatility_volume(high, low, close, series(bars, "volume"))
    for column in ("atr_14", "bb_width", "vol_ratio_30d", "vol_ratio_60d", "pos_52w"):
        out[column] = volatility[column]
    out["atr_14_pct"] = volatility["atr_14"] / close.where(close > 0)
    span = high - low
    out["ibs"] = ((close - low) / span).where(span > 0)  # undefined on a zero-range bar
    return out


def return_frame(close: pd.Series) -> pd.DataFrame:
    """ret_1d … ret_36m and ret_ytd. Month windows are calendar-anchored (India's rule)."""
    out = pd.DataFrame(index=close.index)
    for name, sessions in SESSION_RETURNS.items():
        out[f"ret_{name}"] = T.trailing_return(close, sessions)
    for name, months in CALENDAR_RETURNS.items():
        out[f"ret_{name}"] = T.calendar_return(close, months)
    # YTD anchors on the last close of the PREVIOUS calendar year — asof, so a year whose
    # 31 December was not a session anchors on the last session that was. pandas' Period
    # type does the year boundary: the start of each session's year, one day earlier.
    year_ends = pd.DatetimeIndex(close.index).to_period("Y").to_timestamp() - pd.Timedelta(days=1)
    base = np.asarray(close.asof(year_ends), dtype="float64")
    out["ret_ytd"] = pd.Series(close.to_numpy(dtype="float64") / base - 1.0, index=close.index)
    return out


def relative_strength(close: pd.Series, benchmark: pd.Series) -> pd.DataFrame:
    """ADR-0002 relative form: ``(1 + r_i) / (1 + r_b) − 1`` at each RS window."""
    out = pd.DataFrame(index=close.index)
    for name in RS_WINDOWS:
        months = CALENDAR_RETURNS.get(name)
        if months is None:
            mine = T.trailing_return(close, SESSION_RETURNS[name])
            theirs = T.trailing_return(benchmark, SESSION_RETURNS[name])
        else:
            mine = T.calendar_return(close, months)
            theirs = T.calendar_return(benchmark, months)
        out[f"rs_{name}_spy"] = (1.0 + mine) / (1.0 + theirs) - 1.0
    return out


def metric_frame(
    bars: pd.DataFrame, benchmark_close: pd.Series, risk_free: pd.Series
) -> pd.DataFrame:
    """Every technical_daily metric column for one instrument, indexed by session.

    ``bars`` carries open/high/low/close/volume for ONE price basis (the caller picked the
    columns from ``adjustment_source``), ascending, already restricted to SPY sessions.
    ``benchmark_close`` is SPY's close on the same basis; ``risk_free`` is the daily rate.
    Both are reindexed onto ``bars.index`` here.

    ``rs_*_peer`` is left NULL on purpose. A peer group needs the Phase 2 classification
    engine (GICS sector for stocks, taxonomy peer group for ETFs); until it exists there is
    no peer set to be relative TO, and a stand-in — "all ETFs", "the whole index" — would be
    a fabricated benchmark wearing a real column's name (rule #0).
    """
    close = series(bars, "close")
    benchmark = cast(pd.Series, benchmark_close.reindex(bars.index))
    out = pd.concat(
        [
            trend_frame(bars),
            return_frame(close),
            relative_strength(close, benchmark),
            risk_frame(close, benchmark, risk_free.reindex(bars.index)),
        ],
        axis=1,
    )
    for name in PEER_WINDOWS:
        out[f"rs_{name}_peer"] = np.nan
    return out.reindex(columns=METRIC_COLUMNS)
