"""``build_country_views``'s CLI and report contract — the two defects the first run hit.

Neither is a data bug and neither needs a database, which is exactly why both survived
``make gate`` and died on the box in front of the FM:

* ``Report(path, REPORT_COLUMNS)`` counts by ``("status",)`` unless told otherwise, and the
  builder's columns had no ``status``. The constructor raised ``ValueError`` before a single
  query ran — ``tuple.index(x): x not in tuple``, which names nothing.
* ``--report`` parsed as ``str``. ``Report`` calls ``path.open(...)``, so a string would have
  failed on the NEXT line with ``AttributeError`` — and only in the branch where the FM asked
  for a CSV, which is every time anyone wants to look at the output.

Both are contradictions between two constants in this repo, so they are checkable without a
feed, a fixture or a number (rule #0): nothing here asserts on market data.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tests.unit.global_market.script_loader import load_global_script

pytestmark = pytest.mark.unit

bcv = load_global_script("build_country_views")


def test_report_columns_carry_every_column_the_report_counts_by() -> None:
    """Constructing the Report the way ``main`` does must not raise."""
    report = bcv.Report(None, bcv.REPORT_COLUMNS)
    assert report.counts == {}


def test_status_is_a_report_column() -> None:
    """The default ``count_by``; also what makes the run print its own outcome summary."""
    assert "status" in bcv.REPORT_COLUMNS


def test_report_line_width_matches_the_columns() -> None:
    """``Report.add`` is positional and raises when the row is not exactly as wide as the
    header, so a column added on one side only is a runtime error on the box.

    This calls the real ``daily_rows`` rather than asserting a count, which is what let the
    header and the emitted line drift apart the moment P2-E added three columns. Every metric
    below is NaN — a country whose funds have no data yet is a real state, and NaN is what the
    query returns for it, so nothing here is an invented market number (rule #0).
    """
    frame = pd.DataFrame(
        {
            "instrument_id": ["00000000-0000-0000-0000-000000000000"],
            "symbol": ["EWJ"],
            "name": ["iShares MSCI Japan ETF"],
            "iso2": ["JP"],
            "country_name": ["Japan"],
            "region": ["asia_pacific"],
            "eligible": [True],
            "adv_usd_60d_median": [float("nan")],
            "composite": [float("nan")],
            **{c: [float("nan")] for c in bcv.RS_COLUMNS},
        }
    )
    _rows, lines = bcv.daily_rows(frame, dt.date(2026, 9, 8), "run", Decimal("60"))
    assert len(lines) == 1
    assert len(lines[0]) == len(bcv.REPORT_COLUMNS)


def test_report_argument_parses_to_a_path() -> None:
    """A ``str`` here is an ``AttributeError`` inside ``Report``, one line further on."""
    args = bcv.parser().parse_args(["--report", "c.csv"])
    assert isinstance(args.report, Path)


def test_no_report_is_none_not_an_empty_path() -> None:
    """``Path("")`` is falsy-adjacent but truthy enough to break ``if args.report``."""
    assert bcv.parser().parse_args([]).report is None


def test_the_two_status_words_are_distinct() -> None:
    """They key the printed counter; one value for both outcomes would hide the failures."""
    assert bcv.PICKED != bcv.NO_ELIGIBLE


# ── P2-E: the country ranking ────────────────────────────────────────────────


def test_breadth_counts_only_the_funds_that_carry_a_score() -> None:
    """Geared, inverse and below-floor funds are excluded from ``in_universe`` and therefore
    have no composite. Counting them in the denominator would make a market look weak in
    proportion to how many leveraged products someone happened to launch on it."""
    group = pd.DataFrame({"composite": [72.0, 55.0, float("nan"), float("nan")]})
    n_scored, pct = bcv.breadth(group, Decimal("60"))
    assert n_scored == 2, "the two unscored funds are not in the denominator"
    assert pct == 50.0


def test_a_market_with_nothing_scored_has_no_breadth_rather_than_zero() -> None:
    """Zero reads as 'measured, and every fund failed'. None is the truth: not measured."""
    n_scored, pct = bcv.breadth(pd.DataFrame({"composite": [float("nan")]}), Decimal("60"))
    assert n_scored == 0
    assert pct is None


def test_the_cut_is_the_seeded_threshold_not_a_literal() -> None:
    """Both funds sit either side of the value the caller passes, so moving the seeded
    ``rollup_breadth_min`` moves the answer — which is the point of it being a table row."""
    group = pd.DataFrame({"composite": [65.0, 55.0]})
    assert bcv.breadth(group, Decimal("60"))[1] == 50.0
    assert bcv.breadth(group, Decimal("50"))[1] == 100.0
    assert bcv.breadth(group, Decimal("70"))[1] == 0.0
