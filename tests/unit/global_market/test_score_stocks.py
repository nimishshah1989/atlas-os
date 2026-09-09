"""``score_stocks``: the cohort rule, the report contract, and the row it writes.

No DB, no network — everything here is a contract between two constants in this repo, or a
property of a pure function, which is the only kind of thing that can be checked without a
feed (rule #0). Three failure classes, all of which have already cost this project a run:

* **A report whose ``count_by`` column is not among its columns.** ``Report(path, COLUMNS)``
  counts by ``("status",)`` unless told otherwise, and ``build_country_views`` shipped without
  one: the constructor raised ``ValueError`` before a single query ran, on the box, in front of
  the FM (``test_country_report.py``).
* **A column the table does not have.** The row this script writes must be spelled the way
  ``ddl/05_scores.sql`` spells it, or the whole nightly upsert fails hours after ``make gate``
  went green — the class ``test_classify_etfs.py`` guards for the classification writer.
* **A cohort that is not monotone in weight.** Deciles are cut within cohort, so a cohort that
  can put a heavier name below a lighter one corrupts every ranking read off it.

**ON THE WEIGHTS BELOW.** The committed S&P 500 fixture
(``tests/fixtures/global/index/sp500_ticker_start_end.csv``, MIT, fja05680 — see its
``SOURCE.md``) carries membership spells and NO weights: the real SPY weights live in SSGA's
holdings workbook, which that same SOURCE.md records as un-redistributable and therefore never
committed. So the tickers here are REAL current members read out of that fixture, and the
weights are the ORDERING ``1, 2, 3 …`` — deliberately whole numbers rather than fractions, so
that nothing on this page can be read as a claim about what any of these companies weighs in
the index. What is under test is the tercile rule's PROPERTIES over an ordering (monotone,
three near-equal parts, a missing weight lands lowest), and those hold whatever the real
weights turn out to be.
"""

from __future__ import annotations

import ast
import csv
import datetime as dt
import inspect
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from atlas.global_market.fundamentals import cross_section as xsec
from atlas.global_market.scoring.stock_lenses import (
    FUNDAMENTAL_KEYS,
    QUICK_RATIO_KEYS,
    REACHABLE_KEYS,
)
from tests.unit.global_market.scaffold_identity import scaffold_rows
from tests.unit.global_market.script_loader import load_global_script

pytestmark = pytest.mark.unit

ss = load_global_script("score_stocks")
seed_thresholds = load_global_script("seed_thresholds")

_REPO = Path(__file__).resolve().parents[3]
_DDL = _REPO / "scripts" / "global_market" / "ddl" / "05_scores.sql"
_SP500_FIXTURE = _REPO / "tests" / "fixtures" / "global" / "index" / "sp500_ticker_start_end.csv"

# The cohort's rank, lightest first — the order the labels must come out in.
_COHORT_RANK = {name: i for i, name in enumerate(ss.COHORTS_LIGHTEST_FIRST)}

# Every technical_daily / ohlcv_daily column score_rows reads off a target row.
_METRIC_COLUMNS = (
    "ema_21",
    "ema_50",
    "ema_200",
    "rsi_14",
    "ret_1w",
    "price",
    "rs_1m_spy",
    "rs_3m_spy",
    "rs_6m_spy",
    "rs_12m_spy",
    "rs_1m_peer",
    "rs_3m_peer",
    "rs_6m_peer",
    "rs_12m_peer",
    "atr_14",
    "bb_width",
    "vol_ratio_30d",
    "vol_ratio_60d",
    "pos_52w",
)


def current_members(limit: int) -> list[str]:
    """The first ``limit`` CURRENT S&P 500 tickers in the committed fixture (empty end_date).

    Real names from a real committed source; the fixture's own ``SOURCE.md`` records its
    provenance, licence and sha256, and says to refresh it by re-fetching, never by editing.
    """
    with _SP500_FIXTURE.open(newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if not (r["end_date"] or "").strip()]
    assert len(rows) > limit, f"{_SP500_FIXTURE.name} holds only {len(rows)} current members"
    return [r["ticker"] for r in rows[:limit]]


