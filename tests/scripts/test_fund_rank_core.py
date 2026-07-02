"""Unit tests for scripts/foundation/fund_rank_core.py — the composite + within-category
rank + percentile-band math that powers the daily fund-rank history.

This Python core MUST produce the IDENTICAL number to the live frontend
(`frontend/src/lib/v6/fundScore.ts` → `sectorScore.ts`), because the history's
"today" row has to equal what the funds page shows. The fixtures below are the SAME
REAL holdings-weighted lens vectors used in the TS test (fundScore.test.ts) — real
records pulled from atlas_foundation (snapshot 2026-06-26), NO synthetic inputs
(rule #0). Reproducing the TS expected outputs here proves the port is faithful.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import fund_rank_core as C  # noqa: E402

pytestmark = pytest.mark.unit

# Real holdings-weighted lens vectors (atlas_foundation, 2026-06-26 snapshot) — three
# India Multi-Cap funds. Same fixtures as the TS test; NOT synthetic.
BANK_OF_INDIA = {"v_tech": 62.09, "v_fund": 54.47, "v_flow": 25.25, "v_cat": 48.9}
GROWW = {"v_tech": 68.61, "v_fund": 63.8, "v_flow": 23.52, "v_cat": 47.95}
HSBC = {"v_tech": 66.47, "v_fund": 59.92, "v_flow": 23.64, "v_cat": 48.41}

# TS DEFAULT_WEIGHTS (sectorScore.ts) — used to prove parity with the documented TS outputs.
W_DEFAULT = {"technical": 0.30, "fundamental": 0.25, "flow": 0.25, "catalyst": 0.20}
# The live 2-lens model (atlas_thresholds): Technical .60 / Flow .40, others 0.
W_2LENS = {"technical": 0.60, "fundamental": 0.0, "flow": 0.40, "catalyst": 0.0}


class TestComposite:
    def test_matches_ts_default_weights_all_lenses_present(self):
        # Identical expected values to fundScore.test.ts → proves the port is faithful.
        assert C.composite(BANK_OF_INDIA, W_DEFAULT) == pytest.approx(48.34, abs=0.01)
        assert C.composite(GROWW, W_DEFAULT) == pytest.approx(52.0, abs=0.01)
        assert C.composite(HSBC, W_DEFAULT) == pytest.approx(50.514, abs=0.01)

    def test_two_lens_blend_renormalises_over_weighted_lenses(self):
        # Only Technical (.60) and Flow (.40) carry weight; Fund/Cat are context (w=0).
        # composite = (0.60*v_tech + 0.40*v_flow) / (0.60+0.40)
        expected = (0.60 * 62.09 + 0.40 * 25.25) / 1.0
        assert C.composite(BANK_OF_INDIA, W_2LENS) == pytest.approx(expected, abs=1e-9)

    def test_renormalises_when_a_weighted_lens_is_missing(self):
        # Flow missing under default weights → renormalise over tech/fund/cat (tw=0.75).
        v = {"v_tech": 60.0, "v_fund": 40.0, "v_flow": None, "v_cat": 50.0}
        expected = (0.30 * 60 + 0.25 * 40 + 0.20 * 50) / 0.75
        assert C.composite(v, W_DEFAULT) == pytest.approx(expected, abs=1e-9)

    def test_weight_zero_lens_present_does_not_move_score(self):
        # Under 2-lens, v_fund/v_cat present but weight 0 → ignored; only tech present here.
        v = {"v_tech": 70.0, "v_fund": 40.0, "v_flow": None, "v_cat": 50.0}
        assert C.composite(v, W_2LENS) == pytest.approx(70.0, abs=1e-9)

    def test_returns_none_when_no_weighted_lens_present(self):
        # All weighted lenses null → no composite.
        assert (
            C.composite({"v_tech": None, "v_fund": 40.0, "v_flow": None, "v_cat": 9.0}, W_2LENS)
            is None
        )
        assert (
            C.composite({"v_tech": None, "v_fund": None, "v_flow": None, "v_cat": None}, W_DEFAULT)
            is None
        )


class TestRankInCategory:
    def _mk(self, mstar_id, v, weights, breadth=0.0, category="India Fund Multi-Cap"):
        return {
            "mstar_id": mstar_id,
            "category": category,
            "breadth": breadth,
            "composite": C.composite(v, weights),
        }

    def test_ranks_by_composite_desc_with_size_over_scored_cohort(self):
        rows = [
            self._mk("boi", BANK_OF_INDIA, W_DEFAULT),
            self._mk("groww", GROWW, W_DEFAULT),
            self._mk("hsbc", HSBC, W_DEFAULT),
        ]
        out = {r["mstar_id"]: r for r in C.rank_in_category(rows)}
        assert out["groww"]["cat_rank"] == 1
        assert out["hsbc"]["cat_rank"] == 2
        assert out["boi"]["cat_rank"] == 3
        assert all(r["cat_size"] == 3 for r in out.values())

    def test_ties_broken_by_breadth_then_mstar_id(self):
        rows = [
            self._mk("low", HSBC, W_DEFAULT, breadth=0.1),
            self._mk("high", HSBC, W_DEFAULT, breadth=0.9),
        ]
        out = {r["mstar_id"]: r for r in C.rank_in_category(rows)}
        assert out["high"]["cat_rank"] == 1
        assert out["low"]["cat_rank"] == 2

    def test_identical_everything_breaks_by_mstar_id_unique_ranks(self):
        rows = [
            self._mk("bbb", HSBC, W_DEFAULT, breadth=0.5),
            self._mk("aaa", HSBC, W_DEFAULT, breadth=0.5),
        ]
        out = {r["mstar_id"]: r for r in C.rank_in_category(rows)}
        assert out["aaa"]["cat_rank"] == 1
        assert out["bbb"]["cat_rank"] == 2

    def test_separate_categories_rank_independently(self):
        rows = [
            self._mk("a", GROWW, W_DEFAULT, category="Large-Cap"),
            self._mk("b", HSBC, W_DEFAULT, category="Mid-Cap"),
        ]
        out = {r["mstar_id"]: r for r in C.rank_in_category(rows)}
        assert out["a"]["cat_rank"] == 1 and out["a"]["cat_size"] == 1
        assert out["b"]["cat_rank"] == 1 and out["b"]["cat_size"] == 1

    def test_unscored_fund_has_no_rank_but_counts_scored_size(self):
        rows = [
            self._mk("hsbc", HSBC, W_DEFAULT),
            {
                "mstar_id": "x",
                "category": "India Fund Multi-Cap",
                "breadth": 0.0,
                "composite": None,
            },
        ]
        out = {r["mstar_id"]: r for r in C.rank_in_category(rows)}
        assert out["x"]["cat_rank"] is None
        assert out["hsbc"]["cat_rank"] == 1
        assert out["hsbc"]["cat_size"] == 1


class TestPctBand:
    @pytest.mark.parametrize(
        "rank,size,band",
        [
            (1, 1, "Top 10%"),
            (1, 50, "Top 10%"),
            (5, 50, "Top 10%"),  # (5-1)/50 = 0.08 < 0.10
            (6, 50, "Top 20%"),  # (6-1)/50 = 0.10 -> next band
            (10, 50, "Top 20%"),  # 0.18 < 0.20
            (11, 50, "Top 50%"),  # 0.20 -> next band
            (25, 50, "Top 50%"),  # 0.48 < 0.50
            (26, 50, "Bottom 50%"),  # 0.50 -> next band
            (50, 50, "Bottom 50%"),
        ],
    )
    def test_bands(self, rank, size, band):
        assert C.pct_band(rank, size) == band

    def test_none_when_unranked(self):
        assert C.pct_band(None, 10) is None
        assert C.pct_band(3, 0) is None
