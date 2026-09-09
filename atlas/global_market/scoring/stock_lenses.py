"""Stock lens scorers — pure. Dict in, Decimal out; no database, no clock, no I/O.

The six stock lenses of ``docs/global/plan.md`` §B. This module implements the ONE that
today's nightly data can answer, and does not pretend about the rest:

    technical    ✅ every sub-score the lens has, from technical_daily
    fundamental  ✗  needs stock_financials_pit (EDGAR XBRL) — no producer yet (phase2.md P3-A)
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

from atlas.global_market.scoring.etf_lenses import LensResult
from atlas.lenses.compute import technical as india_technical

# Every threshold key India's `_score_trend` and `_score_relative_strength` read. Indexed,
# never defaulted — see the module docstring. Kept in sync with India's source by
# test_stock_lenses.test_technical_keys_covers_every_threshold_india_reads.
TECHNICAL_KEYS: tuple[str, ...] = (
    "ema_aligned_all",
    "ema_aligned_partial",
    "price_above_ema200_strong",
    "price_below_ema200_weak",
    "slope_strong_pct",
    "slope_weak_pct",
    "rs_golden_cross_pts",
    "rs_fast_above_mid_pts",
)

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


def india_thresholds(th: Mapping[str, Decimal]) -> dict[str, Any]:
    """The keys India's technical scorer reads, as the floats it does arithmetic in.

    Converting AT THIS BOUNDARY and nowhere else keeps the reuse honest — the values are
    still the global table's rows, and no money or stored score is touched: these are
    dimensionless band edges and point counts. ``etf_lenses.score_technical`` does the same
    at the same boundary, for the same two functions.
    """
    return {key: float(th[key]) for key in TECHNICAL_KEYS}


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
