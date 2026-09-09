"""Cutting the fundamental ladder from the index's own distribution.

WHY THE LADDER IS DERIVED AT ALL. ``atlas.lenses.compute.fundamental`` grades a company by which
rung it clears: ROE at or above ``prof_roe_high`` earns eleven points. India's rungs start at ROE
20 because that is where India's index sits. Applied to the S&P 500 the failure is not a wrong
number, it is a SILENT one — a ladder whose rungs all sit below the population puts every name on
the top rung, the sub-score stops discriminating, and the board reads "these companies are all
excellent" rather than "this measure is switched off".

WHAT IS REAL HERE. The metric values are Apple's, JPMorgan's and Verizon's own filed figures,
assembled point-in-time from the three verbatim SEC company-facts payloads under
``tests/fixtures/global/edgar/`` (provenance in that directory's SOURCE.md). Three filers are NOT
the index's distribution, and the module refuses to cut a ladder from them — which is the
headline assertion below. The percentile MAPPING is what these tests pin: which rung takes which
percentile, which direction each ladder runs in, and that a rung the data cannot fill raises
instead of quietly becoming India's number.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from atlas.global_market.fundamentals import bands
from atlas.global_market.fundamentals import cross_section as xsec
from atlas.global_market.fundamentals.facts import extract_rows
from atlas.global_market.fundamentals.metrics import Metrics, metrics_as_of
from atlas.global_market.scoring.stock_lenses import (
    FUNDAMENTAL_KEYS,
    QUICK_RATIO_KEYS,
    REACHABLE_KEYS,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "edgar"
AS_OF = dt.date(2026, 9, 4)

# The floor these tests lower the module to. TWO, not three: JPMorgan is a financial, so
# ``ratios`` suppresses its ROCE, operating margin, debt/equity and current ratio at the source
# (a bank's leverage is not comparable with an industrial's), and those four metrics are
# therefore reported by two of the three filers. Prod never passes this — see the refusal test.
MIN_FOR_TESTS = 2

# CIK → whether ratios must suppress its balance-sheet inputs (a bank's debt/equity is not
# comparable with an industrial's, so `ratios` returns None for both at the source).
FILERS = (
    ("companyfacts_AAPL_CIK0000320193.json", False),
    ("companyfacts_JPM_CIK0000019617.json", True),
    ("companyfacts_VZ_CIK0000732712.json", False),
)


@cache
def filed_metrics() -> tuple[Metrics, ...]:
    out: list[Metrics] = []
    for name, is_financial in FILERS:
        payload: dict[str, Any] = json.loads((FIXTURES / name).read_text())
        found = metrics_as_of(extract_rows(payload), AS_OF, is_financial=is_financial)
        assert found is not None, f"{name}: no full TTM window at {AS_OF}"
        out.append(found)
    return tuple(out)


@cache
def three_filer_table() -> pd.DataFrame:
    return xsec.cross_section(filed_metrics())


# ── the refusal that matters most ───────────────────────────────────────────


def test_three_filers_are_not_a_distribution_and_the_ladder_refuses_to_be_cut() -> None:
    """The whole point of deriving bands is that they describe the POPULATION. A 90th percentile
    over three names is a real number about the wrong thing — and a real number about the wrong
    thing is the hardest kind of error to see later, because nothing about it looks wrong."""
    with pytest.raises(bands.UndeterminedBandError, match="name"):
        bands.bands_from_cross_section(three_filer_table())


def test_the_floor_is_a_named_argument_so_a_test_can_lower_it_and_prod_cannot() -> None:
    """Everything below cuts a ladder from these filers by lowering the floor EXPLICITLY. Prod
    never passes it, so the refusal above is what a real run gets."""
    cut = bands.bands_from_cross_section(three_filer_table(), min_names=MIN_FOR_TESTS)
    assert cut, "with the floor lowered, the three filers do produce a ladder"


# ── the mapping ─────────────────────────────────────────────────────────────


@cache
def cut() -> dict[str, Decimal]:
    return bands.bands_from_cross_section(three_filer_table(), min_names=MIN_FOR_TESTS)


def percentile(metric: str, p: int) -> Decimal:
    row = three_filer_table().loc[three_filer_table()["metric"] == metric]
    return Decimal(str(row.iloc[0][f"p{p}"]))


def test_every_rung_is_the_percentile_the_ladder_declares() -> None:
    """No rung is computed twice or shifted: each is exactly the cell of the cross-section its
    LADDERS entry names."""
    for metric, _direction, rungs in bands.LADDERS:
        for key, p in rungs:
            assert cut()[key] == percentile(metric, p), f"{key} is not {metric} P{p}"


def test_a_quality_ladder_runs_down_from_the_top_percentile() -> None:
    """ROE's best rung is the highest value, so `high` takes P90 and `low` P25 — and the four
    must descend, or the scorer's if/elif chain has rungs it can never reach."""
    ladder = [cut()[k] for k in ("prof_roe_high", "prof_roe_good", "prof_roe_ok", "prof_roe_low")]
    assert ladder == sorted(ladder, reverse=True)
    assert cut()["prof_roe_high"] == percentile("roe", 90)
    assert cut()["prof_roe_low"] == percentile("roe", 25)


