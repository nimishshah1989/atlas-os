"""Real-data tests for the v2 capability-app data layer widening (Rule #0: no
fixtures — every assertion runs against the live wealth.* tables)."""
import json
import sys

sys.path.insert(0, "scripts/wealth")

from build_capability_app import fetch, render  # noqa: E402
from engine_common import connect  # noqa: E402

# client_id=1: confirmed (via live psql) to have real rows in every source
# table this task widens — holdings, client_scorecard, client_flags,
# client_churn_risk, client_stock_exposure, client_segments, client_curves,
# fund_performance (via a held scheme) and cut_list.
SAMPLE_CLIENT = "1"


def _data():
    conn = connect()
    data = fetch(conn)
    conn.close()
    return data


def test_sampled_client_has_all_v2_keys_with_real_content():
    data = _data()
    c = data["clients"][SAMPLE_CLIENT]
    for key in ("holdings", "scorecard", "flags", "churn", "stock_exposure",
                "segment", "curve", "cut_list"):
        assert key in c, f"missing key {key!r} on client {SAMPLE_CLIENT}"
    assert c["holdings"], "client should have >=1 holding row"
    assert c["scorecard"] is not None
    assert c["churn"] is not None
    assert c["stock_exposure"], "client should have >=1 stock exposure row"
    assert len(c["stock_exposure"]) <= 10, "stock_exposure embed must be top-10 only"
    assert c["segment"] is not None
    assert c["curve"] is not None and c["curve"]["months"]
    assert c["cut_list"] is not None
    # fund_performance is embedded ONCE as a top-level {scheme_id: perf} map
    # (deduped per final review); the client's held funds resolve into it.
    fp = data["fund_performance"]
    assert isinstance(fp, dict) and fp, "top-level fund_performance map must be non-empty"
    held = {str(h["scheme_id"]) for h in c["holdings"] if h.get("scheme_id") is not None}
    assert held & set(fp), "client's held funds should resolve in the fund_performance map"


def test_holdings_carry_asset_class_and_quality_tint():
    data = _data()
    holdings = data["clients"][SAMPLE_CLIENT]["holdings"]
    assert all(h["asset_class"] for h in holdings), "T6 groups holdings by asset_class"
    # at least one Atlas-scored holding should carry a quality tint
    assert any(h["quality"] is not None for h in holdings)


def test_curve_encoding_is_compact_parallel_arrays():
    curve = _data()["clients"][SAMPLE_CLIENT]["curve"]
    assert isinstance(curve["months"], list) and isinstance(curve["values"], list)
    assert len(curve["months"]) == len(curve["values"])
    assert curve["coverage_pct"] is None or isinstance(curve["coverage_pct"], (int, float))


def test_cohort_top_level_present_with_all_sections():
    data = _data()
    assert "cohort" in data
    cohort = data["cohort"]
    for key in ("headline", "segment_bar", "histograms", "waterfall", "scatter", "funnel"):
        assert key in cohort, f"cohort missing {key!r}"


def test_segment_bar_sums_to_full_client_count():
    data = _data()
    total = sum(row["count"] for row in data["cohort"]["segment_bar"])
    assert total == data["book"]["clients"] == 242


def test_six_histograms_present_with_medians():
    data = _data()
    hist = data["cohort"]["histograms"]
    expected = {"book_size_l", "tenure_years", "growth_gap_pp",
                "freak_out_pct", "effective_bets", "sip_health_pct"}
    assert set(hist) == expected
    for name, h in hist.items():
        assert h["n"] > 0, f"{name} histogram has no real data"
        assert h["median"] is not None


def test_waterfall_total_matches_its_components():
    data = _data()
    wf = data["cohort"]["waterfall"]
    total_row = wf[-1]
    assert total_row["label"].lower().startswith("total")
    parts = sum(r["value_cr"] for r in wf[:-1])
    assert round(parts, 2) == round(total_row["value_cr"], 2)


def test_scatter_has_real_points():
    data = _data()
    sc = data["cohort"]["scatter"]
    assert sc["points"]
    assert sc["churn_threshold"] is not None
    assert sc["book_threshold_cr"] is not None


def test_funnel_narrows_to_call_sheet():
    data = _data()
    stages = [s["n"] for s in data["cohort"]["funnel"]]
    assert stages[0] == 242
    assert stages[-1] <= 20
    assert stages == sorted(stages, reverse=True), "funnel stages must not widen"


def test_json_dumps_with_allow_nan_false_succeeds():
    data = _data()
    json.dumps(data, allow_nan=False)  # raises ValueError if any NaN/Inf slipped through


def test_rendered_app_stays_under_6mb():
    data = _data()
    html = render(data)
    size = len(html.encode("utf-8"))
    assert size < 6 * 1024 * 1024, f"rendered app is {size / 1e6:.2f} MB, must stay <6MB"
