"""The fundamental lens adapter — units, bands, and the two ways it could be silently wrong.

The scorer is India's (`atlas.lenses.compute.fundamental`, reached over the declared modulith
edge). Everything that can go wrong lives in the boundary between it and this market:

* **Units.** ``fundamentals.ratios`` returns FRACTIONS; India's ladders are written in
  PER CENT. Hand 0.20 to a rung that starts at 20 and every S&P 500 company scores at the
  bottom of every profitability, margin and growth band — a full cross-section of plausible,
  evenly distributed, uniformly wrong numbers.
* **Bands.** India's scorer reads its thresholds with ``.get(key, default)`` and ALL 37 of
  those defaults are India's own. A key missing from ``atlas_global.atlas_thresholds`` would
  score the S&P 500 on a methodology this market never approved, invisibly.

Both are asserted below on Apple's and JPMorgan's real filings
(``tests/fixtures/global/edgar/SOURCE.md``). Nothing here is constructed except the threshold
map, which is deliberately India's defaults: the point of those tests is the ARITHMETIC, and
the US bands are the FM's to lock.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from atlas.global_market.fundamentals import ratios
from atlas.global_market.fundamentals.facts import extract_rows
from atlas.global_market.scoring.stock_lenses import (
    FUNDAMENTAL_KEYS,
    PERCENT,
    score_fundamental,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "global" / "edgar"
INDIA_SCORER = REPO / "atlas" / "lenses" / "compute" / "fundamental.py"
PAYLOADS = {
    "AAPL": "companyfacts_AAPL_CIK0000320193.json",
    "JPM": "companyfacts_JPM_CIK0000019617.json",
}


@cache
def payload(symbol: str) -> dict[str, Any]:
    return json.loads((FIXTURES / PAYLOADS[symbol]).read_text())


@cache
def latest_annual(symbol: str):
    """The most recently filed annual row of a real company-facts payload."""
    annuals = [r for r in extract_rows(payload(symbol)) if r.period_class == "annual"]
    assert annuals, f"{symbol}: the fixture has no annual row"
    return max(annuals, key=lambda r: (r.filed, r.period_end))


@cache
def india_defaults() -> dict[str, Decimal]:
    """India's own literal fallbacks, read out of its source.

    Used ONLY as a stand-in band set so the arithmetic can be exercised — and, in
    :func:`test_every_band_india_falls_back_to_is_a_key_we_index`, as the proof that every one
    of them exists to fire.
    """
    found = re.findall(r'_t\(\s*th,\s*"([a-z0-9_]+)",\s*([0-9.]+)\)', INDIA_SCORER.read_text())
    return {key: Decimal(value) for key, value in found}


def bands() -> dict[str, Decimal]:
    return {key: india_defaults()[key] for key in FUNDAMENTAL_KEYS}


# ── the bands ──


def test_fundamental_keys_covers_every_threshold_india_reads() -> None:
    """The list is pinned against India's source, so a key added there cannot slip through
    unindexed and quietly fall back to an Indian number."""
    assert set(FUNDAMENTAL_KEYS) == set(india_defaults())
    assert len(FUNDAMENTAL_KEYS) == len(set(FUNDAMENTAL_KEYS)) == 37


def test_every_band_india_falls_back_to_is_a_key_we_index() -> None:
    """All 37 have a literal default in India's code. Every single one would have fired
    silently on a `.get`, which is why the adapter indexes."""
    assert all(key in india_defaults() for key in FUNDAMENTAL_KEYS)


def test_a_missing_band_raises_by_name_rather_than_scoring_on_indias() -> None:
    incomplete = {k: v for k, v in bands().items() if k != "prof_roe_ok"}
    with pytest.raises(KeyError, match="prof_roe_ok"):
        score_fundamental(
            roe=Decimal("0.35"),
            roce=None,
            operating_margin=None,
            net_margin=None,
            revenue_growth=None,
            eps_growth=None,
            debt_to_equity=None,
            current_ratio=None,
            th=incomplete,
        )


# ── the units ──


def test_a_fraction_is_not_a_percent() -> None:
    """Apple's real FY figures, scored twice: once as ``ratios`` returns them, once a hundred
    times smaller — which is what passing a fraction to a per-cent ladder amounts to.

    The second score is not an error and not zero. It is 27 out of 100 for one of the most
    profitable companies on the index, sitting in a distribution that would look entirely
    normal on a board.
    """
    row = latest_annual("AAPL")
    revenue = row.values.get("revenue")
    net_income = row.values.get("net_income")
    equity = row.values.get("equity")
    operating_income = row.values.get("operating_income")
    assert None not in (revenue, net_income, equity, operating_income)

    net = ratios.net_margin(net_income, revenue)
    op = ratios.operating_margin(operating_income, revenue)
    ret_equity = ratios.roe(net_income, equity)
    assert net is not None and op is not None and ret_equity is not None
    assert net < 1 and op < 1 and ret_equity < 10  # fractions, as ratios.py documents

    def score(scale: Decimal):
        return score_fundamental(
            roe=ret_equity * scale,
            roce=None,
            operating_margin=op * scale,
            net_margin=net * scale,
            revenue_growth=None,
            eps_growth=None,
            debt_to_equity=None,
            current_ratio=None,
            th=bands(),
        )

    as_filed = score(Decimal(1))
    as_hundredth = score(Decimal(1) / PERCENT)
    assert as_filed.value is not None and as_hundredth.value is not None
    assert as_filed.value > as_hundredth.value
    filed_prof = as_filed.subs["fund_profitability"]
    hundredth_prof = as_hundredth.subs["fund_profitability"]
    assert filed_prof is not None and hundredth_prof is not None
    assert filed_prof > hundredth_prof


def test_the_conversion_is_applied_to_rates_and_not_to_the_balance_sheet_ratios() -> None:
    """Debt/equity 0.4 is BELOW India's ``bs_de_ok`` of 0.5 and scores well; multiplied by a
    hundred it would be 40 and score at the bottom. The rates go the other way. This pins
    which side of the boundary each input is on."""
    healthy = score_fundamental(
        roe=None,
        roce=None,
        operating_margin=None,
        net_margin=None,
        revenue_growth=None,
        eps_growth=None,
        debt_to_equity=Decimal("0.4"),
        current_ratio=Decimal("1.8"),
        th=bands(),
    )
    geared = score_fundamental(
        roe=None,
        roce=None,
        operating_margin=None,
        net_margin=None,
        revenue_growth=None,
        eps_growth=None,
        debt_to_equity=Decimal("40"),
        current_ratio=Decimal("1.8"),
        th=bands(),
    )
    assert healthy.subs["fund_balance_sheet"] is not None
    assert geared.subs["fund_balance_sheet"] is not None
    assert healthy.subs["fund_balance_sheet"] > geared.subs["fund_balance_sheet"]


# ── coverage is honest, not filled in ──


def test_a_bank_gets_no_balance_sheet_sub_score_and_the_lens_renormalises() -> None:
    """JPMorgan files no ``AssetsCurrent`` and no ``LiabilitiesCurrent`` in any period, and
    ``ratios`` suppresses debt/equity for a financial company at the source. The sub-score is
    absent — not zero, which would say a bank is badly financed for being a bank."""
    row = latest_annual("JPM")
    de = ratios.debt_to_equity(
        row.values.get("debt_long"), row.values.get("equity"), is_financial=True
    )
    cr = ratios.current_ratio(
        row.values.get("assets_current"), row.values.get("liabilities_current"), is_financial=True
    )
    assert de is None and cr is None

    net = ratios.net_margin(row.values.get("net_income"), row.values.get("revenue"))
    result = score_fundamental(
        roe=ratios.roe(row.values.get("net_income"), row.values.get("equity")),
        roce=None,
        operating_margin=None,
        net_margin=net,
        revenue_growth=None,
        eps_growth=None,
        debt_to_equity=de,
        current_ratio=cr,
        th=bands(),
    )
    assert result.subs["fund_balance_sheet"] is None
    assert result.value is not None  # renormalised over the sub-scores that DID have inputs
    assert result.evidence["subs_present"] == len(
        [v for v in result.subs.values() if v is not None]
    )


def test_no_inputs_is_none_and_never_zero() -> None:
    result = score_fundamental(
        roe=None,
        roce=None,
        operating_margin=None,
        net_margin=None,
        revenue_growth=None,
        eps_growth=None,
        debt_to_equity=None,
        current_ratio=None,
        th=bands(),
    )
    assert result.value is None
    assert result.evidence["reason"] == "no sub-score had inputs"
    assert all(v is None for v in result.subs.values())


def test_the_sub_score_columns_are_the_tables() -> None:
    """A rename in ``05_scores.sql`` without one here is an ``UndefinedColumn`` on the box."""
    ddl = (REPO / "scripts" / "global_market" / "ddl" / "05_scores.sql").read_text()
    result = score_fundamental(
        roe=Decimal("0.2"),
        roce=None,
        operating_margin=None,
        net_margin=None,
        revenue_growth=None,
        eps_growth=None,
        debt_to_equity=None,
        current_ratio=None,
        th=bands(),
    )
    for column in result.subs:
        assert re.search(rf"^\s{{4}}{column}\s+numeric", ddl, re.M), column