def test_debt_to_equity_is_the_INVERTED_ladder_and_is_cut_the_other_way_round() -> None:
    """The trap this module exists to keep out of the scores. `bs_de_low` is the rung a company
    clears by borrowing LEAST, so it takes the 25th percentile, and `bs_de_high` the 90th. The
    names run low → high in both families while the quality they denote runs opposite; cutting
    debt/equity like ROE would grade the most-indebted companies as the safest."""
    ladder = [cut()[k] for k in ("bs_de_low", "bs_de_ok", "bs_de_med", "bs_de_high")]
    assert ladder == sorted(ladder), "debt/equity rungs must ASCEND from low to high"
    assert cut()["bs_de_low"] == percentile("debt_to_equity", 25)
    assert cut()["bs_de_high"] == percentile("debt_to_equity", 90)
    # And the quality ladder next to it runs the other way, from the same table.
    assert cut()["bs_cr_high"] == percentile("current_ratio", 90)
    assert cut()["bs_cr_ok"] == percentile("current_ratio", 50)


def test_a_rate_band_is_in_PER_CENT_because_that_is_what_the_scorer_compares() -> None:
    """``ratios`` returns fractions (ROE 0.20) and India's ladder reads per cents (20). The
    cross-section does the ×100 once; a band that skipped it would put every filer on the bottom
    rung of every rate ladder — the same unit bug that scored Apple 27 instead of 87."""
    roes = [m.roe for m in filed_metrics() if m.roe is not None]
    assert roes, "the fixtures must carry a filed ROE"
    assert max(abs(r) for r in roes) < 5, "ratios returns FRACTIONS"
    assert cut()["prof_roe_high"] > Decimal(5), "the band is a per cent, not a fraction"
    # The ratio ladders are NOT scaled: a current ratio of 1.2 is 1.2 on both sides.
    crs = [m.current_ratio for m in filed_metrics() if m.current_ratio is not None]
    if crs:
        assert min(crs) <= cut()["bs_cr_high"] <= max(crs) * 100


# ── what it will not do ─────────────────────────────────────────────────────


def test_an_empty_metric_raises_rather_than_producing_a_band() -> None:
    """A percentile of nothing is not a number. The refusal names the metric so the operator
    knows which ingest to run, instead of a threshold that looks derived and is not."""
    table = three_filer_table().copy()
    table.loc[table["metric"] == "roe", [f"p{p}" for p in xsec.PERCENTILES]] = None
    with pytest.raises(bands.UndeterminedBandError, match="roe"):
        bands.bands_from_cross_section(table, min_names=MIN_FOR_TESTS)


def test_a_metric_the_cross_section_never_carried_raises_too() -> None:
    table = three_filer_table().loc[lambda d: d["metric"] != "current_ratio"]
    with pytest.raises(bands.UndeterminedBandError, match="current_ratio"):
        bands.bands_from_cross_section(table, min_names=MIN_FOR_TESTS)


def test_the_derived_set_is_exactly_the_reachable_set() -> None:
    """Every band the scorer can read is derivable, and nothing more is derived than it reads."""
    assert bands.DERIVED_KEYS == REACHABLE_KEYS
    assert bands.undecidable(REACHABLE_KEYS) == frozenset()


def test_the_only_bands_left_out_are_the_ones_whose_INPUT_is_missing() -> None:
    """The escape hatch is pinned to its reason. ``bs_qr_*`` grade a QUICK ratio, which needs
    inventory that ``stock_financials_pit`` does not carry, so ``Metrics`` has no such field and
    India's sub-score skips the rung. The day inventory lands and ``Metrics`` grows a
    ``quick_ratio``, this test goes red and forces the three keys back into the required set at
    the same moment their input arrives."""
    assert not hasattr(Metrics, "quick_ratio"), (
        "Metrics now carries a quick ratio: add quick_ratio to cross_section.LENS_METRICS, add "
        "its ladder to bands.LADDERS, and delete stock_lenses.QUICK_RATIO_KEYS"
    )
    assert QUICK_RATIO_KEYS == frozenset(k for k in FUNDAMENTAL_KEYS if k.startswith("bs_qr_"))
    assert REACHABLE_KEYS | QUICK_RATIO_KEYS == frozenset(FUNDAMENTAL_KEYS)


def test_a_ladder_declared_in_the_wrong_order_is_caught_as_a_code_defect() -> None:
    """Percentiles are monotone by construction, so the only way the check can fail is a LADDERS
    entry written in the wrong order — which would otherwise become a silent scoring bug rather
    than an error."""
    table = three_filer_table().copy()
    # Claim debt/equity is higher-is-better while its rungs still ascend: the guard must fire.
    broken = tuple(
        (m, "higher_is_better" if m == "debt_to_equity" else d, r) for m, d, r in bands.LADDERS
    )
    original = bands.LADDERS
    try:
        bands.LADDERS = broken  # type: ignore[misc]
        with pytest.raises(bands.UndeterminedBandError, match="monotone"):
            bands.bands_from_cross_section(table, min_names=MIN_FOR_TESTS)
    finally:
        bands.LADDERS = original  # type: ignore[misc]