def ordering(tickers: list[str]) -> pd.Series:
    """An ORDERING of index weights over real tickers — 1 is the lightest. Not observations."""
    return pd.Series([Decimal(i) for i in range(1, len(tickers) + 1)], index=tickers, dtype=object)


def ddl_block(table: str) -> str:
    sql = _DDL.read_text()
    start = sql.index(f"CREATE TABLE IF NOT EXISTS atlas_global.{table} (")
    return sql[start : sql.index(f"CONSTRAINT {table}_pkey", start)]


def ddl_columns(table: str) -> set[str]:
    """The column names of a CREATE TABLE block — the first word of each declaration line."""
    body = ddl_block(table).split("(", 1)[1]
    return {
        m.group(1) for line in body.splitlines() if (m := re.match(r"\s{4}([a-z_]+)\s+[a-z]", line))
    }


def ddl_check_vocabulary(constraint: str) -> set[str]:
    """The words a CHECK constraint allows (the technique ``test_classify_etfs.py`` uses)."""
    sql = _DDL.read_text()
    start = sql.index(constraint)
    return set(re.findall(r"'([a-z_]+)'", sql[start : sql.index("))", start)]))


def written_columns() -> set[str]:
    """Every key of the row dict ``score_rows`` appends, read out of its own source.

    Static, because building the frame would need an instrument identity and a session's
    metrics — data this test has no honest source for. The keys are what the INSERT names.
    """
    tree = ast.parse(inspect.getsource(ss.score_rows))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "rows"
            and node.args
            and isinstance(node.args[0], ast.Dict)
        ):
            keys |= {str(k.value) for k in node.args[0].keys if isinstance(k, ast.Constant)}
            # `**dict(technical.subs)` splats the lens's sub-score columns in.
            if any(k is None for k in node.args[0].keys):
                keys |= {column for column, _attribute in _technical_subs()}
    assert keys, "found no row dict in score_rows — the parse, not the code, broke"
    return keys


def _technical_subs() -> tuple[tuple[str, str], ...]:
    from atlas.global_market.scoring.stock_lenses import TECHNICAL_SUBS

    return TECHNICAL_SUBS


# ── the cohort rule (SPY-weight terciles) ─────────────────────────────────────


def test_a_heavier_member_is_never_in_a_lighter_cohort() -> None:
    """The property deciles-within-cohort depend on. Asserted over an ORDERING of weights."""
    weights = ordering(current_members(300))
    ranks = ss.cap_cohorts(weights).map(_COHORT_RANK)
    assert ranks.is_monotonic_increasing, "cohorts are not monotone in weight"


def test_the_three_cohorts_are_terciles_of_the_weighted_members() -> None:
    weights = ordering(current_members(300))
    sizes = ss.cap_cohorts(weights).value_counts().to_dict()
    assert set(sizes) == set(ss.COHORTS_LIGHTEST_FIRST)
    assert max(sizes.values()) - min(sizes.values()) <= 1, sizes


def test_the_heaviest_third_is_mega_and_the_lightest_is_mid() -> None:
    """The names are the DDL's, and the direction is the one a reader assumes: mega = biggest."""
    weights = ordering(current_members(300))
    cohorts = ss.cap_cohorts(weights)
    assert cohorts.iloc[-1] == "mega"
    assert cohorts.iloc[0] == "mid"


def test_every_cohort_word_is_one_the_check_constraint_allows() -> None:
    """A word the CHECK refuses fails the nightly upsert on the box, not here."""
    allowed = ddl_check_vocabulary("chk_lens_scores_daily_cap_cohort")
    assert set(ss.COHORTS_LIGHTEST_FIRST) == allowed


