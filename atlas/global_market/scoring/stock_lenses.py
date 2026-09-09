"""Stock lens scorers — pure. Dict in, Decimal out; no database, no clock, no I/O.

The six stock lenses of ``docs/global/plan.md`` §B. This module implements the ONE that
today's nightly data can answer, and does not pretend about the rest:

    technical    ✅ every sub-score the lens has, from technical_daily
    fundamental  ◐  complete and wired; it scores the moment ``atlas_global.atlas_thresholds``
                    carries all 37 bands. India's are named for India's index, so until the FM
                    locks the US ones the lens is NULL rather than borrowed
                    (see FUNDAMENTAL_KEYS, and the unit trap above it)
    valuation    ✗  same source, and its bands must be seeded from the live S&P 500
                    cross-section first (India's "PE under 8 is cheap" is nonsense here)
    catalyst     ✗  needs filings_8k + insider_form4 — no producer yet (P3-B)
    flow         ✗  needs insider_form4 / holders_13f_q / short_interest — no producer (P3-B)
    policy       ✗  not ported: zero weight in India, and no honest US registry exists

Absent lenses are ``None`` at the call site, ``blend()`` renormalises over what is present,
and ``lenses_active`` records how many that was. They are NOT zero: zero is a score, and a
company is not weak on fundamentals because nobody has written the EDGAR ingestor yet
(rule #0). Nothing here stubs an unbuilt lens — a stub is a number the FM cannot trace.

THIS IS AN ADAPTER, NOT A SECOND TECHNICAL LENS. ``atlas.lenses.compute.technical.
score_technical`` is a pure function over EMAs, a price, a weekly return and a set of
thresholds — no market, currency or venue in it — and §B names it as the US stock scorer
"verbatim". It is reached over the declared modulith edge ``atlas.global_market →
atlas.lenses.compute`` (ADR-0006 Decision 2, ``scripts/hooks/check_module_boundaries.py``),
exactly as ``etf_lenses`` reaches its two sub-scorers. Copying it would give two definitions
of a trend that must drift apart, and the FM would eventually be shown two different answers
to the same question about the same EMA stack.

WHAT THE MAPPING IS. India's parameters are named for India's benchmarks; the values this
market puts in them are the US ones:

    rs_{1m,3m,6m,12m}_n500    ←  technical_daily.rs_{1m,3m,6m,12m}_spy
    rs_{1m,3m,6m,12m}_sector  ←  technical_daily.rs_{1m,3m,6m,12m}_peer

``rs_*_n500`` receives ``rs_*_spy`` because SPY is this market's broad benchmark, the way the
Nifty 500 is India's — the same quantity, the same relative form ``(1+r_i)/(1+r_b) − 1``
(ADR-0002), against the index this market is actually measured by. ``rs_*_sector`` receives
the ``rs_*_peer`` columns, which for a US stock are computed against its GICS-sector SPDR
(``docs/global/plan.md`` §A). Both families are accepted by India's scorer and currently read
by none of its sub-scores — the FM removed the return-vs-benchmark RS on 2026-06-30 and
redefined the sub-score as EMA structure — so they change no number today. They are passed
anyway: the day the FM restores that sub-score, both markets get it from one definition, which
is the entire reason this module is an adapter instead of a copy. The same is true of
``atr_14 / bb_width / vol_ratio_30d / vol_ratio_60d / pos_52w``: volatility-contraction and
volume were removed from the lens on the same date, so India returns ``None`` for both
sub-scores whatever is passed, and the real columns are still handed over rather than
hard-wired to ``None`` here.

EVERY NUMBER COMES FROM ``atlas_global.atlas_thresholds`` (rule #1). India's scorer reads its
thresholds with ``.get(key, default)`` — the defaults are India's, written into India's code,
and if one fired here it would be a methodology number this market never approved, invisible
in a score nobody could explain. So :data:`TECHNICAL_KEYS` names every key the two sub-scorers
read and :func:`india_thresholds` INDEXES them: a key missing from the global table raises
``KeyError`` by name, at the first scored row, instead of quietly scoring the whole S&P 500 on
India's numbers. ``tests/unit/global_market/test_stock_lenses.py`` keeps that list honest
against India's source.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

# TECHNICAL_KEYS and india_thresholds live in etf_lenses (the lower module: stock_lenses
# imports it, so the definition cannot live here without a cycle). Re-exported so this
# module's own name for them, and the tests that pin it, keep working.
from atlas.global_market.scoring.etf_lenses import (
    TECHNICAL_KEYS,
    LensResult,
    india_thresholds,
)
from atlas.lenses.compute import fundamental as india_fundamental
from atlas.lenses.compute import technical as india_technical

# Re-exported: `TECHNICAL_KEYS` is pinned against India's own source by
# test_stock_lenses.test_technical_keys_covers_every_threshold_india_reads, which reads it
# from this module. __all__ makes the re-export explicit rather than an unused import.
__all__ = [
    "FUNDAMENTAL_KEYS",
    "QUICK_RATIO_KEYS",
    "REACHABLE_KEYS",
    "TECHNICAL_KEYS",
    "india_thresholds",
    "score_fundamental",
    "score_technical",
]

# The lens_scores_daily sub-score columns, in India's own order (ddl/05_scores.sql), mapped
# from the TechnicalResult attribute each one carries. `vol_contraction` and `volume` are the
# two the FM removed on 2026-06-30: India returns None for both, so both columns are NULL
# here — a fact about the methodology, not missing data.
TECHNICAL_SUBS: tuple[tuple[str, str], ...] = (
    ("tech_trend", "trend"),
    ("tech_rs", "relative_strength"),
    ("tech_vol_contraction", "vol_contraction"),
    ("tech_volume", "volume"),
)


def score_technical(
    *,
    ema_21: float | None,
    ema_50: float | None,
    ema_200: float | None,
    price: float | None,
    ret_1w: float | None,
    rsi_14: float | None,
    rs_1m_spy: float | None,
    rs_3m_spy: float | None,
    rs_6m_spy: float | None,
    rs_12m_spy: float | None,
    rs_1m_peer: float | None = None,
    rs_3m_peer: float | None = None,
    rs_6m_peer: float | None = None,
    rs_12m_peer: float | None = None,
    atr_14: float | None = None,
    bb_width: float | None = None,
    vol_ratio_30d: float | None = None,
    vol_ratio_60d: float | None = None,
    pos_52w: float | None = None,
    th: Mapping[str, Decimal],
) -> LensResult:
    """The technical lens (0–100) for one US stock — India's scorer, US inputs.

    Arguments are ``technical_daily`` column names; the mapping onto India's parameter names
    is in the module docstring. The result is ``etf_lenses.LensResult`` so the two markets'
    writers and the board's derivation tree read one shape: ``subs`` is keyed by the
    ``lens_scores_daily`` sub-score COLUMN names, ready to splat into the row.

    A stock with no EMAs scores ``None``, never 0 — a name listed last month has not been
    measured, and 0 would say its trend is bad.
    """
    result = india_technical.score_technical(
        ema_21=ema_21,
        ema_50=ema_50,
        ema_200=ema_200,
        rsi_14=rsi_14,
        price=price,
        ret_1w=ret_1w,
        # SPY is this market's broad benchmark, so the *_n500 parameters take the *_spy
        # columns; the sector parameters take the GICS-sector-SPDR RS columns.
        rs_1m_n500=rs_1m_spy,
        rs_3m_n500=rs_3m_spy,
        rs_6m_n500=rs_6m_spy,
        rs_12m_n500=rs_12m_spy,
        atr_14=atr_14,
        bb_width=bb_width,
        vol_ratio_30d=vol_ratio_30d,
        vol_ratio_60d=vol_ratio_60d,
        pos_52w=pos_52w,
        thresholds=india_thresholds(th),
        rs_1m_sector=rs_1m_peer,
        rs_3m_sector=rs_3m_peer,
        rs_6m_sector=rs_6m_peer,
        rs_12m_sector=rs_12m_peer,
    )
    subs: dict[str, Decimal | None] = {
        column: getattr(result, attribute) for column, attribute in TECHNICAL_SUBS
    }
    present = [value for value in subs.values() if value is not None]
    evidence: dict[str, Any] = dict(result.evidence)
    # The same evidence contract etf_lenses._lens writes, so one board component renders both.
    evidence |= {"subs_present": len(present)} if present else {"reason": "no sub-score had inputs"}
    return LensResult(result.score, subs, evidence)


# ── the fundamental lens ──────────────────────────────────────────────────────────────────

# THE UNIT TRAP, and it is the reason this adapter exists rather than a direct call.
# ``fundamentals.ratios`` returns FRACTIONS — return on equity is net income ÷ equity, 0.20 for
# twenty per cent — because that is what a ratio is and what the columns store. India's scorer
# reads PERCENTS: its ROE ladder starts at 20, its margin ladder at 20, its revenue-growth
# ladder at 25. Hand it 0.20 and every S&P 500 company falls below the bottom rung of every
# profitability, margin and growth band — a full cross-section of plausible, evenly
# distributed, uniformly wrong scores that nothing downstream could flag.
#
# So the six RATE inputs are multiplied by a hundred here, at the boundary, and the three
# PURE RATIOS (debt/equity, current, quick — 0.3, 2.0, 1.5 on India's ladders) are not. Which
# is which is the whole content of this function, and
# ``test_stock_lenses.test_a_fraction_is_not_a_percent`` pins it on real filings.
RATE_INPUTS = ("roe", "roce", "operating_margin", "net_margin", "revenue_growth", "eps_growth")
RATIO_INPUTS = ("debt_to_equity", "current_ratio", "quick_ratio")
PERCENT = Decimal(100)

FUNDAMENTAL_KEYS: tuple[str, ...] = (
    "bs_cr_good",
    "bs_cr_high",
    "bs_cr_ok",
    "bs_de_high",
    "bs_de_low",
    "bs_de_med",
    "bs_de_ok",
    "bs_qr_good",
    "bs_qr_high",
    "bs_qr_ok",
    "growth_eps_good",
    "growth_eps_high",
    "growth_eps_ok",
    "growth_rev_good",
    "growth_rev_high",
    "growth_rev_ok",
    "margin_net_good",
    "margin_net_high",
    "margin_net_ok",
    "margin_op_good",
    "margin_op_high",
    "margin_op_low",
    "margin_op_ok",
    "olev_de_low",
    "olev_margin_expand",
    "olev_rev_high",
    "olev_rev_mod",
    "prof_nm_high",
    "prof_nm_ok",
    "prof_roce_good",
    "prof_roce_high",
    "prof_roce_low",
    "prof_roce_ok",
    "prof_roe_good",
    "prof_roe_high",
    "prof_roe_low",
    "prof_roe_ok",
)

# THE THREE BANDS NOTHING CAN READ. `bs_qr_{ok,good,high}` grade a QUICK ratio, which needs
# inventory; ``stock_financials_pit`` carries none, ``Metrics`` has no ``quick_ratio`` field, and
# India's balance-sheet sub-score skips an absent input rather than penalising it — so these
# rungs are never evaluated for any US filer today.
#
# They are excluded from the gate below, and the exclusion is NOT a weakening of it. The gate
# exists so that no band silently falls back to India's number (``.get(key, default)``); a band
# no code path reads cannot fall back to anything. Requiring them would instead hold a working
# lens hostage to a threshold nothing consults.
#
# ``test_fundamental_lens`` ties this set to its REASON — the absence of a ``quick_ratio`` on
# ``Metrics`` — so the day inventory lands in the table, that test goes red and forces the three
# keys back into the required set at the same moment their input arrives.
QUICK_RATIO_KEYS: frozenset[str] = frozenset({"bs_qr_ok", "bs_qr_good", "bs_qr_high"})

#: The bands a US filer's score can actually depend on — what ``score_stocks`` requires before
#: it will score the fundamental lens at all.
REACHABLE_KEYS: frozenset[str] = frozenset(FUNDAMENTAL_KEYS) - QUICK_RATIO_KEYS

# lens_scores_daily's fundamental sub-score columns (ddl/05_scores.sql) ← FundamentalResult.
FUNDAMENTAL_SUBS: tuple[tuple[str, str], ...] = (
    ("fund_profitability", "profitability"),
    ("fund_margin", "margin"),
    ("fund_growth", "growth"),
    ("fund_balance_sheet", "balance_sheet"),
    ("fund_op_leverage", "op_leverage"),
)


def _percent(value: Decimal | None) -> float | None:
    """A fraction as the per-cent number India's ladders are written in."""
    return None if value is None else float(value * PERCENT)


