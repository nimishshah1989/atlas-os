"""The S&P 500 fundamental cross-section, and how a run prints it.

Split out of ``score_stocks`` for two reasons. It is over the 600-line tier without this,
and — the better reason — this table's job is to inform ``seed_thresholds.py
--fundamental-bands``, which cuts the lens's ladder from exactly these percentiles. It is
the band-setter's report that the scorer happens to print, not the other way round.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import _gdb
import pandas as pd
from _report import Report

from atlas.global_market.fundamentals import cross_section as xsec
from atlas.global_market.fundamentals.metrics import Metrics
from atlas.global_market.scoring.stock_lenses import REACHABLE_KEYS

M = _gdb.M

METRIC_REPORT_COLUMNS = xsec.COLUMNS


def cross_section(by_id: Mapping[str, Metrics], report: Report | None) -> pd.DataFrame:
    """The pure table, with each row also written to the FM's CSV."""
    table = xsec.cross_section(by_id.values())
    if report is not None:
        for row in table.to_dict("records"):
            report.add(*(row[c] for c in METRIC_REPORT_COLUMNS))
    return table


def print_cross_section(table: pd.DataFrame, missing: Sequence[str]) -> None:
    """The same table on the console, and — when the bands are not all there — why the lens
    did not score."""
    header = f"{'metric':<20}{'unit':<9}{'names':>6}" + "".join(
        f"{'P' + str(p):>10}" for p in xsec.PERCENTILES
    )
    print("\n[score_stocks] S&P 500 fundamental cross-section — the FM sets the bands from this")
    print("  " + header)
    for r in table.to_dict("records"):
        # pd.isna, not `is None`: DataFrame.from_records turns a None into NaN in a float
        # column, and NaN formats as "nan" through the same "{:>10.2f}" that would show a
        # number. The CSV is written from the dicts and keeps the empty cell either way.
        cells = "".join(
            f"{'—':>10}" if pd.isna(r[f"p{p}"]) else f"{r[f'p{p}']:>10.2f}"
            for p in xsec.PERCENTILES
        )
        print(f"  {r['metric']:<20}{r['unit']:<9}{r['names']:>6}{cells}")
    if missing:
        print(
            f"  the fundamental lens is NOT scored: {len(missing)} of {len(REACHABLE_KEYS)} "
            f"band(s) are missing from {M}.atlas_thresholds, first {missing[0]!r}. Set them "
            "from the table above (seed_thresholds.py, FM approval first) — a partial set "
            "would score this market on India's numbers."
        )
