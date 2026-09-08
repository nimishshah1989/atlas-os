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

from pathlib import Path

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
    """``Report.add`` is positional, so a column added without a value is a runtime error.

    ``daily_rows`` builds one list per country; every one has the same literal shape, so the
    contract is a width check against the header.
    """
    assert len(bcv.REPORT_COLUMNS) == 11


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