@pytest.mark.parametrize("absent", [None, float("nan")])
def test_a_member_with_no_weight_lands_in_the_lowest_cohort_and_is_reported(
    absent: object,
) -> None:
    """``weight_frac`` is nullable: an addition between the issuer's weekly files can have a
    membership interval and no weight yet. Dropping it would silently shrink the S&P 500."""
    tickers = current_members(30)
    weights = ordering(tickers)
    weights.iloc[-1] = absent  # the row that would otherwise be the heaviest
    cohorts, sources = ss.cap_cohorts(weights), ss.cohort_sources(weights)
    assert cohorts.iloc[-1] == ss.LIGHTEST_COHORT
    assert sources.iloc[-1] == ss.COHORT_NO_WEIGHT
    assert list(sources[:-1]) == [ss.COHORT_FROM_WEIGHT] * (len(tickers) - 1)
    assert cohorts.iloc[0] == ss.LIGHTEST_COHORT, "the weighted members are still cut in three"
    assert set(cohorts) == set(ss.COHORTS_LIGHTEST_FIRST)


def test_too_few_weighted_members_to_cut_falls_to_the_lightest_cohort() -> None:
    """A database mid-backfill, never a real S&P 500. Everything lands lowest rather than the
    run inventing a cut; the printed cohort sizes make that state visible."""
    weights = pd.Series([Decimal(1), None], index=current_members(2), dtype=object)
    assert list(ss.cap_cohorts(weights)) == [ss.LIGHTEST_COHORT] * 2


# ── the report contract ───────────────────────────────────────────────────────


def test_report_columns_carry_every_column_the_report_counts_by() -> None:
    """Constructing the Report the way ``main`` does must not raise."""
    assert ss.Report(None, ss.REPORT_COLUMNS).counts == {}


def test_status_is_a_report_column() -> None:
    """The default ``count_by``; also what makes the run print its own outcome summary."""
    assert "status" in ss.REPORT_COLUMNS


def test_report_line_width_matches_the_columns() -> None:
    """``Report.add`` is positional, so a column added without a value is a runtime error."""
    assert len(ss.REPORT_COLUMNS) == 12


def test_report_argument_parses_to_a_path() -> None:
    """A ``str`` here is an ``AttributeError`` inside ``Report``, one line further on."""
    assert isinstance(ss.parser().parse_args(["--report", "s.csv"]).report, Path)


def test_no_report_is_none_not_an_empty_path() -> None:
    assert ss.parser().parse_args([]).report is None


def test_the_two_status_words_are_distinct() -> None:
    """They key the printed counter; one value for both outcomes would hide the failures."""
    assert ss.STATUS_SCORED != ss.STATUS_NO_LENS


def test_eod_parses_to_a_date() -> None:
    assert ss.parser().parse_args(["--eod", "2026-09-07"]).eod.isoformat() == "2026-09-07"


# ── the row it writes, against the table it writes to ─────────────────────────


def test_every_written_column_exists_in_lens_scores_daily() -> None:
    unknown = written_columns() - ddl_columns("lens_scores_daily")
    assert not unknown, f"columns lens_scores_daily does not have: {sorted(unknown)}"


def test_the_four_sub_scores_and_the_cohort_are_among_them() -> None:
    """P2-D's deliverable: the technical lens, its four sub-scores, and the cohort."""
    written = written_columns()
    assert {"technical", "tech_trend", "tech_rs", "tech_vol_contraction", "tech_volume"} <= written
    assert {"cap_cohort", "composite", "conviction_tier", "lenses_active"} <= written
    assert {"coverage_factor", "evidence", "compute_run_id", "asset_class"} <= written


def test_computed_at_is_written_because_the_table_has_no_default() -> None:
    """``etf_scores_daily.computed_at`` defaults to now(); this table's does not. Unwritten it
    lands NULL, and a score row that cannot say when it was computed is not a journal entry."""
    assert "computed_at" in written_columns()
    assert "DEFAULT" not in ddl_block("lens_scores_daily").split("computed_at")[1].split(",")[0]


# ── the lens set agrees with the seeded weights ───────────────────────────────


def test_every_blended_lens_has_a_seeded_weight() -> None:
    """``blend()`` KeyErrors on a lens with no ``lens_weight_*`` row — correctly, and at the
    first scored stock on the box. The seed table and this tuple must agree here instead."""
    seeded = {
        str(r["threshold_key"]).removeprefix("lens_weight_")
        for r in seed_thresholds.SEEDS
        if str(r["threshold_key"]).startswith("lens_weight_")
    }
    assert set(ss.LENSES) == seeded


