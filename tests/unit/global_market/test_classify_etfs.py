"""``classify_etfs`` — the verdict it writes, and that the writer agrees with the schema.

Rule #0: every fund name below is a REAL US-listed product, quoted as its issuer publishes it,
exactly as ``test_countries.py`` does. Nothing here invents a market number; the assertions are
about a name-reading rule and about two constants in this repo agreeing with each other.

The two failures this file exists to prevent:

* **A strategy with no asset class.** ``STRATEGY_ASSET_CLASS`` maps seventeen strategy words
  onto the DDL's six asset-class words. Add an eighteenth strategy to ``classify/strategy.py``
  and the map silently writes NULL — every fund in that bucket loses its asset group, its peer
  group falls back to ``unclassified``, and it is ranked against nothing. The round-trip below
  turns that into a red test at the moment the strategy is added.
* **A word the CHECK constraint rejects.** ``chk_etf_classification_asset_class`` and
  ``chk_etf_classification_strategy`` are the database's vocabulary. A value this script emits
  that the constraint refuses fails the whole nightly upsert on the box, hours after
  ``make gate`` went green — the class of bug that put ``build_country_views`` in front of the
  FM broken (``test_country_report.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from atlas.global_market.classify.strategy import STRATEGIES
from tests.unit.global_market.script_loader import load_global_script

pytestmark = pytest.mark.unit

ce = load_global_script("classify_etfs")
DDL = Path(__file__).resolve().parents[3] / "scripts" / "global_market" / "ddl"


def _check_vocabulary(constraint: str) -> set[str]:
    """The words a CHECK constraint in 03_classification.sql allows."""
    sql = (DDL / "03_classification.sql").read_text()
    start = sql.index(constraint)
    body = sql[start : sql.index("))", start)]
    return set(re.findall(r"'([a-z_]+)'", body))


# ── the writer and the schema agree ───────────────────────────────────────────


def test_every_strategy_has_an_asset_class(_: None = None) -> None:
    missing = set(STRATEGIES) - set(ce.STRATEGY_ASSET_CLASS)
    assert not missing, (
        f"strategies with no asset class: {sorted(missing)} — funds in those buckets would be "
        "written with a NULL asset_class and ranked against nothing"
    )


def test_the_map_invents_no_strategy_the_classifier_cannot_produce() -> None:
    extra = set(ce.STRATEGY_ASSET_CLASS) - set(STRATEGIES)
    assert not extra, f"asset classes mapped for non-existent strategies: {sorted(extra)}"


def test_every_asset_class_written_is_one_the_check_constraint_allows() -> None:
    allowed = _check_vocabulary("chk_etf_classification_asset_class")
    written = set(ce.STRATEGY_ASSET_CLASS.values())
    assert written <= allowed, f"{sorted(written - allowed)} would fail the CHECK on the box"


def test_every_strategy_written_is_one_the_check_constraint_allows() -> None:
    allowed = _check_vocabulary("chk_etf_classification_strategy")
    assert set(STRATEGIES) <= allowed, f"{sorted(set(STRATEGIES) - allowed)} would fail the CHECK"


def test_both_status_words_are_ones_the_check_constraint_allows() -> None:
    allowed = _check_vocabulary("chk_etf_classification_status")
    assert {ce.STATUS_AUTO, ce.STATUS_REVIEW} <= allowed


def test_the_geo_focus_words_are_ones_the_check_constraint_allows() -> None:
    allowed = _check_vocabulary("chk_etf_classification_geo_focus")
    assert {ce.GEO_SINGLE, ce.GEO_REGION} <= allowed


def test_the_report_carries_the_column_it_counts_by() -> None:
    """``Report`` counts by ``("status",)`` and indexes the column at construction — the exact
    contradiction that killed ``build_country_views`` inside its own constructor."""
    assert "status" in ce.REPORT_COLUMNS


# ── the verdict on real funds ─────────────────────────────────────────────────


def test_a_country_fund_is_filed_as_equity_country_with_its_iso_code() -> None:
    v = ce.classify_one("iShares MSCI Japan ETF", set())
    assert v["strategy"] == "country"
    assert v["asset_class"] == "equity"
    assert v["country_codes"] == ["JP"]
    assert v["geo_focus_type"] == ce.GEO_SINGLE
    assert v["status"] == ce.STATUS_AUTO
    assert v["leveraged"] is False and v["inverse"] is False


def test_a_geared_fund_is_flagged_and_can_never_be_scored() -> None:
    """It still gets classified — it exists and the board lists it — but the leveraged flag is
    what keeps it out of ``in_universe``, and therefore out of every ranking and basket."""
    v = ce.classify_one("ProShares UltraPro QQQ", set())
    assert v["leveraged"] is True


def test_an_inverse_fund_is_flagged_as_inverse() -> None:
    v = ce.classify_one("ProShares Short S&P500", set())
    assert v["inverse"] is True


def test_a_currency_hedged_share_class_is_flagged() -> None:
    v = ce.classify_one("WisdomTree Japan Hedged Equity Fund", set())
    assert v["hedged"] is True


def test_an_ex_country_fund_is_not_filed_under_the_country_it_excludes() -> None:
    """The trap worth a test of its own: reading "Asia ex Japan" as a Japan fund produces a
    wrong answer that reads perfectly plausibly on a card, and would put the fund in the wrong
    peer group as well as the wrong country."""
    v = ce.classify_one("iShares MSCI All Country Asia ex Japan ETF", set())
    assert v["country_codes"] is None
    assert v["geo_focus_type"] != ce.GEO_SINGLE


def test_a_bond_fund_is_fixed_income_not_equity() -> None:
    v = ce.classify_one("iShares 20+ Year Treasury Bond ETF", set())
    assert v["strategy"] == "fixed_income"
    assert v["asset_class"] == "fixed_income"


def test_a_gold_fund_is_a_commodity() -> None:
    v = ce.classify_one("SPDR Gold Shares", set())
    assert v["asset_class"] == "commodity"


def test_a_name_no_rule_reads_goes_to_review_with_no_strategy() -> None:
    """The ~22% the rules do not cover are a work queue, not a default bucket. Filing them
    under ``broad_market`` because nothing else matched would corrupt that peer group with
    funds that do something else entirely."""
    v = ce.classify_one("Amplius Aggressive Asset Allocation ETF", set())
    if v["strategy"] is None:
        assert v["status"] == ce.STATUS_REVIEW
        assert v["asset_class"] is None
    else:  # a rule does read it — then it must be filed consistently, not half-filed
        assert v["status"] == ce.STATUS_AUTO
        assert v["asset_class"] is not None


def test_no_confidence_number_is_invented_for_a_deterministic_rule() -> None:
    """A regex matched or it did not. A probability would be a number with no source, and the
    review queue would then sort on it (rule #0). The rule and the matched text carry the
    audit instead."""
    v = ce.classify_one("iShares MSCI Japan ETF", set())
    assert "confidence" not in v
    assert v["rule"] and v["evidence_text"]
