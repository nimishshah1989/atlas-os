"""WHICH price series a US bar carries, and therefore what a technical computed on it means.

``ohlcv_daily`` has two adjusted closes: ``close_adj`` (split-only) and ``close_tr`` (splits
AND dividends). Metrics are only comparable across instruments when they were computed on
the SAME kind of series, so every ``technical_daily`` row stores the basis it used. This
module is the shared VOCABULARY for that: the two series names, the ``adjustment_source``
labels that say WHICH SERIES a feed's rows carry, the OHLC columns each series lives in, and
the plan that follows — which series each metric family reads, and the stamp that records it.

A row can carry both. The vendor is pulled on three adjustments per window, so one Alpaca
row holds the split-only family in ``*_adj`` AND the total-return close in ``close_tr``. The
basis is therefore a property of the METRIC, not of the instrument: the trend block takes
split-only, returns / RS / risk take total return, and :class:`BasisPlan` is that pairing.
The Stooq archive carries only ``close_tr``, so there both families read it and the stamp
says ``total_return`` — a compromise declared on the row rather than hidden inside it.

What this module is NOT
-----------------------
It does not decide, record or restate what any real feed carries. That is a measurement, and
it has one owner: ``scripts/global_market/validate_global.py --check BASIS``, which reads the
actual bars, compares them against FRED's SP500 price index and prints a verdict. A constant
here saying "Stooq is total return" would be a second, unmeasured copy of that answer — and
the day a feed changes, or a split-only source is added, the constant would still say
total_return while the gate said otherwise, and every EMA on the board would be computed on a
basis nothing had checked. So:

* the GATE measures, per run, from real rows;
* ``import_stooq.py`` asks the gate before it mints a label, and mints none when the gate
  does not pass (:func:`basis_of` then refuses those rows);
* ``compute_technicals.py`` reads the label off the rows it is about to compute, resolves
  it to a :class:`BasisPlan`, and stamps ``plan.stamp`` on every row as
  ``technical_daily.price_basis``.

Nothing in this file needs editing when a feed's adjustment changes; the gate's verdict
changes, and the labels follow.

Why the distinction is worth this much care
-------------------------------------------
A total-return series drifts upward against a split-only one by the dividend yield,
compounded — for SPY that is on the order of 1.6 percent a year. EMA, RSI, ATR and Bollinger
conventionally run on split-only prices; run on total return they sit a little low against
the close, which reads a little bullish. Returns, relative strength and the risk block are
CORRECT on total return — that is the series they want. Where both series exist each family
gets its own, and where only one does the basis is not an error to be removed but a fact to
be carried: stamped on the row, not assumed by the reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# The two SERIES ohlcv_daily carries, and the values technical_daily.price_basis may hold
# (its CHECK constraint in scripts/global_market/ddl/01_prices.sql lists exactly these three).
TOTAL_RETURN: Final = "total_return"
SPLIT_ONLY: Final = "split_only"
PRICE_SERIES: Final[tuple[str, ...]] = (TOTAL_RETURN, SPLIT_ONLY)

# The stamp for a row whose trend block ran on split-only and whose return / RS / risk block
# ran on total return — each family on the series it wants. It is not a third series; it is
# the honest name for "both, correctly".
SPLIT_AND_TOTAL_RETURN: Final = "split_only+total_return"
PRICE_BASES: Final[tuple[str, ...]] = (TOTAL_RETURN, SPLIT_ONLY, SPLIT_AND_TOTAL_RETURN)

# ohlcv_daily.adjustment_source values, and the SERIES each one's rows carry. A label is
# minted only by a writer that has evidence for it: `stooq:total_return` by import_stooq.py
# AFTER the BASIS gate passes, the alpaca:* labels by ingest_prices.py from the adjustments it
# requested. `stooq:unknown` is the label for bars nothing has measured yet and carries none.
STOOQ_TOTAL_RETURN: Final = "stooq:total_return"
STOOQ_UNKNOWN: Final = "stooq:unknown"
ALPACA_SPLIT: Final = "alpaca:split"
ALPACA_ALL: Final = "alpaca:all"
ALPACA_SPLIT_AND_ALL: Final = "alpaca:split+all"

SERIES_BY_ADJUSTMENT_SOURCE: Final[dict[str, frozenset[str]]] = {
    STOOQ_TOTAL_RETURN: frozenset({TOTAL_RETURN}),
    ALPACA_ALL: frozenset({TOTAL_RETURN}),
    ALPACA_SPLIT: frozenset({SPLIT_ONLY}),
    ALPACA_SPLIT_AND_ALL: frozenset({SPLIT_ONLY, TOTAL_RETURN}),
}

# The OHLC columns to read for each series. A total-return instrument's high/low are on the
# same re-based scale as its close (a back-adjusting source adjusts the whole bar), so they
# are read from the raw columns and close_tr is the labelled close. A split-only instrument
# carries the *_adj family, which is the split-consistent H/L that ATR, IBS and Bollinger
# need. Nothing reads the raw `close`: it belongs to no basis.
COLUMNS_BY_SERIES: Final[dict[str, tuple[str, str, str, str]]] = {
    TOTAL_RETURN: ("open", "high", "low", "close_tr"),
    SPLIT_ONLY: ("open_adj", "high_adj", "low_adj", "close_adj"),
}


@dataclass(frozen=True)
class BasisPlan:
    """Which series each metric family runs on, and the stamp that records it.

    ``trend`` feeds EMA / RSI / ATR / Bollinger / IBS — conventionally split-only prices.
    ``returns`` feeds every return, relative-strength and risk metric — correctly total
    return. ``stamp`` is what lands in ``technical_daily.price_basis``, and it names the pair,
    never a preference: a row stamped ``split_only`` says its returns are PRICE returns
    because no total-return series existed for that instrument, not that we chose one.
    """

    trend: str
    returns: str
    stamp: str

    @property
    def one_series(self) -> bool:
        """Do both families read the same column family (so one bar frame serves both)?"""
        return self.trend == self.returns


def plan_for(adjustment_source: str | None) -> BasisPlan | None:
    """The basis plan an ``adjustment_source`` names, or ``None`` when it names none.

    ``None`` is the honest answer for a NULL label, for ``stooq:unknown`` (bars whose basis
    was never measured, or was measured and did not come back total-return), and for any
    label this module has not been taught. Callers must SKIP such an instrument and say so —
    never fall back to the raw close, which is neither split- nor dividend-adjusted.

    Where a source carries only one series, BOTH families read it and the stamp is that
    series' own name: a Stooq row's EMAs run on total return (they sit a little low against
    the close, which reads a little bullish), and the stamp is what declares it rather than
    hiding it. Where a source carries both — the vendor's three-pull rows — each family gets
    the series it wants and the stamp says so.
    """
    if not adjustment_source:
        return None
    series = SERIES_BY_ADJUSTMENT_SOURCE.get(adjustment_source)
    if not series:
        return None
    trend = SPLIT_ONLY if SPLIT_ONLY in series else TOTAL_RETURN
    returns = TOTAL_RETURN if TOTAL_RETURN in series else SPLIT_ONLY
    stamp = SPLIT_AND_TOTAL_RETURN if trend != returns else trend
    return BasisPlan(trend=trend, returns=returns, stamp=stamp)


def price_columns(series: str) -> tuple[str, str, str, str]:
    """The ``(open, high, low, close)`` ohlcv_daily columns that carry ``series``."""
    try:
        return COLUMNS_BY_SERIES[series]
    except KeyError:
        raise ValueError(
            f"unknown price series {series!r}; expected one of {PRICE_SERIES}"
        ) from None
