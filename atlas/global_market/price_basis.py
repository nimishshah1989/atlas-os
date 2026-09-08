"""WHICH price series a US bar carries, and therefore what a technical computed on it means.

``ohlcv_daily`` has two adjusted closes: ``close_adj`` (split-only) and ``close_tr`` (splits
AND dividends). Metrics are only comparable across instruments when they were computed on
the SAME kind of series, so every ``technical_daily`` row stores the basis it used. This
module is the shared VOCABULARY for that: the two basis names, the ``adjustment_source``
labels that map onto them, and the OHLC columns each basis lives in.

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
* ``compute_technicals.py`` reads the label off the rows it is about to compute, and stamps
  it on every metric as ``technical_daily.price_basis``.

Nothing in this file needs editing when a feed's adjustment changes; the gate's verdict
changes, and the labels follow.

Why the distinction is worth this much care
-------------------------------------------
A total-return series drifts upward against a split-only one by the dividend yield,
compounded — for SPY that is on the order of 1.6 percent a year. EMA, RSI, ATR and Bollinger
conventionally run on split-only prices; run on total return they sit a little low against
the close, which reads a little bullish. Returns, relative strength and the risk block are
CORRECT on total return — that is the series they want. So the basis is not an error to be
removed, it is a fact to be carried: stamped on the row, not assumed by the reader.
"""

from __future__ import annotations

from typing import Final

# The two values technical_daily.price_basis may hold (its CHECK constraint in
# scripts/global_market/ddl/01_prices.sql lists exactly these).
TOTAL_RETURN: Final = "total_return"
SPLIT_ONLY: Final = "split_only"
PRICE_BASES: Final[tuple[str, ...]] = (TOTAL_RETURN, SPLIT_ONLY)

# ohlcv_daily.adjustment_source values, and the basis each one names. A label is minted only
# by a writer that has evidence for it: `stooq:total_return` by import_stooq.py AFTER the
# BASIS gate passes, the alpaca:* pair by ingest_prices.py from the adjustment it requested.
# `stooq:unknown` is the label for bars nothing has measured yet and maps to NO basis.
STOOQ_TOTAL_RETURN: Final = "stooq:total_return"
STOOQ_UNKNOWN: Final = "stooq:unknown"
ALPACA_SPLIT: Final = "alpaca:split"
ALPACA_ALL: Final = "alpaca:all"

BASIS_BY_ADJUSTMENT_SOURCE: Final[dict[str, str]] = {
    STOOQ_TOTAL_RETURN: TOTAL_RETURN,
    ALPACA_ALL: TOTAL_RETURN,
    ALPACA_SPLIT: SPLIT_ONLY,
}

# The OHLC columns to read for each basis. A total-return instrument's high/low are on the
# same re-based scale as its close (a back-adjusting source adjusts the whole bar), so they
# are read from the raw columns and close_tr is the labelled close. A split-only instrument
# carries the *_adj family, which is the split-consistent H/L that ATR, IBS and Bollinger
# need. Nothing reads the raw `close`: it belongs to no basis.
COLUMNS_BY_BASIS: Final[dict[str, tuple[str, str, str, str]]] = {
    TOTAL_RETURN: ("open", "high", "low", "close_tr"),
    SPLIT_ONLY: ("open_adj", "high_adj", "low_adj", "close_adj"),
}


def basis_of(adjustment_source: str | None) -> str | None:
    """The price basis an ``adjustment_source`` names, or ``None`` when it names none.

    ``None`` is the honest answer for a NULL label, for ``stooq:unknown`` (bars whose basis
    was never measured, or was measured and did not come back total-return), and for any
    label this module has not been taught. Callers must SKIP such an instrument and say so —
    never fall back to the raw close, which is neither split- nor dividend-adjusted.
    """
    if not adjustment_source:
        return None
    return BASIS_BY_ADJUSTMENT_SOURCE.get(adjustment_source)


def price_columns(basis: str) -> tuple[str, str, str, str]:
    """The ``(open, high, low, close)`` ohlcv_daily columns that carry ``basis``."""
    try:
        return COLUMNS_BY_BASIS[basis]
    except KeyError:
        raise ValueError(f"unknown price basis {basis!r}; expected one of {PRICE_BASES}") from None
