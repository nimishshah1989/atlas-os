"""The stock technical lens adapter, exercised against the REAL seeded thresholds.

Rule #0: nothing here invents a market number. There are two kinds of input below and both
are real, following ``test_etf_lenses.py`` exactly:

* **The thresholds** come from ``seed_thresholds.SEEDS`` — the actual rows that go into
  ``atlas_global.atlas_thresholds``, read here rather than restated, so a seed the FM re-tunes
  cannot leave these assertions asserting a number the product no longer uses.
* **The instrument inputs** are POSITIONS RELATIVE TO THOSE SEEDED CUTS, not observations:
  "EMAs stacked", "a price above ``price_above_ema200_strong``", "a week above
  ``slope_strong_pct``". What is under test is the LADDER — does a stock on this side of a
  seeded cut get the seeded points — and that question has no market data in it.

The failure mode these tests exist for is the one rule #0 was written after: a sub-score
returning 0 (a real, bad score) where it means "no data". A company is not in a downtrend
because it listed last month, and a 0 there would drag a composite down with a number nobody
can trace.

The third test below is a different guard and the reason this module indexes its thresholds
at all: India's scorer reads ITS keys with ``th.get(key, default)``. If a key the global
table never seeded reached it, India's default would silently become this market's approved
methodology. :data:`stock_lenses.TECHNICAL_KEYS` is checked here against India's own source,
so adding a key there turns into a red test rather than an invisible number.
"""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal

import pytest

from atlas.global_market.scoring.etf_lenses import LensResult
from atlas.global_market.scoring.stock_lenses import (
    TECHNICAL_KEYS,
    TECHNICAL_SUBS,
    india_thresholds,
    score_technical,
)
from atlas.lenses.compute import technical as india_technical
from tests.unit.global_market.script_loader import load_global_script

pytestmark = pytest.mark.unit

seed_thresholds = load_global_script("seed_thresholds")


@pytest.fixture(scope="module")
def th() -> dict[str, Decimal]:
    """The real seed table as ``load_thresholds`` hands it to the scorers."""
    return {
        str(row["threshold_key"]): Decimal(str(row["threshold_value"]))
        for row in seed_thresholds.SEEDS
    }


def _uptrend_inputs(th: dict[str, Decimal]) -> dict[str, float]:
    """EMAs stacked, price well above the 200, a strong week — every term on the good side of
    its seeded cut. Positions relative to thresholds, not a real company's numbers."""
    ema_200 = 100.0
    return {
        "ema_21": 112.0,
        "ema_50": 108.0,
        "ema_200": ema_200,
        "price": ema_200 * (1 + float(th["price_above_ema200_strong"]) + 0.01),
        "ret_1w": float(th["slope_strong_pct"]) + 0.01,
        "rsi_14": 60.0,
    }


def _no_rs() -> dict[str, None]:
    """Every relative-strength column absent. India's scorer accepts them and, since the FM's
    2026-06-30 redefinition, reads none of them — so passing them cannot change a score, and
    these tests pin the sub-scores that DO move."""
    return {
        "rs_1m_spy": None,
        "rs_3m_spy": None,
        "rs_6m_spy": None,
        "rs_12m_spy": None,
    }


# ── the adapter reaches India's scorer, and reaches it with the global table ──


def test_technical_keys_covers_every_threshold_india_reads() -> None:
    """The list this module indexes must be India's full key set, or a default fires silently.

    Read out of India's own source: every ``th.get("key", default)`` inside the two sub-scorers
    the lens still uses. A key added there without being added here would be scored on India's
    literal — a methodology number this market never approved (rule #1).
    """
    source = inspect.getsource(india_technical)
    tree = ast.parse(source)
    functions = {"_score_trend", "_score_relative_strength"}
    read: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in functions):
            continue
        for call in ast.walk(node):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "get"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "th"
                and call.args
                and isinstance(call.args[0], ast.Constant)
            ):
                read.add(str(call.args[0].value))
    assert read, "found no threshold reads in India's scorer — the parse, not the code, broke"
    assert read == set(TECHNICAL_KEYS), (
        f"stock_lenses.TECHNICAL_KEYS is out of step with India's scorer: "
        f"missing {sorted(read - set(TECHNICAL_KEYS))}, stale {sorted(set(TECHNICAL_KEYS) - read)}"
    )


def test_every_indexed_key_is_actually_seeded(th: dict[str, Decimal]) -> None:
    """Indexing is only an improvement if the keys exist: otherwise every row raises."""
    assert not set(TECHNICAL_KEYS) - set(th)
    assert set(india_thresholds(th)) == set(TECHNICAL_KEYS)