def _plain(value: Decimal | None) -> float | None:
    """A ratio that is already on India's scale — a multiplier, not a rate."""
    return None if value is None else float(value)


def score_fundamental(
    *,
    roe: Decimal | None,
    roce: Decimal | None,
    operating_margin: Decimal | None,
    net_margin: Decimal | None,
    revenue_growth: Decimal | None,
    eps_growth: Decimal | None,
    debt_to_equity: Decimal | None,
    current_ratio: Decimal | None,
    quick_ratio: Decimal | None = None,
    th: Mapping[str, Decimal],
) -> LensResult:
    """The fundamental lens (0–100) for one US stock — India's scorer, US inputs, US bands.

    Every argument is a ``fundamentals.ratios`` output: a FRACTION for the six rates, a plain
    multiple for the three balance-sheet ratios. The conversion is above; do not pass
    per-cent numbers in.

    ``quick_ratio`` is ``None`` for every filer today: it needs inventory, which
    ``stock_financials_pit`` does not carry. India's balance-sheet sub-score skips an absent
    input rather than penalising it, so the sub-score is the debt/equity and current-ratio
    read — honestly two of three, not a guess at the third.

    A financial company arrives with ``debt_to_equity`` and ``current_ratio`` already ``None``
    (``ratios`` suppresses them at the source), so its balance-sheet sub-score is absent and
    the lens renormalises over the four that are not — India's own stance on banks.
    """
    result = india_fundamental.score_fundamental(
        roe=_percent(roe),
        roce=_percent(roce),
        operating_margin=_percent(operating_margin),
        net_margin=_percent(net_margin),
        revenue_growth_yoy=_percent(revenue_growth),
        eps_growth_yoy=_percent(eps_growth),
        debt_to_equity=_plain(debt_to_equity),
        current_ratio=_plain(current_ratio),
        quick_ratio=_plain(quick_ratio),
        # Accepted by India's signature and read by none of its sub-scorers; passed as None
        # rather than invented, so the day a sub-score starts reading one, nothing here lies.
        roa=None,
        roic=None,
        gross_margin=None,
        revenue_ttm=None,
        eps_diluted_ttm=None,
        thresholds=india_thresholds(th, FUNDAMENTAL_KEYS),
    )
    subs: dict[str, Decimal | None] = {
        column: getattr(result, attribute) for column, attribute in FUNDAMENTAL_SUBS
    }
    present = [value for value in subs.values() if value is not None]
    evidence: dict[str, Any] = dict(result.evidence)
    evidence |= {"subs_present": len(present)} if present else {"reason": "no sub-score had inputs"}
    return LensResult(result.score, subs, evidence)
