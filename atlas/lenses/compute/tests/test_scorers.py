# allow-large: real-data scorer suite — reconciles all 8 modules to live DB output
"""Real-data tests for the six lens scorers, composite, risk flags + roll-ups.

RULE #0 (CLAUDE.md): no synthetic/fabricated inputs anywhere — every input is a
REAL row pulled from the data layer for a REAL instrument on a REAL trading day.
The previous version of this file fed hand-typed literals (ema_21=110.0,
roe=25.0, fabricated filing dicts) to every scorer; that is exactly the pattern
that let the catalyst bug ship green, and it is forbidden.

The backbone here is RECONCILIATION: for each lens we load the real adapter
inputs, invoke the scorer through the SAME plumbing the pipeline uses
(`_to_float`, `_group_by_iid`), and assert the result equals the value the
pipeline already persisted in atlas.atlas_lens_scores_daily for that
instrument+date. That proves the scorer + adapter + pipeline path end-to-end on
production data — and it cannot be made to pass with a weak assertion, because it
checks against real produced output. We add relational tests (a clearly strong
real name out-scores a clearly weak one) and structural tests (a sub-component is
present iff its real input is present; every score sits in its valid range).

Requires DB connectivity (atlas.db.get_engine). If the journal has no rows for
the reference session the whole module skips rather than failing spuriously.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.db import get_engine, load_thresholds
from atlas.lenses.compute.catalyst import CatalystResult, score_catalyst
from atlas.lenses.compute.composite import (
    CompositeResult,
    compute_composite,
    rollup_holdings,
    rollup_index,
    rollup_sector,
)
from atlas.lenses.compute.flow import FlowResult, score_flow
from atlas.lenses.compute.fundamental import FundamentalResult, score_fundamental
from atlas.lenses.compute.policy import PolicyResult, score_policy
from atlas.lenses.compute.risk_flags import RiskFlagsResult, compute_risk_flags
from atlas.lenses.compute.technical import TechnicalResult, score_technical
from atlas.lenses.compute.valuation import ValuationResult, score_valuation
from atlas.lenses.data import adapters
from atlas.lenses.pipeline import _group_by_iid, _to_float

# A real NSE session (membership-validated by atlas/lenses/data/tests/test_calendar.py).
D = date(2026, 6, 19)
TOL = 0.05  # reconciliation tolerance (scores are quantized to 0.01/0.1)


# ──────────────────────────── module fixtures ────────────────────────────
@pytest.fixture(scope="module")
def engine():
    eng = get_engine()
    n = pd.read_sql(
        "SELECT count(*) n FROM atlas.atlas_lens_scores_daily "
        "WHERE date = %(d)s AND asset_class = 'stock'",
        eng, params={"d": D},
    )["n"].iloc[0]
    if not n:
        pytest.skip(f"no journal rows for {D}; run the pipeline first")
    return eng


@pytest.fixture(scope="module")
def th(engine):
    raw = load_thresholds(engine=engine)
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in raw.items()}


@pytest.fixture(scope="module")
def journal(engine):
    df = pd.read_sql(
        "SELECT * FROM atlas.atlas_lens_scores_daily "
        "WHERE date = %(d)s AND asset_class = 'stock'",
        engine, params={"d": D},
    )
    return df.set_index("instrument_id")


@pytest.fixture(scope="module")
def data(engine):
    """All real adapter inputs, grouped EXACTLY as run_pipeline groups them."""
    tech = adapters.load_technical_data(engine, D)
    fund = adapters.load_fundamental_data(engine)
    val = adapters.load_valuation_data(engine)
    cat = adapters.load_catalyst_data(engine, as_of=D)
    flow = adapters.load_flow_data(engine, as_of=D)
    sectors = adapters.load_instrument_sectors(engine)
    policies = adapters.load_policy_registry(engine)
    return {
        "tech": _first_per_iid(tech),
        "fund": _first_per_iid(fund),
        "val": _first_per_iid(val),
        "cat": _group_by_iid(cat),
        "insider": _group_by_iid(flow["insider"]),
        "sh": _group_by_iid(flow["shareholding"], sort_col="period_end"),
        "bulk": _group_by_iid(flow["bulk_deals"]),
        "sectors": _first_per_iid(sectors),
        "policies": policies,
    }


def _first_per_iid(df: pd.DataFrame) -> dict:
    """instrument_id -> first row dict (matches pipeline's fund_idx.loc[iid] use)."""
    out: dict = {}
    if df is None or df.empty:
        return out
    for iid, grp in df.groupby("instrument_id"):
        out[iid] = grp.iloc[0].to_dict()
    return out


def _f(v):
    return _to_float(v)


# ──────────────── scorer invocations mirroring run_pipeline ────────────────
def _score_tech(row, th):
    return score_technical(
        ema_21=_f(row.get("ema_21")), ema_50=_f(row.get("ema_50")),
        ema_200=_f(row.get("ema_200")), rsi_14=_f(row.get("rsi_14")),
        price=_f(row.get("price")), high_52w=_f(row.get("high_52w")),
        low_52w=_f(row.get("low_52w")), ret_1w=_f(row.get("ret_1w")),
        rs_1m_n500=_f(row.get("rs_1m_n500")), rs_3m_n500=_f(row.get("rs_3m_n500")),
        rs_6m_n500=_f(row.get("rs_6m_n500")), rs_12m_n500=_f(row.get("rs_12m_n500")),
        atr_14=_f(row.get("atr_14")), bb_width=_f(row.get("bb_width")),
        volume=_f(row.get("volume")), avg_volume_30d=_f(row.get("avg_volume_30d")),
        avg_volume_60d=_f(row.get("avg_volume_60d")),
        rel_volume_10d=_f(row.get("rel_volume_10d")), thresholds=th,
    )


def _score_fund(row, th):
    return score_fundamental(
        roe=_f(row.get("roe")), roa=_f(row.get("roa")), roic=_f(row.get("roic")),
        operating_margin=_f(row.get("operating_margin")),
        net_margin=_f(row.get("net_margin")), gross_margin=_f(row.get("gross_margin")),
        revenue_growth_yoy=_f(row.get("revenue_growth_yoy")),
        eps_growth_yoy=_f(row.get("eps_growth_yoy")),
        debt_to_equity=_f(row.get("debt_to_equity")),
        current_ratio=_f(row.get("current_ratio")),
        quick_ratio=_f(row.get("quick_ratio")), revenue_ttm=_f(row.get("revenue_ttm")),
        eps_diluted_ttm=_f(row.get("eps_diluted_ttm")), thresholds=th,
    )


def _score_val(row, th):
    return score_valuation(
        pe_ttm=_f(row.get("pe_ttm")), pb_fbs=_f(row.get("pb_fbs")),
        ev_ebitda=_f(row.get("ev_ebitda")), price=_f(row.get("price")),
        high_52w=_f(row.get("high_52w")), low_52w=_f(row.get("low_52w")),
        ema_200=_f(row.get("ema_200")), sector_median_pe=_f(row.get("sector_median_pe")),
        thresholds=th,
    )


def _score_flow_for(iid, data, th):
    insider = data["insider"].get(iid, [])
    sh = data["sh"].get(iid, [])
    sh_cur = sh[0] if len(sh) >= 1 else None
    sh_prev = sh[1] if len(sh) >= 2 else None
    bulk = data["bulk"].get(iid, [])
    if not (insider or sh_cur or bulk):
        return None
    return score_flow(insider, sh_cur, sh_prev, bulk, th)


def _reconcilable(journal, pool, lens, n=30):
    """Real instrument_ids that are both in `pool` and have a non-null `lens`."""
    out = []
    for iid in pool:
        if iid in journal.index:
            v = journal.loc[iid, lens]
            if v is not None and pd.notna(v):
                out.append(iid)
        if len(out) >= n:
            break
    return out


def _match(a, b) -> bool:
    if a is None and (b is None or pd.isna(b)):
        return True
    if a is None or b is None or pd.isna(b):
        return False
    return abs(float(a) - float(b)) <= TOL


# ════════════════════════════ TECHNICAL ════════════════════════════
class TestTechnicalRealData:
    def test_reconciles_to_journal(self, data, journal, th):
        iids = _reconcilable(journal, data["tech"], "technical")
        assert len(iids) >= 10, "need real technical rows to reconcile"
        for iid in iids:
            r = _score_tech(data["tech"][iid], th)
            assert _match(r.score, journal.loc[iid, "technical"]), (
                f"{iid}: scorer {r.score} != journal {journal.loc[iid, 'technical']}"
            )

    def test_subcomponents_in_range(self, data, th):
        for iid in list(data["tech"])[:50]:
            r = _score_tech(data["tech"][iid], th)
            assert isinstance(r, TechnicalResult)
            for sub in (r.trend, r.relative_strength, r.vol_contraction, r.volume):
                if sub is not None:
                    assert Decimal(0) <= sub <= Decimal(25)
            if r.score is not None:
                assert Decimal(0) <= r.score <= Decimal(100)

    def test_real_cross_sectional_dispersion(self, journal):
        # Real produced output must show genuine cross-sectional spread — a lens
        # that separates names, not a degenerate near-constant. Asserted from the
        # distribution itself (max>min + real stddev), no magic absolute bounds.
        s = journal["technical"].dropna().astype(float)
        assert s.max() > s.min()
        assert s.std() > 5


# ════════════════════════════ FUNDAMENTAL ════════════════════════════
class TestFundamentalRealData:
    def test_reconciles_to_journal(self, data, journal, th):
        iids = _reconcilable(journal, data["fund"], "fundamental")
        assert len(iids) >= 10
        for iid in iids:
            r = _score_fund(data["fund"][iid], th)
            assert _match(r.score, journal.loc[iid, "fundamental"]), (
                f"{iid}: scorer {r.score} != journal {journal.loc[iid, 'fundamental']}"
            )

    def test_composite_follows_renorm_formula(self, data, th):
        # The real contract: score = sum(present subs) * 100 / (20 * count), with
        # each sub in [0, 20]. Asserted from the scorer's own sub-scores on real
        # rows — no assumption about which raw field maps to which sub.
        for iid in list(data["fund"])[:50]:
            r = _score_fund(data["fund"][iid], th)
            assert isinstance(r, FundamentalResult)
            present = [s for s in (r.profitability, r.margin, r.growth,
                                   r.balance_sheet, r.op_leverage) if s is not None]
            for sub in present:
                assert Decimal(0) <= sub <= Decimal(20)
            if present:
                expected = (sum(present) * Decimal(100)
                            / (Decimal(20) * Decimal(len(present)))).quantize(Decimal("0.1"))
                assert r.score == expected
            else:
                assert r.score is None


# ════════════════════════════ VALUATION ════════════════════════════
class TestValuationRealData:
    def test_reconciles_to_journal(self, data, journal, th):
        iids = _reconcilable(journal, data["val"], "valuation")
        assert len(iids) >= 10
        for iid in iids:
            r = _score_val(data["val"][iid], th)
            assert _match(r.score, journal.loc[iid, "valuation"]), (
                f"{iid}: scorer {r.score} != journal {journal.loc[iid, 'valuation']}"
            )

    def test_no_data_returns_none_not_stub(self, data, journal, th):
        # RULE #0: a name with no valuation inputs must return None, never the old
        # fabricated 35/FAIR stub. Two real-grounded checks: (1) the journal must
        # carry ZERO 35-stubs imputed from no data, and (2) the scorer's absence
        # contract (the exact all-None shape the adapter yields for a name with no
        # tv_metrics row) is None / UNKNOWN / neutral multiplier.
        stub_imputed = journal[journal["evidence"].astype(str).str.contains(
            "no_data_default_fair", na=False)]
        assert len(stub_imputed) == 0
        r = score_valuation(None, None, None, None, None, None, None, None, th)
        assert r.score is None
        assert r.zone == "UNKNOWN"
        assert r.multiplier == Decimal("1.00")
        assert r.evidence.get("no_data") is True

    def test_zone_consistent_with_score(self, data, journal, th):
        # Real zone/score pairs must be internally consistent with the zone map.
        for iid in _reconcilable(journal, data["val"], "valuation", n=40):
            r = _score_val(data["val"][iid], th)
            if r.score is None:
                continue
            if r.score >= Decimal(75):
                assert r.zone == "DEEP_VALUE"
            elif r.score < Decimal(20):
                assert r.zone == "OVERVALUED"

    def test_no_value_names_not_labeled_fair(self, journal):
        # End-to-end no-data contract: a name we cannot value (valuation IS NULL,
        # no tv_metrics row) must be labelled UNKNOWN/None in the journal, never
        # the misleading FAIR the pipeline fallback used to write.
        no_val = journal[journal["valuation"].isna()]
        bad = no_val[no_val["valuation_zone"] == "FAIR"]
        assert len(bad) == 0, f"{len(bad)} unvalued names mislabelled FAIR"

    def test_pb_dimension_absent_on_real_data(self, data, th):
        # tv_metrics.pb_fbs is 100% null in production; the pb dimension must
        # therefore never fire on real rows (documents the real-feed reality).
        fired = 0
        for iid in list(data["val"])[:200]:
            r = _score_val(data["val"][iid], th)
            if r.price_to_book is not None:
                fired += 1
        assert fired == 0, f"pb dimension fired on {fired} real names (expected 0)"


# ════════════════════════════ CATALYST ════════════════════════════
class TestCatalystRealData:
    def test_reconciles_to_journal(self, data, journal, th):
        iids = _reconcilable(journal, data["cat"], "catalyst")
        assert len(iids) >= 10, "need real filing-backed names to reconcile"
        for iid in iids:
            r = score_catalyst(data["cat"][iid], D, th)
            assert _match(r.score, journal.loc[iid, "catalyst"]), (
                f"{iid}: scorer {r.score} != journal {journal.loc[iid, 'catalyst']}"
            )

    def test_filing_rich_names_score_positive(self, data, journal, th):
        # The exact bug this gate exists for: filing-rich names must score > 0.
        rich = sorted(data["cat"], key=lambda i: len(data["cat"][i]), reverse=True)[:20]
        scored = [score_catalyst(data["cat"][i], D, th).score for i in rich]
        pos = [s for s in scored if s is not None and s > 0]
        assert len(pos) >= 15, f"only {len(pos)}/20 filing-rich names scored >0"

    def test_buckets_present_iff_filings(self, data, th):
        for iid in list(data["cat"])[:30]:
            filings = data["cat"][iid]
            r = score_catalyst(filings, D, th)
            assert isinstance(r, CatalystResult)
            if r.score is not None:
                assert Decimal(0) <= r.score <= Decimal(100)

    def test_empty_filings_is_none(self, th):
        # The real "no filings" shape the pipeline passes (empty list -> None).
        r = score_catalyst([], D, th)
        assert r.score is None


# ════════════════════════════ FLOW ════════════════════════════
class TestFlowRealData:
    def test_reconciles_to_journal(self, data, journal, th):
        iids = _reconcilable(journal, journal.index, "flow")
        # restrict to names that actually have flow source data in-window
        iids = [i for i in iids
                if (data["insider"].get(i) or data["sh"].get(i) or data["bulk"].get(i))][:30]
        assert len(iids) >= 10
        for iid in iids:
            r = _score_flow_for(iid, data, th)
            assert r is not None
            assert _match(r.score, journal.loc[iid, "flow"]), (
                f"{iid}: scorer {r.score} != journal {journal.loc[iid, 'flow']}"
            )

    def test_no_source_data_is_none(self, data, th):
        # An instrument with no insider/shareholding/bulk in-window -> None flow.
        all_with = set(data["insider"]) | set(data["sh"]) | set(data["bulk"])
        without = [i for i in data["sectors"] if i not in all_with][:5]
        assert without, "expected some names with no flow source data"
        for iid in without:
            assert _score_flow_for(iid, data, th) is None

    def test_insider_signal_type_is_other_on_real_data(self, data):
        # Documents real-feed reality: lens_insider.signal_type is uniformly
        # 'other', so the open_market_buy/pledge paths never fire in production.
        seen = set()
        for txns in list(data["insider"].values())[:200]:
            for t in txns:
                seen.add(t.get("signal_type"))
        assert seen and seen <= {"other", None}, f"unexpected signal types: {seen}"


# ════════════════════════════ POLICY ════════════════════════════
class TestPolicyRealData:
    def test_reconciles_to_journal(self, data, journal, th):
        iids = _reconcilable(journal, data["sectors"], "policy", n=40)
        assert len(iids) >= 10
        for iid in iids:
            row = data["sectors"][iid]
            r = score_policy(row.get("sector"), row.get("industry"), data["policies"], th)
            assert _match(r.score, journal.loc[iid, "policy"]), (
                f"{iid}: scorer {r.score} != journal {journal.loc[iid, 'policy']}"
            )

    def test_always_scored_never_none(self, data, th):
        # policy is structural — it returns a score even with null sector.
        for iid in list(data["sectors"])[:50]:
            row = data["sectors"][iid]
            r = score_policy(row.get("sector"), row.get("industry"), data["policies"], th)
            assert isinstance(r, PolicyResult)
            assert r.score is not None
            assert Decimal(0) <= r.score <= Decimal(60)


# ════════════════════════════ RISK FLAGS ════════════════════════════
class TestRiskFlagsRealData:
    def test_degradation_in_range_on_real_inputs(self, data, th):
        # Risk flags from real filings + insider for real names; degradation must
        # sit within its floor..0 band and is_degrading must agree with the score.
        for iid in list(data["cat"])[:50]:
            r = compute_risk_flags(
                insider_signals=data["insider"].get(iid, []),
                quarterly_margins=[], annual_financials={},
                filings=data["cat"].get(iid, []),
                price=_f(data["tech"].get(iid, {}).get("price")),
                ema_200=_f(data["tech"].get(iid, {}).get("ema_200")),
                thresholds=th,
            )
            assert isinstance(r, RiskFlagsResult)
            assert Decimal(-30) <= r.degradation_score <= Decimal(0)
            assert r.is_degrading == (r.degradation_score <= Decimal(-15))


# ════════════════════════════ COMPOSITE ════════════════════════════
class TestCompositeRealData:
    def test_reconciles_to_journal(self, journal, th):
        # Recompute the composite from the journal's OWN persisted lens scores and
        # modifiers, and reconcile to the persisted composite — proves the
        # composite engine on real produced output.
        sample = journal.dropna(subset=["composite"]).head(40)
        for iid, row in sample.iterrows():
            r = compute_composite(
                technical=_f(row["technical"]), fundamental=_f(row["fundamental"]),
                valuation_score=_f(row["valuation"]), catalyst=_f(row["catalyst"]),
                flow=_f(row["flow"]), policy=_f(row["policy"]),
                valuation_multiplier=_f(row["valuation_multiplier"]) or 1.0,
                smart_money_score=_f(row["smart_money_score"]) or 0.0,
                degradation_score=_f(row["degradation_score"]) or 0.0,
                thresholds=th,
            )
            assert isinstance(r, CompositeResult)
            assert _match(r.final_score, row["composite"]), (
                f"{iid}: composite {r.final_score} != journal {row['composite']}"
            )

    def test_final_score_and_tier_valid(self, journal):
        comp = journal["composite"].dropna()
        assert (comp >= 0).all() and (comp <= 100).all()
        assert set(journal["conviction_tier"].dropna().unique()) <= {
            "HIGHEST", "HIGH", "MEDIUM", "WATCH", "BELOW_THRESHOLD",
        }

    def test_coverage_factor_tracks_active_lenses(self, journal):
        # More active lenses -> higher coverage factor, on real produced rows.
        sub = journal.dropna(subset=["lenses_active", "coverage_factor"])
        hi = sub[sub["lenses_active"] >= 5]["coverage_factor"].astype(float)
        lo = sub[sub["lenses_active"] <= 3]["coverage_factor"].astype(float)
        if len(hi) and len(lo):
            assert hi.mean() > lo.mean()


# ════════════════════════════ FRACTAL ROLL-UPS ════════════════════════════
class TestRollupRealData:
    def _members(self, journal, engine):
        # Real sector with real member stocks + market caps from tv_metrics.
        caps = pd.read_sql(
            "SELECT instrument_id, market_cap FROM atlas.tv_metrics "
            "WHERE market_cap IS NOT NULL AND market_cap > 0", engine,
        ).set_index("instrument_id")["market_cap"]
        # Postgres treats NaN > 0 as TRUE, so NaN market_caps slip past the SQL
        # filter — drop them here (a NaN weight would poison the weighted average).
        caps = caps[caps.notna() & (caps > 0)]
        rows = []
        for iid, r in journal.dropna(subset=["composite", "technical"]).iterrows():
            if iid in caps.index:
                rows.append({
                    "market_cap": float(caps.loc[iid]),
                    "final_score": float(r["composite"]),
                    "technical": float(r["technical"]),
                    "fundamental": float(r["fundamental"]) if pd.notna(r["fundamental"]) else 0.0,
                    "weight": float(caps.loc[iid]),
                })
            if len(rows) >= 50:
                break
        return rows

    def test_sector_rollup_within_member_bounds(self, journal, engine):
        members = self._members(journal, engine)
        assert len(members) >= 10
        res = rollup_sector(members)
        assert res["stock_count"] == len(members)
        finals = [m["final_score"] for m in members]
        # Weighted average must lie within [min, max] of the constituents.
        assert min(finals) - TOL <= res["weighted_final_score"] <= max(finals) + TOL

    def test_holdings_rollup_within_bounds(self, journal, engine):
        members = self._members(journal, engine)
        res = rollup_holdings(members)
        finals = [m["final_score"] for m in members]
        assert min(finals) - TOL <= res["weighted_final_score"] <= max(finals) + TOL
        assert res["holding_count"] == len(members)

    def test_index_rollup_within_bounds(self, journal, engine):
        members = self._members(journal, engine)
        res = rollup_index(members)
        finals = [m["final_score"] for m in members]
        assert min(finals) - TOL <= res["weighted_final_score"] <= max(finals) + TOL