def test_valuation_is_not_blended() -> None:
    """§B makes valuation an overlay (zone + multiplier), not a composite term: it carries no
    weight key, so including it here would KeyError every night."""
    assert "valuation" not in ss.LENSES


# ── the write path, end to end, on a member with nothing to score ─────────────


def unmeasured_row(member: str) -> dict[str, object]:
    """One target row for a REAL S&P 500 member whose metrics are all absent.

    A real state, not an invented one: a name added to the index this week has a
    ``universe_snapshot`` row and an empty ``technical_daily`` row long before it has 200
    sessions of EMAs. Its identity comes from the repo's own minting rule over the real
    Nasdaq/SEC directory files (``scaffold_identity``), so no number and no id here is typed
    in — and no metric is invented, because every metric is ABSENT.
    """
    row = next(r for r in scaffold_rows() if r.symbol == member)
    absent = dict.fromkeys(_METRIC_COLUMNS)
    return {
        "instrument_id": row.instrument_id,
        "symbol": row.symbol,
        "name": row.name,
        "weight_frac": None,
        "cap_cohort": ss.LIGHTEST_COHORT,
        "cohort_source": ss.COHORT_NO_WEIGHT,
        **absent,
    }


def seeded_thresholds() -> dict[str, Decimal]:
    return {
        str(r["threshold_key"]): Decimal(str(r["threshold_value"])) for r in seed_thresholds.SEEDS
    }


def test_scoring_a_member_with_no_metrics_writes_a_row_that_says_so() -> None:
    """The whole write path over the REAL seed table: no lens has inputs, so the composite is
    NULL and the tier is the floor. Nothing is 0, and nothing raises.

    This is also the guard for the argument that breaks a scorer on the box and nowhere else:
    ``blend()``'s fourth parameter is the conviction-TIER ladder, not the lens order. A lens
    tuple passed there raises ``KeyError: blend: tiers has no entry for [...]`` on the first
    scored row — and no unit test that stops at the pure lens would ever see it.
    """
    frame = pd.DataFrame([unmeasured_row("AAPL")])
    table, lines = ss.score_rows(frame, dt.date(2026, 9, 4), seeded_thresholds(), "run")
    assert len(table) == 1 and len(lines) == 1
    row = table.iloc[0]
    assert row["asset_class"] == "stock"
    assert row["technical"] is None and row["composite"] is None
    assert row["conviction_tier"] == "BELOW_THRESHOLD"
    assert row["lenses_active"] == 0
    assert row["coverage_factor"] == 0
    assert row["cap_cohort"] == ss.LIGHTEST_COHORT
    assert lines[0][-1] == ss.STATUS_NO_LENS
    assert row["computed_at"].tzinfo is not None, "tz-aware timestamps (rule #2)"


def test_the_report_line_the_writer_builds_fits_the_header_it_declares() -> None:
    """``Report.add`` is positional: a line shorter or longer than the header is a ValueError
    on the first stock, after the query has already run."""
    frame = pd.DataFrame([unmeasured_row("MSFT")])
    _table, lines = ss.score_rows(frame, dt.date(2026, 9, 4), seeded_thresholds(), "run")
    report = ss.Report(None, ss.REPORT_COLUMNS)
    report.add(*lines[0])
    assert report.counts == {ss.STATUS_NO_LENS: 1}


# ── the fundamental lens: it needs BOTH a metric set and the FM's bands ──


def _apple_metrics(as_of: dt.date = dt.date(2026, 9, 4)):
    """Apple's real point-in-time metric set, from the committed company-facts payload."""
    import json

    from atlas.global_market.fundamentals.facts import extract_rows
    from atlas.global_market.fundamentals.metrics import metrics_as_of

    payload = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "tests"
            / "fixtures"
            / "global"
            / "edgar"
            / "companfacts.json".replace("companfacts", "companyfacts_AAPL_CIK0000320193")
        ).read_text()
    )
    found = metrics_as_of(extract_rows(payload), as_of, is_financial=False)
    assert found is not None
    return found


