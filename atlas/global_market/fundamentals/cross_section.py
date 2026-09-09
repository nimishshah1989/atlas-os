"""The live distribution of every metric the fundamental lens bands. Pure, no I/O, no clock.

The fundamental lens has 37 threshold bands, and India's — "return on equity above 20 is
high", "revenue growth above 25 is high" — are statements about the Nifty's cross-section.
The S&P 500's is a different set of numbers, and dropping India's in would produce scores that
look authoritative and mean nothing (rule #1: a methodology number is the FM's, and it is set
from data).

So this is the table the FM sets them from: the real percentiles of the scored universe on the
day it runs, the same shape as the ADV$ percentile table that set the $1,000,000 liquidity
floor. Nothing here chooses anything.

UNITS MATCH THE LADDER THEY WILL BE READ AGAINST. The six RATES are reported as per cent,
because that is the scale India's ROE, margin and growth rungs are written on; the three
BALANCE-SHEET multiples are reported as filed, because 0.5 on the debt/equity rung means half.
It is the same split ``scoring.stock_lenses.score_fundamental`` applies at the boundary, and
if the two ever disagreed the FM would set bands on one scale and the lens would read them on
the other.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from atlas.global_market.fundamentals.metrics import Metrics

PERCENT = 100

# (metric, is_a_rate) — the nine ratios the lens reads, in the order the table prints them.
LENS_METRICS: tuple[tuple[str, bool], ...] = (
    ("roe", True),
    ("roce", True),
    ("operating_margin", True),
    ("net_margin", True),
    ("revenue_growth", True),
    ("eps_growth", True),
    ("debt_to_equity", False),
    ("current_ratio", False),
    ("interest_cover", False),
)
# Which percentiles to print is the FM's question about his own distribution, not a
# methodology number: the same seven the universe snapshot's ADV$ table reports.
PERCENTILES = (10, 25, 50, 75, 90, 95, 99)
COLUMNS: tuple[str, ...] = ("metric", "unit", "names", *(f"p{p}" for p in PERCENTILES))


def cross_section(sets: Iterable[Metrics]) -> pd.DataFrame:
    """``DataFrame[COLUMNS]`` — one row per lens input, over the names that HAVE it.

    ``names`` is that count, and it is the point: a percentile over eleven filers is not the
    index's distribution, and a metric no filer reports quarterly (interest cover, on the
    committed payloads) comes out empty rather than as a number computed from nothing.
    """
    materialised = list(sets)
    records: list[dict[str, Any]] = []
    for name, is_rate in LENS_METRICS:
        scale = PERCENT if is_rate else 1
        values = pd.Series(
            [float(v) * scale for m in materialised if (v := getattr(m, name)) is not None],
            dtype=float,
        )
        row: dict[str, Any] = {
            "metric": name,
            "unit": "percent" if is_rate else "ratio",
            "names": int(values.size),
        }
        quantiles = values.quantile([p / 100 for p in PERCENTILES]) if values.size else None
        row |= {
            f"p{p}": (None if quantiles is None else round(float(quantiles.iloc[i]), 4))
            for i, p in enumerate(PERCENTILES)
        }
        records.append(row)
    return pd.DataFrame.from_records(records, columns=list(COLUMNS))