def test_a_missing_threshold_key_fails_by_name_rather_than_defaulting(
    th: dict[str, Decimal],
) -> None:
    """The global convention scoring/blend.py sets: index the table, never ``.get(k, default)``.
    India's own scorer defaults; this adapter refuses to let it, because the first anyone would
    know of a silent default is a score nobody can explain."""
    incomplete = {k: v for k, v in th.items() if k != "ema_aligned_all"}
    with pytest.raises(KeyError, match="ema_aligned_all"):
        score_technical(**_uptrend_inputs(th), **_no_rs(), th=incomplete)


# ── the lens itself ──────────────────────────────────────────────────────────


def test_a_stock_in_a_clean_uptrend_scores_near_the_top_of_the_technical_lens(
    th: dict[str, Decimal],
) -> None:
    result = score_technical(**_uptrend_inputs(th), **_no_rs(), th=th)
    assert isinstance(result, LensResult)
    assert result.value is not None and result.value >= Decimal("90")


def test_an_inverted_stack_scores_far_below_a_clean_uptrend(th: dict[str, Decimal]) -> None:
    """Both ends of the ladder are measurements. Getting the orientation backwards would rank
    every downtrend at the top and nothing downstream would notice."""
    up = score_technical(**_uptrend_inputs(th), **_no_rs(), th=th)
    down = score_technical(
        ema_21=88.0,
        ema_50=94.0,
        ema_200=100.0,
        price=100.0 * (1 + float(th["price_below_ema200_weak"]) - 0.01),
        ret_1w=float(th["slope_weak_pct"]) - 0.01,
        rsi_14=35.0,
        **_no_rs(),
        th=th,
    )
    assert up.value is not None and down.value is not None
    assert down.value < up.value
    assert down.value == Decimal("0.00"), "a fully inverted stack earns no points, and is not None"


def test_the_lens_is_the_mean_of_present_subs_times_four(th: dict[str, Decimal]) -> None:
    """The 0–25 → 0–100 contract. Two of the four sub-scores are permanently absent (the FM
    removed volatility-contraction and volume on 2026-06-30), so the scale must come from the
    PRESENT ones or every US stock would be scored at half of what it earned."""
    result = score_technical(**_uptrend_inputs(th), **_no_rs(), th=th)
    present = [v for v in result.subs.values() if v is not None]
    assert len(present) == 2, "trend and RS-structure only"
    expected = (sum(present, Decimal("0")) / Decimal(len(present)) * 4).quantize(Decimal("0.01"))
    assert result.value == expected
    assert result.evidence["subs_present"] == 2


def test_the_two_removed_sub_scores_are_absent_not_zero(th: dict[str, Decimal]) -> None:
    """`tech_vol_contraction` and `tech_volume` are NULL because the lens no longer has them —
    a methodology fact. A 0 would say the stock is bad at something the lens does not measure."""
    result = score_technical(**_uptrend_inputs(th), **_no_rs(), th=th)
    assert result.subs["tech_vol_contraction"] is None
    assert result.subs["tech_volume"] is None


def test_a_stock_with_no_metrics_at_all_scores_none_not_zero(th: dict[str, Decimal]) -> None:
    result = score_technical(
        ema_21=None,
        ema_50=None,
        ema_200=None,
        price=None,
        ret_1w=None,
        rsi_14=None,
        **_no_rs(),
        th=th,
    )
    assert result.value is None
    assert all(v is None for v in result.subs.values())
    assert result.evidence["reason"] == "no sub-score had inputs"


def test_the_sub_score_keys_are_the_lens_scores_daily_column_names() -> None:
    """``score_stocks`` splats ``subs`` straight into the row, so a rename here is a failed
    INSERT on the box hours after ``make gate`` went green."""
    result_columns = [column for column, _attribute in TECHNICAL_SUBS]
    assert result_columns == ["tech_trend", "tech_rs", "tech_vol_contraction", "tech_volume"]


def test_the_rs_columns_reach_india_under_its_own_parameter_names() -> None:
    """The mapping this adapter exists for: ``rs_*_n500`` receives the SPY columns because SPY
    is this market's broad benchmark, ``rs_*_sector`` the GICS-sector-SPDR peer columns. India
    reads neither today, so this is asserted on the SIGNATURE — the day the FM restores that
    sub-score, a rename on either side is caught here rather than by a wrong score."""
    india = set(inspect.signature(india_technical.score_technical).parameters)
    assert {f"rs_{w}_n500" for w in ("1m", "3m", "6m", "12m")} <= india
    assert {f"rs_{w}_sector" for w in ("1m", "3m", "6m", "12m")} <= india
    ours = set(inspect.signature(score_technical).parameters)
    assert {f"rs_{w}_spy" for w in ("1m", "3m", "6m", "12m")} <= ours
    assert {f"rs_{w}_peer" for w in ("1m", "3m", "6m", "12m")} <= ours