def test_the_seed_table_does_not_carry_the_fundamental_bands_yet() -> None:
    """The US bands are cut from the live cross-section, not written into the seed file. Until
    they are in the table the lens must not score — India's numbers are named for India's index.

    The gate asks for the REACHABLE set, not all 37: the three quick-ratio rungs grade an input
    no US filer supplies (``stock_lenses.QUICK_RATIO_KEYS``), and a band no code path reads
    cannot fall back to India's number, which is the only thing this gate exists to prevent.
    """
    missing = ss.missing_bands(seeded_thresholds())
    assert set(missing) == set(REACHABLE_KEYS)
    assert not (set(missing) & QUICK_RATIO_KEYS)
    assert REACHABLE_KEYS | QUICK_RATIO_KEYS == set(FUNDAMENTAL_KEYS)


def test_metrics_without_bands_do_not_score_the_lens() -> None:
    """The refusal that matters: real inputs, no approved bands, so ``fundamental`` is NULL and
    the composite is the technical read alone."""
    frame = pd.DataFrame([unmeasured_row("AAPL")])
    iid = frame.iloc[0]["instrument_id"]
    table, _ = ss.score_rows(
        frame,
        dt.date(2026, 9, 4),
        seeded_thresholds(),
        "run",
        {str(iid): _apple_metrics()},
        bands_locked=False,
    )
    assert table.iloc[0]["fundamental"] is None
    assert table.iloc[0]["lenses_active"] == 0


def test_with_bands_locked_a_real_metric_set_scores_the_lens() -> None:
    """India's own numbers stand in for the bands ONLY here, to prove the wiring: real Apple
    ratios in, a fundamental score and its five sub-scores out, and the composite now counts
    two lenses instead of one."""
    import re

    india = dict(seeded_thresholds())
    source = (
        Path(__file__).resolve().parents[3] / "atlas" / "lenses" / "compute" / "fundamental.py"
    ).read_text()
    india |= {
        key: Decimal(value)
        for key, value in re.findall(r'_t\(\s*th,\s*"([a-z0-9_]+)",\s*([0-9.]+)\)', source)
    }
    assert not ss.missing_bands(india)

    frame = pd.DataFrame([unmeasured_row("AAPL")])
    iid = frame.iloc[0]["instrument_id"]
    table, lines = ss.score_rows(
        frame, dt.date(2026, 9, 4), india, "run", {str(iid): _apple_metrics()}, bands_locked=True
    )
    row = table.iloc[0]
    assert row["fundamental"] is not None and Decimal(0) <= row["fundamental"] <= Decimal(100)
    assert row["fund_profitability"] is not None
    assert row["composite"] is not None
    assert row["lenses_active"] == 1  # technical still has no inputs on an unmeasured row
    assert lines[0][-1] == ss.STATUS_SCORED


def test_the_cross_section_reports_every_metric_the_lens_bands() -> None:
    """The table the FM sets bands from: one row per lens input, per-cent for the six rates and
    a plain multiple for the three balance-sheet ratios, over the names that HAVE each."""
    table = ss.cross_section({"a": _apple_metrics()}, None)
    assert list(table.columns) == list(xsec.COLUMNS)
    assert list(table["metric"]) == [name for name, _ in xsec.LENS_METRICS]
    assert set(table["unit"]) <= {"percent", "ratio"}
    roe = table.loc[table["metric"] == "roe"].iloc[0]
    assert roe["unit"] == "percent"
    assert roe["names"] == 1
    apple_roe = _apple_metrics().roe
    assert apple_roe is not None
    assert roe["p50"] == pytest.approx(float(apple_roe) * 100, rel=1e-6)
    # Apple files no quarterly interest expense, so the metric has no cross-section at all.
    absent = table.loc[table["metric"] == "interest_cover"].iloc[0]
    assert absent["names"] == 0 and pd.isna(absent["p50"])
    ss.print_cross_section(table, ss.missing_bands(seeded_thresholds()))  # must not print "nan"
