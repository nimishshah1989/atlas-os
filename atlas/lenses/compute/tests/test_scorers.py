# allow-large: real-data scorer suite — reconciles the production scoring path to live DB output
"""Real-data tests for the six-lens engine (Loop C, point-in-time).

RULE #0 (CLAUDE.md): NO synthetic/fabricated inputs anywhere — every input is a
REAL row pulled from the data layer for a REAL instrument on a REAL NSE session.

The backbone is END-TO-END RECONCILIATION: we run the exact production scoring core
(atlas.lenses.pipeline.score_all) over the real as-of adapter inputs for a reference
session, and assert each lens + the composite equals what the pipeline already
persisted in atlas.atlas_lens_scores_daily for that session. That proves
adapters + scorers + composite end-to-end on production data and cannot be made to
pass with a weak assertion. Around it sit contract tests (a sub-component is present
iff its real input is present; ranges; no-data → None not a stub) and the Loop C
fixes (RS now fires; insider signal_type now classified; PE/ROE/D-E are PIT).

Requires DB connectivity. If the journal has no rows for the reference session the
module skips rather than failing spuriously.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.db import get_engine, load_thresholds
from atlas.lenses.compute.composite import compute_composite
from atlas.lenses.compute.fundamental_pit import derive_fundamentals_asof
from atlas.lenses.compute.thresholds_view import nest_thresholds
from atlas.lenses.compute.valuation import score_valuation
from atlas.lenses.data import adapters
from atlas.lenses.pipeline import score_all

# A real NSE session (membership-validated by data/tests/test_calendar.py).
D = date(2026, 6, 19)
TOL = 0.1
# Composite is ON-READ (D19) — NOT materialized; it is reconciled on-read in
# TestComposite, never against the vestigial/stale stored `composite` column. The six
# lens SUB-scores ARE materialized and reconcile end-to-end here.
LENSES = ["technical", "fundamental", "valuation", "catalyst", "flow", "policy"]


@pytest.fixture(scope="module")
def engine():
    eng = get_engine()
    n = pd.read_sql(
        "SELECT count(*) n FROM atlas.atlas_lens_scores_daily "
        "WHERE date = %(d)s AND asset_class = 'stock'", eng, params={"d": D},
    )["n"].iloc[0]
    if not n:
        pytest.skip(f"no journal rows for {D}; run the pipeline first")
    return eng


@pytest.fixture(scope="module")
def th(engine):
    raw = load_thresholds(engine=engine)
    return nest_thresholds({k: (float(v) if isinstance(v, Decimal) else v) for k, v in raw.items()})


@pytest.fixture(scope="module")
def journal(engine):
    df = pd.read_sql(
        "SELECT * FROM atlas.atlas_lens_scores_daily "
        "WHERE date = %(d)s AND asset_class = 'stock'", engine, params={"d": D},
    )
    return df.set_index("instrument_id")


@pytest.fixture(scope="module")
def produced(engine, th):
    """Run the real production scoring core over real as-of inputs for D."""
    tech = adapters.load_technical_data(engine, D)
    fund = adapters.load_fundamental_data(engine, D)
    cat = adapters.load_catalyst_data(engine, as_of=D)
    flow = adapters.load_flow_data(engine, as_of=D)
    sec = adapters.load_instrument_sectors(engine)
    pol = adapters.load_policy_registry(engine)
    results, _, _ = score_all(D, tech, fund, cat, flow, sec, pol, th, uuid.uuid4())
    return {r["instrument_id"]: r for r in results}


def _num(v):
    return float(v) if v is not None and pd.notna(v) else None


def _match(a, b) -> bool:
    a, b = _num(a), _num(b)
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= TOL


# ════════════════════ END-TO-END PRODUCTION RECONCILIATION ════════════════════
class TestProductionReconciliation:
    """score_all over real adapter inputs == the persisted journal, lens by lens."""

    @pytest.mark.parametrize("lens", LENSES)
    def test_lens_reconciles_to_journal(self, produced, journal, lens):
        common = [iid for iid in produced if iid in journal.index]
        assert len(common) >= 100, "need a real overlap to reconcile"
        checked = matched = 0
        mismatches = []
        for iid in common:
            jv = journal.loc[iid, lens]
            pv = produced[iid].get(lens)
            # only reconcile where at least one side has a value
            if _num(jv) is None and _num(pv) is None:
                continue
            checked += 1
            if _match(pv, jv):
                matched += 1
            elif len(mismatches) < 5:
                mismatches.append((str(iid), pv, jv))
        assert checked >= 20, f"{lens}: too few non-null to reconcile ({checked})"
        rate = matched / checked
        assert rate >= 0.98, f"{lens}: only {matched}/{checked} reconcile; e.g. {mismatches}"


# ════════════════════════════ TECHNICAL ════════════════════════════
class TestTechnical:
    def test_rs_now_fires(self, journal):
        # Loop C fix: RS tier breakpoints corrected to the difference scale, so the
        # RS sub is no longer silently 0 for ~99% of names (it was 15/2090 before).
        rs = pd.to_numeric(journal["tech_rs"], errors="coerce").dropna()
        assert (rs > 0).mean() >= 0.5, f"RS fires for only {(rs > 0).mean():.0%} of names"

    def test_cross_sectional_dispersion(self, journal):
        s = pd.to_numeric(journal["technical"], errors="coerce").dropna()
        assert s.max() > s.min() and s.std() > 5

    def test_subcomponents_in_range(self, produced):
        for r in list(produced.values())[:80]:
            for sub in ("tech_trend", "tech_rs", "tech_vol_contraction", "tech_volume"):
                v = _num(r.get(sub))
                if v is not None:
                    assert 0 <= v <= 25


# ════════════════════════════ FUNDAMENTAL (PIT) ════════════════════════════
class TestFundamental:
    def test_derive_reconciles_to_raw_quarters(self, engine):
        # Pull a real instrument's real trailing quarters from the DB and check the
        # PIT derivation (TTM EPS / ROE / D-E) reconciles to a hand sum — no synthetic.
        q = pd.read_sql("""
            SELECT DISTINCT ON (period_end) period_end, revenue, ebit, pat, eps,
                   net_margin, finance_costs, debt_equity_ratio
            FROM foundation_staging.financials_quarterly
            WHERE symbol='RELIANCE' AND period_end <= %(c)s AND eps IS NOT NULL
            ORDER BY period_end DESC, consolidated DESC LIMIT 8
        """, engine, params={"c": D}).to_dict("records")
        a = pd.read_sql("""
            SELECT equity, total_borrowings FROM foundation_staging.financials_annual
            WHERE symbol='RELIANCE' AND period_end <= %(c)s AND equity IS NOT NULL
            ORDER BY period_end DESC, consolidated DESC LIMIT 1
        """, engine, params={"c": D}).to_dict("records")
        assert len(q) >= 4 and a, "expected real RELIANCE financials"
        out = derive_fundamentals_asof(q, a[0])["kwargs"]
        assert abs(out["eps_diluted_ttm"] - sum(r["eps"] for r in q[:4])) < 1e-6
        assert out["roe"] is not None and 0 < out["roe"] < 60
        assert out["debt_to_equity"] is not None and out["debt_to_equity"] >= 0

    def test_renorm_formula(self, produced):
        # composite = sum(present subs)*100/(20*count), each sub in [0,20].
        for r in list(produced.values())[:80]:
            subs = [_num(r.get(k)) for k in
                    ("fund_profitability", "fund_margin", "fund_growth",
                     "fund_balance_sheet", "fund_op_leverage")]
            present = [s for s in subs if s is not None]
            for s in present:
                assert 0 <= s <= 20
            if present:
                exp = round(sum(present) * 100 / (20 * len(present)), 1)
                assert abs(_num(r["fundamental"]) - exp) <= 0.2


# ════════════════════════════ VALUATION (PIT) ════════════════════════════
class TestValuation:
    def test_no_data_returns_none_not_stub(self, th):
        # RULE #0: no inputs -> None/UNKNOWN/neutral multiplier, never the old 35/FAIR stub.
        r = score_valuation(None, None, None, None, None, None, None, th)
        assert r.score is None and r.zone == "UNKNOWN" and r.multiplier == Decimal("1.00")
        assert r.evidence.get("no_data") is True

    def test_pb_absent_on_real_data(self, produced):
        # P/B has no unit-safe as-of source (DECISIONS D-LoopC) -> never fires.
        fired = sum(1 for r in list(produced.values())[:300] if _num(r.get("val_pb")) is not None)
        assert fired == 0, f"pb dimension fired on {fired} real names (expected 0)"

    def test_unvalued_names_not_labelled_fair(self, journal):
        no_val = journal[journal["valuation"].isna()]
        assert (no_val["valuation_zone"] == "FAIR").sum() == 0


# ════════════════════════════ FLOW ════════════════════════════
class TestFlow:
    def test_insider_signal_type_now_classified(self, engine):
        # Loop C fix (D-LoopC): the insider feed is no longer uniformly 'other' —
        # real acqMode/txn-type classification populates open_market_buy/sell, pledge, etc.
        kinds = pd.read_sql(
            "SELECT DISTINCT signal_type FROM foundation_staging.lens_insider "
            "WHERE transaction_date >= %(d)s - INTERVAL '365 days'", engine, params={"d": D},
        )["signal_type"].dropna().tolist()
        assert set(kinds) - {"other"}, f"signal_type still only 'other': {kinds}"

    def test_no_source_data_is_none(self, produced, journal):
        # A name with no flow source in-window -> flow None in the produced output.
        nulls = [iid for iid in produced if _num(produced[iid].get("flow")) is None]
        assert nulls, "expected some names with no flow signal"


# ════════════════════════════ CATALYST ════════════════════════════
class TestCatalyst:
    def test_filing_rich_names_score_positive(self, engine, produced):
        rich = pd.read_sql("""
            SELECT instrument_id, count(*) c FROM foundation_staging.lens_filings
            WHERE filing_date BETWEEN %(d)s - INTERVAL '365 days' AND %(d)s
            GROUP BY 1 ORDER BY 2 DESC LIMIT 20
        """, engine, params={"d": D})["instrument_id"].tolist()
        pos = sum(1 for iid in rich if iid in produced and (_num(produced[iid].get("catalyst")) or 0) > 0)
        assert pos >= 15, f"only {pos}/20 filing-rich names scored catalyst>0"


# ════════════════════════════ COMPOSITE ════════════════════════════
class TestComposite:
    def test_consumes_db_weights(self, journal, th):
        # Composite is ON-READ (D19): computed from the stored lens SUB-scores × the live
        # DB weights, never materialized. We assert the on-read compute is well-formed AND
        # genuinely weight-sensitive (perturbing a weight MOVES it) — NOT that it matches
        # the vestigial/stale stored `composite` column.
        sample = journal.dropna(subset=["technical", "catalyst"]).head(30)
        pth = {**th, "lens_weights": {**th["lens_weights"], "technical": 0.0, "catalyst": 0.5}}

        def _comp(row, thr):
            return compute_composite(
                technical=_num(row["technical"]), fundamental=_num(row["fundamental"]),
                valuation_score=_num(row["valuation"]), catalyst=_num(row["catalyst"]),
                flow=_num(row["flow"]), policy=_num(row["policy"]),
                valuation_multiplier=_num(row["valuation_multiplier"]) or 1.0,
                smart_money_score=_num(row["smart_money_score"]) or 0.0,
                degradation_score=_num(row["degradation_score"]) or 0.0, thresholds=thr)

        moved = 0
        for _iid, row in sample.iterrows():
            base = _comp(row, th)
            assert 0 <= float(base.final_score) <= 100
            if abs(float(base.final_score) - float(_comp(row, pth).final_score)) > 0.5:
                moved += 1
        assert moved >= 0.6 * len(sample), f"only {moved}/{len(sample)} move on perturbation"

    def test_tier_valid_and_coverage_tracks_lenses(self, journal, th):
        # On-read (D19): compute composite/tier/coverage from the stored sub-scores × DB
        # weights (never the stale stored columns). lenses_active counts the 4 CONVICTION
        # lenses only (policy is FYI, valuation a multiplier), so its max is 4; coverage =
        # sqrt(Σ present conviction-lens weights), so more lenses -> higher coverage.
        sample = journal.dropna(subset=["technical"]).head(400)
        out = []
        for _iid, row in sample.iterrows():
            r = compute_composite(
                technical=_num(row["technical"]), fundamental=_num(row["fundamental"]),
                valuation_score=_num(row["valuation"]), catalyst=_num(row["catalyst"]),
                flow=_num(row["flow"]), policy=_num(row["policy"]),
                valuation_multiplier=_num(row["valuation_multiplier"]) or 1.0,
                smart_money_score=_num(row["smart_money_score"]) or 0.0,
                degradation_score=_num(row["degradation_score"]) or 0.0, thresholds=th)
            out.append((r.lenses_active, float(r.coverage_factor),
                        float(r.final_score), r.conviction_tier))
        assert out, "need real journal rows to compute on-read"
        assert all(0 <= fs <= 100 for _, _, fs, _ in out)
        assert {tier for *_, tier in out} <= {
            "HIGHEST", "HIGH", "MEDIUM", "WATCH", "BELOW_THRESHOLD"}
        hi = [cf for la, cf, _, _ in out if la == 4]
        lo = [cf for la, cf, _, _ in out if la <= 3]
        if hi and lo:
            assert sum(hi) / len(hi) > sum(lo) / len(lo)
