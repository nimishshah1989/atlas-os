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
            "in_universe": [True],
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


def test_breadth_counts_only_the_funds_the_universe_offers() -> None:
    """The two real Japan rows that made this test wrong, and then right.

    ProShares UltraShort MSCI Japan scored 7.55 on the live board of 2026-09-09 and iShares MSCI
    Japan scored 93.32. A bear fund is a bet AGAINST the market, so counting its low score as
    evidence that Japan is weak is backwards — and that is what the old denominator did, because
    it was "every fund carrying a composite" and score_etfs.py now grades everything.
    """
    group = pd.DataFrame(
        {
            "composite": [93.32, 70.54, 7.55, 47.32],
            "in_universe": [True, True, False, False],
        }
    )
    n_offered, pct = bcv.breadth(group, Decimal("60"))
    assert n_offered == 2, "the geared and below-floor funds are not in the denominator"
    assert pct == 100.0, "both funds the FM can buy clear the cut"


def test_a_fund_the_universe_offers_but_the_scorer_has_not_measured_is_not_counted() -> None:
    """Offered and unscored is a real state — a fund that cleared the floor this week and has no
    composite yet. It belongs in neither half of a percentage."""
    group = pd.DataFrame(
        {"composite": [72.0, 55.0, float("nan")], "in_universe": [True, True, True]}
    )
    n_offered, pct = bcv.breadth(group, Decimal("60"))
    assert n_offered == 2
    assert pct == 50.0


def test_a_market_with_nothing_offered_has_no_breadth_rather_than_zero() -> None:
    """Zero reads as 'measured, and every fund failed'. None is the truth: nothing to measure.

    Seven markets are in exactly this state — Belgium, Denmark, Finland, Ireland, Kuwait, Norway
    and Qatar are each covered only by funds below the FM's liquidity floor."""
    below_floor = pd.DataFrame({"composite": [63.86], "in_universe": [False]})
    assert bcv.breadth(below_floor, Decimal("60")) == (0, None)
    unmeasured = pd.DataFrame({"composite": [float("nan")], "in_universe": [True]})
    assert bcv.breadth(unmeasured, Decimal("60")) == (0, None)


def test_the_cut_is_the_seeded_threshold_not_a_literal() -> None:
    """Both funds sit either side of the value the caller passes, so moving the seeded
    ``rollup_breadth_min`` moves the answer — which is the point of it being a table row."""
    group = pd.DataFrame({"composite": [65.0, 55.0], "in_universe": [True, True]})
    assert bcv.breadth(group, Decimal("60"))[1] == 50.0
    assert bcv.breadth(group, Decimal("50"))[1] == 100.0
    assert bcv.breadth(group, Decimal("70"))[1] == 0.0
