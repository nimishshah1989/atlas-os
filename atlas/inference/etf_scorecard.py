"""ETF scorecard pipeline — 6-component composite ranking.

For each ETF in ``atlas_universe_etfs`` (active), computes six 0-100
component scores from the latest available data and weighted composite:

  1. matrix_conviction_score  — best POSITIVE-leaning conviction across
     tenures for the ETF (read from atlas_conviction_daily if present)
  2. sector_strength_score    — for sector ETFs: underlying sector
     strength_rank percentile; for broad ETFs: weighted-avg of sector
     strengths (degrades to 50.0 if sector states unavailable)
  3. tracking_quality_score   — 252d tracking error vs benchmark
     (passive) or alpha (active). Degrades to 50.0 when benchmark
     time-series missing
  4. aum_bracket_score        — sweet-spot bracket per atlas_thresholds
  5. liquidity_score          — log_med_tv_60d normalised within category
  6. expense_ratio_score      — inverse-TER percentile (lower = better)

Composite = weighted sum (weights live in atlas_thresholds, keys
``etf_weight_*``). Top ``etf_atlas_leader_pct`` per category →
``is_atlas_leader = TRUE``.

Outputs an ``ETFScoreRow`` list. CLI writes either live (when
``.supabase-write-approved`` marker present) or to a SQL file under the
``--output-dir``. Mirrors the conviction_tape.py CLI contract.

Missing-data handling: every component gracefully degrades to the
category median (50.0) and stamps the reason into ``raw_metrics`` so
the API can surface it.
"""

# allow-large: end-to-end ETF scorecard pipeline. Six component scorers,
# composite math, ELI5, SQL emitter live together because they share
# the ETFScoreRow shape and the universe row semantics — splitting
# would require duplicating typedicts across modules.

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ETFScoreRow:
    """One row of the daily ETF scorecard."""

    snapshot_date: date
    instrument_id: str
    isin: str | None
    ticker: str | None
    etf_name: str | None
    # broad_index / sector / thematic / commodity / international / debt / smart_beta
    etf_category: str
    underlying_sector: str | None
    matrix_conviction_score: Decimal | None
    sector_strength_score: Decimal | None
    tracking_quality_score: Decimal | None
    aum_bracket_score: Decimal | None
    liquidity_score: Decimal | None
    expense_ratio_score: Decimal | None
    composite_score: Decimal
    rank_in_category: int | None
    category_size: int | None
    is_atlas_leader: bool
    eli5: str | None
    raw_metrics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Threshold + universe loaders
# ---------------------------------------------------------------------------


_DEFAULT_WEIGHTS = {
    "etf_weight_matrix": Decimal("0.30"),
    "etf_weight_sector": Decimal("0.25"),
    "etf_weight_tracking": Decimal("0.15"),
    "etf_weight_aum": Decimal("0.10"),
    "etf_weight_liquidity": Decimal("0.10"),
    "etf_weight_expense": Decimal("0.10"),
    "etf_atlas_leader_pct": Decimal("25.0"),
    "etf_aum_sweet_spot_min_cr": Decimal("100.0"),
    "etf_aum_sweet_spot_max_cr": Decimal("50000.0"),
}


def _load_etf_thresholds(engine: Engine | None) -> dict[str, Decimal]:
    """Load atlas_thresholds for ETF keys; fall back to defaults if engine None."""
    if engine is None:
        return dict(_DEFAULT_WEIGHTS)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT threshold_key, threshold_value
                    FROM atlas.atlas_thresholds
                    WHERE is_active = TRUE AND category IN ('etf_rank','etf')
                    """
                )
            ).all()
        loaded = {k: Decimal(str(v)) for k, v in rows}
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("etf_thresholds_load_failed", error=str(exc))
        loaded = {}
    merged = dict(_DEFAULT_WEIGHTS)
    merged.update(loaded)
    return merged


_LOAD_ETFS_SQL = text(
    """
    SELECT
        u.ticker,
        u.isin,
        u.etf_name,
        u.theme,
        u.linked_sector,
        u.linked_index,
        u.asset_class,
        u.inception_date
    FROM atlas.atlas_universe_etfs u
    WHERE u.effective_to IS NULL
    ORDER BY u.ticker
    """
)


def _synth_etf_instrument_id(ticker: str | None, isin: str | None) -> str | None:
    """Synthesize a deterministic UUID5 for an ETF.

    ``atlas_universe_etfs`` does not carry a UUID — ETFs are keyed by
    ticker (and ISIN). The scorecard table requires a UUID
    ``instrument_id`` (NOT NULL) so we derive one from ISIN preferred,
    ticker fallback. Deterministic so reruns hit the ON CONFLICT path.
    """
    import uuid as _uuid

    seed = (isin or ticker or "").strip()
    if not seed:
        return None
    return str(_uuid.uuid5(_uuid.NAMESPACE_OID, f"atlas-etf::{seed}"))


def _load_etf_universe(engine: Engine) -> list[Mapping[str, Any]]:
    """Pull active ETF universe rows."""
    with engine.connect() as conn:
        rows = conn.execute(_LOAD_ETFS_SQL).mappings().all()
    out: list[Mapping[str, Any]] = []
    for r in rows:
        d = dict(r)
        # Inject a deterministic instrument_id derived from ISIN/ticker so
        # the scorecard table's NOT NULL UUID constraint is satisfied.
        d["instrument_id"] = _synth_etf_instrument_id(d.get("ticker"), d.get("isin"))
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Component scorers (each returns 0-100 Decimal + reason)
# ---------------------------------------------------------------------------


def _theme_to_category(theme: str | None, asset_class: str | None) -> str:
    """Map (theme, asset_class) → etf_category enum value."""
    t = (theme or "").lower()
    ac = (asset_class or "").lower()
    if "debt" in ac or "bond" in ac:
        return "debt"
    if "commodity" in ac or "gold" in ac or "silver" in ac:
        return "commodity"
    if "international" in ac or "global" in ac or "world" in ac:
        return "international"
    if "smart" in t or "factor" in t:
        return "smart_beta"
    if "sector" in t or t == "sectoral":
        return "sector"
    if "thematic" in t:
        return "thematic"
    return "broad_index"


def _percentile_rank(values: Sequence[float], target: float) -> float:
    """Return the percentile rank (0-100) of `target` within `values`.

    Higher values rank higher. Empty input → 50.0.
    """
    if not values:
        return 50.0
    below = sum(1 for v in values if v < target)
    equal = sum(1 for v in values if v == target)
    n = len(values)
    return ((below + 0.5 * equal) / n) * 100.0


def _inverse_percentile_rank(values: Sequence[float], target: float) -> float:
    """Lower-is-better percentile: invert the rank."""
    return 100.0 - _percentile_rank(values, target)


def score_matrix_conviction(
    instrument_id: str | None,
    conviction_rows: Mapping[str, list[Mapping[str, Any]]],
) -> tuple[Decimal, str]:
    """Score matrix conviction 0-100 from the conviction tape.

    Algorithm: for each tenure ('1m','3m','6m','12m') look at the verdict
    and friction-adjusted excess. POSITIVE=+1, NEUTRAL=0, NEGATIVE=-1.
    Composite signed score = sum(weight_t * sign_t * abs(fric_adj_t)).
    Then map [-1, +1] → [0, 100] with 50 = neutral.
    """
    if instrument_id is None or instrument_id not in conviction_rows:
        return Decimal("50.0"), "no_conviction_row"
    tenure_weights = {"1m": 0.10, "3m": 0.25, "6m": 0.35, "12m": 0.30}
    score_signed = 0.0
    fired_any = False
    for r in conviction_rows.get(instrument_id, []):
        tenure = str(r.get("tenure"))
        verdict = str(r.get("verdict"))
        weight = tenure_weights.get(tenure, 0.0)
        sign = 1 if verdict == "POSITIVE" else -1 if verdict == "NEGATIVE" else 0
        if sign != 0:
            fired_any = True
        fric_adj_raw = r.get("friction_adjusted_excess")
        magnitude = min(abs(float(fric_adj_raw or 0.0)), 1.0)
        score_signed += weight * sign * magnitude
    # score_signed lies in [-1, +1]; map to [0, 100]
    pct = max(0.0, min(100.0, (score_signed + 1.0) * 50.0))
    reason = "ok" if fired_any else "all_neutral"
    return Decimal(f"{pct:.2f}"), reason


def score_sector_strength(
    underlying_sector: str | None,
    sector_strength_map: Mapping[str, int],
    etf_category: str,
) -> tuple[Decimal, str]:
    """Score 0-100 from the sector strength_rank (1 = strongest).

    For sector/thematic ETFs: lookup the underlying sector. For broad
    ETFs: return 50.0 (neutral — composite of all sectors). For commodity
    and international ETFs: return 50.0 (no domestic sector mapping).
    """
    if etf_category in ("commodity", "international", "debt"):
        return Decimal("50.0"), f"category_{etf_category}_no_sector_map"
    if etf_category == "broad_index":
        # For broad indices we have no per-sector breakdown without holdings —
        # use the average rank (proxy for breadth).
        if not sector_strength_map:
            return Decimal("50.0"), "no_sector_states"
        avg_rank = sum(sector_strength_map.values()) / len(sector_strength_map)
        # avg_rank is around (1+N)/2 if uniform; map: best=100 worst=0
        n = len(sector_strength_map)
        if n <= 1:
            return Decimal("50.0"), "single_sector"
        pct = (1.0 - (avg_rank - 1) / max(1, n - 1)) * 100.0
        return Decimal(f"{pct:.2f}"), "broad_avg"
    # sector / thematic / smart_beta with a linked_sector
    if underlying_sector is None or underlying_sector not in sector_strength_map:
        return Decimal("50.0"), "sector_not_ranked"
    rank = sector_strength_map[underlying_sector]
    n = len(sector_strength_map)
    if n <= 1:
        return Decimal("50.0"), "single_sector"
    pct = (1.0 - (rank - 1) / max(1, n - 1)) * 100.0
    pct = max(0.0, min(100.0, pct))
    return Decimal(f"{pct:.2f}"), "ranked"


def score_tracking_quality(
    tracking_error_252d: float | None,
    alpha_252d: float | None,
    is_passive: bool,
) -> tuple[Decimal, str]:
    """Score 0-100 from tracking error (passive) or alpha (active)."""
    if is_passive:
        if tracking_error_252d is None:
            return Decimal("50.0"), "no_tracking_error_data"
        # Lower TE = better. Cap TE at 5% (5.0 pct points => 0).
        te_pct = abs(float(tracking_error_252d))
        score = max(0.0, 100.0 - min(te_pct / 5.0, 1.0) * 100.0)
        return Decimal(f"{score:.2f}"), "passive_te"
    # Active: positive alpha = better
    if alpha_252d is None:
        return Decimal("50.0"), "no_alpha_data"
    # Map alpha in [-0.10, +0.10] → [0, 100]
    a = max(-0.10, min(0.10, float(alpha_252d)))
    score = (a + 0.10) / 0.20 * 100.0
    return Decimal(f"{score:.2f}"), "active_alpha"


def score_aum_bracket(
    aum_cr: float | None,
    sweet_min_cr: float,
    sweet_max_cr: float,
) -> tuple[Decimal, str]:
    """Score 0-100: 100 inside [sweet_min, sweet_max], degrades outside."""
    if aum_cr is None:
        return Decimal("50.0"), "no_aum_data"
    if aum_cr <= 0:
        return Decimal("0.0"), "aum_zero_or_negative"
    if sweet_min_cr <= aum_cr <= sweet_max_cr:
        return Decimal("100.0"), "in_sweet_spot"
    if aum_cr < sweet_min_cr:
        # Below sweet spot: log-decay
        ratio = aum_cr / sweet_min_cr
        score = max(0.0, min(100.0, ratio * 100.0))
        return Decimal(f"{score:.2f}"), "below_sweet_spot"
    # Above sweet spot: gentle taper (size hurts only a little)
    over = math.log10(aum_cr / sweet_max_cr)
    score = max(40.0, 100.0 - over * 30.0)
    return Decimal(f"{score:.2f}"), "above_sweet_spot"


def score_liquidity(
    log_med_tv_60d: float | None,
    category_log_tvs: Sequence[float],
) -> tuple[Decimal, str]:
    """Score 0-100 = percentile rank of log_med_tv_60d within category."""
    if log_med_tv_60d is None:
        return Decimal("50.0"), "no_liquidity_data"
    if not category_log_tvs:
        return Decimal("50.0"), "no_category_baseline"
    pct = _percentile_rank(category_log_tvs, float(log_med_tv_60d))
    return Decimal(f"{pct:.2f}"), "ranked"


def score_expense_ratio(
    ter_pct: float | None,
    category_ter_list: Sequence[float],
) -> tuple[Decimal, str]:
    """Score 0-100 = INVERSE-percentile-rank of TER (lower TER = higher score)."""
    if ter_pct is None:
        return Decimal("50.0"), "no_ter_data"
    if not category_ter_list:
        return Decimal("50.0"), "no_category_baseline"
    pct = _inverse_percentile_rank(category_ter_list, float(ter_pct))
    return Decimal(f"{pct:.2f}"), "ranked"


# ---------------------------------------------------------------------------
# Composite + ELI5
# ---------------------------------------------------------------------------


def _compute_composite(
    components: dict[str, Decimal | None],
    weights: dict[str, Decimal],
) -> Decimal:
    """Weighted sum of component scores. Missing components ignored (rescale)."""
    weight_map = {
        "matrix_conviction_score": weights["etf_weight_matrix"],
        "sector_strength_score": weights["etf_weight_sector"],
        "tracking_quality_score": weights["etf_weight_tracking"],
        "aum_bracket_score": weights["etf_weight_aum"],
        "liquidity_score": weights["etf_weight_liquidity"],
        "expense_ratio_score": weights["etf_weight_expense"],
    }
    total_weight = Decimal("0")
    weighted_sum = Decimal("0")
    for k, w in weight_map.items():
        v = components.get(k)
        if v is None:
            continue
        weighted_sum += Decimal(str(v)) * w
        total_weight += w
    if total_weight == 0:
        return Decimal("50.00")
    return (weighted_sum / total_weight).quantize(Decimal("0.01"))


def _eli5_etf(row: ETFScoreRow) -> str:
    """Render ETF ELI5 string. Atlas Leader → cat archetype; else generic.

    Delegates to :mod:`atlas.inference.eli5_fund_etf` for leader rows so
    the template library lives in one place. Non-leader rows render a
    short composite-score line locally (no template needed).
    """
    from atlas.inference.eli5_fund_etf import eli5_etf_leader

    cat = row.etf_category
    aum: float | None = None
    ter: float | None = None
    primary: str | None = None
    if row.raw_metrics:
        aum_raw = row.raw_metrics.get("aum_cr")
        ter_raw = row.raw_metrics.get("ter_pct")
        aum = float(aum_raw) if aum_raw is not None else None
        ter = float(ter_raw) if ter_raw is not None else None
        # Pick the dominant component score for primary_strength.
        primary = _pick_primary_strength(row)
    if row.is_atlas_leader:
        return eli5_etf_leader(
            category=cat,
            primary_strength=primary,
            aum_cr=aum,
            ter_pct=ter,
            underlying_sector=row.underlying_sector,
        )
    # Non-leader — keep concise; no template needed.
    aum_blurb = f" ₹{aum:,.0f}Cr AUM" if aum is not None else ""
    if ter is not None:
        aum_blurb += f", {ter:.2f}% TER"
    return (
        f"{cat.replace('_', ' ').title()} ETF — {row.composite_score:.0f}/100 composite.{aum_blurb}"
    )


def _pick_primary_strength(row: ETFScoreRow) -> str | None:
    """Return the component name with the highest score (for ELI5 emphasis)."""
    candidates: list[tuple[str, Decimal | None]] = [
        ("matrix conviction", row.matrix_conviction_score),
        ("sector strength", row.sector_strength_score),
        ("tracking quality", row.tracking_quality_score),
        ("AUM bracket", row.aum_bracket_score),
        ("liquidity", row.liquidity_score),
        ("expense ratio", row.expense_ratio_score),
    ]
    scored = [(label, float(score)) for label, score in candidates if score is not None]
    if not scored:
        return None
    return max(scored, key=lambda t: t[1])[0]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _load_conviction_for_date(
    engine: Engine, snapshot_date: date
) -> dict[str, list[Mapping[str, Any]]]:
    """Pull atlas_conviction_daily rows for snapshot_date, keyed by instrument_id."""
    sql = text(
        """
        SELECT
            instrument_id::text AS instrument_id,
            tenure,
            verdict,
            friction_adjusted_excess
        FROM atlas.atlas_conviction_daily
        WHERE snapshot_date = :d
        """
    )
    out: dict[str, list[Mapping[str, Any]]] = {}
    with engine.connect() as conn:
        for r in conn.execute(sql, {"d": snapshot_date}).mappings():
            out.setdefault(r["instrument_id"], []).append(dict(r))
    return out


def _load_sector_strength_map(engine: Engine, snapshot_date: date) -> dict[str, int]:
    """Build a sector_strength_rank map from atlas_sector_states_daily.

    The live table exposes ``sector_name`` and ``participation_rs_pct``
    (higher = stronger). We rank by ``participation_rs_pct DESC`` to
    produce 1 = strongest. Falls back to an ordinal derived from
    ``sector_state`` ordering when participation is NULL across the row
    set.
    """
    out: dict[str, int] = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT sector_name,
                           participation_rs_pct,
                           sector_state
                    FROM atlas.atlas_sector_states_daily
                    WHERE date = (
                        SELECT MAX(date) FROM atlas.atlas_sector_states_daily
                        WHERE date <= :d
                    )
                    """
                ),
                {"d": snapshot_date},
            ).all()
        # Prefer participation_rs_pct when available; fall back to a
        # qualitative state ordering. Either way the output is a dense
        # rank in [1, N] where 1 = strongest.
        scored: list[tuple[str, float]] = []
        state_score = {
            "Leading": 100.0,
            "Improving": 75.0,
            "Neutral": 50.0,
            "Weakening": 25.0,
            "Lagging": 0.0,
        }
        for sector_name, pct, state in rows:
            if pct is not None:
                scored.append((str(sector_name), float(pct)))
            elif state is not None and str(state) in state_score:
                scored.append((str(sector_name), state_score[str(state)]))
        scored.sort(key=lambda x: x[1], reverse=True)
        for rank, (sector_name, _v) in enumerate(scored, start=1):
            out[sector_name] = rank
    except Exception as exc:
        log.info("etf_sector_strength_load_failed", error=str(exc))
    return out


def compute_etf_scorecard(
    snapshot_date: date,
    *,
    engine: Engine | None = None,
    etf_universe: Sequence[Mapping[str, Any]] | None = None,
    conviction_rows: dict[str, list[Mapping[str, Any]]] | None = None,
    sector_strength_map: Mapping[str, int] | None = None,
    thresholds: dict[str, Decimal] | None = None,
    extra_metrics: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[ETFScoreRow]:
    """Compute ETF scorecard for one snapshot.

    Either pass ``engine`` (production) OR pass the pre-loaded fixtures
    (test path). ``extra_metrics`` is an optional per-ticker dict of
    {ticker: {aum_cr, ter_pct, tracking_error_252d, alpha_252d,
              log_med_tv_60d, is_passive, instrument_id}} that lets the
    test path inject all the auxiliary numbers without hitting a live DB.
    """
    if engine is not None:
        etf_universe = _load_etf_universe(engine)
        conviction_rows = _load_conviction_for_date(engine, snapshot_date)
        sector_strength_map = _load_sector_strength_map(engine, snapshot_date)
        thresholds = _load_etf_thresholds(engine)
    if thresholds is None:
        thresholds = dict(_DEFAULT_WEIGHTS)
    if etf_universe is None:
        etf_universe = []
    if conviction_rows is None:
        conviction_rows = {}
    if sector_strength_map is None:
        sector_strength_map = {}
    if extra_metrics is None:
        extra_metrics = {}

    sweet_min = float(thresholds.get("etf_aum_sweet_spot_min_cr", Decimal("100")))
    sweet_max = float(thresholds.get("etf_aum_sweet_spot_max_cr", Decimal("50000")))
    leader_pct = float(thresholds.get("etf_atlas_leader_pct", Decimal("25")))

    # First pass — classify into categories so we can compute percentile
    # baselines within each category.
    classified: list[dict[str, Any]] = []
    for u in etf_universe:
        ticker = u.get("ticker")
        extras = extra_metrics.get(str(ticker), {}) if ticker is not None else {}
        category = _theme_to_category(u.get("theme"), u.get("asset_class"))
        classified.append({"universe": u, "extras": extras, "category": category})

    # Category-level baselines for liquidity + TER percentile scoring
    cat_liquidity: dict[str, list[float]] = {}
    cat_ter: dict[str, list[float]] = {}
    for c in classified:
        ex = c["extras"]
        cat = c["category"]
        if (lq := ex.get("log_med_tv_60d")) is not None:
            cat_liquidity.setdefault(cat, []).append(float(lq))
        if (te := ex.get("ter_pct")) is not None:
            cat_ter.setdefault(cat, []).append(float(te))

    # Second pass — score every ETF
    rows: list[ETFScoreRow] = []
    for c in classified:
        u = c["universe"]
        extras = c["extras"]
        category = c["category"]
        ticker = u.get("ticker")
        # instrument_id can come from the universe loader (production —
        # derived UUID5 from ISIN/ticker) or via the test-only extras
        # injection. Prefer the universe value when present.
        instrument_id = u.get("instrument_id") or extras.get("instrument_id")
        underlying_sector = u.get("linked_sector")

        m_score, m_reason = score_matrix_conviction(instrument_id, conviction_rows)
        s_score, s_reason = score_sector_strength(underlying_sector, sector_strength_map, category)
        is_passive = bool(extras.get("is_passive", True))
        t_score, t_reason = score_tracking_quality(
            extras.get("tracking_error_252d"), extras.get("alpha_252d"), is_passive
        )
        a_score, a_reason = score_aum_bracket(extras.get("aum_cr"), sweet_min, sweet_max)
        l_score, l_reason = score_liquidity(
            extras.get("log_med_tv_60d"), cat_liquidity.get(category, [])
        )
        e_score, e_reason = score_expense_ratio(extras.get("ter_pct"), cat_ter.get(category, []))

        components: dict[str, Decimal | None] = {
            "matrix_conviction_score": m_score,
            "sector_strength_score": s_score,
            "tracking_quality_score": t_score,
            "aum_bracket_score": a_score,
            "liquidity_score": l_score,
            "expense_ratio_score": e_score,
        }
        composite = _compute_composite(components, thresholds)

        raw_metrics = {
            "ticker": ticker,
            "category": category,
            "aum_cr": extras.get("aum_cr"),
            "ter_pct": extras.get("ter_pct"),
            "is_passive": is_passive,
            "tracking_error_252d": extras.get("tracking_error_252d"),
            "alpha_252d": extras.get("alpha_252d"),
            "log_med_tv_60d": extras.get("log_med_tv_60d"),
            "reasons": {
                "matrix": m_reason,
                "sector": s_reason,
                "tracking": t_reason,
                "aum": a_reason,
                "liquidity": l_reason,
                "expense": e_reason,
            },
        }

        rows.append(
            ETFScoreRow(
                snapshot_date=snapshot_date,
                instrument_id=str(instrument_id) if instrument_id else "",
                isin=u.get("isin"),
                ticker=ticker,
                etf_name=u.get("etf_name"),
                etf_category=category,
                underlying_sector=underlying_sector,
                matrix_conviction_score=m_score,
                sector_strength_score=s_score,
                tracking_quality_score=t_score,
                aum_bracket_score=a_score,
                liquidity_score=l_score,
                expense_ratio_score=e_score,
                composite_score=composite,
                rank_in_category=None,
                category_size=None,
                is_atlas_leader=False,
                eli5=None,
                raw_metrics=raw_metrics,
            )
        )

    # Per-category ranking + Atlas Leader flag
    by_cat: dict[str, list[int]] = {}
    for idx, r in enumerate(rows):
        by_cat.setdefault(r.etf_category, []).append(idx)
    final_rows: list[ETFScoreRow] = []
    for _cat, idxs in by_cat.items():
        sorted_idxs = sorted(idxs, key=lambda i: float(rows[i].composite_score), reverse=True)
        n = len(sorted_idxs)
        leader_cutoff = max(1, round(n * leader_pct / 100.0))
        for rank, i in enumerate(sorted_idxs, start=1):
            is_leader = rank <= leader_cutoff
            r = rows[i]
            new = ETFScoreRow(
                **{
                    **asdict(r),
                    "rank_in_category": rank,
                    "category_size": n,
                    "is_atlas_leader": is_leader,
                    "eli5": None,
                }
            )
            new = ETFScoreRow(**{**asdict(new), "eli5": _eli5_etf(new)})
            final_rows.append(new)
    return final_rows


# ---------------------------------------------------------------------------
# SQL emission
# ---------------------------------------------------------------------------


def _sql_quote(s: str | None) -> str:
    if s is None:
        return "NULL"
    return "'" + str(s).replace("'", "''") + "'"


def _sql_decimal(d: Decimal | None) -> str:
    if d is None:
        return "NULL"
    return f"{float(d):.4f}"


def emit_upsert_sql(rows: list[ETFScoreRow]) -> str:
    """Build a multi-row INSERT...ON CONFLICT statement."""
    if not rows:
        return "-- (no rows)\n"
    values_lines: list[str] = []
    for r in rows:
        if not r.instrument_id:
            # Skip rows without an instrument_id — uniqueness key requires it.
            continue
        raw_json = _sql_quote(json.dumps(r.raw_metrics, default=str)) + "::jsonb"
        values_lines.append(
            "  ("
            f"'{r.snapshot_date.isoformat()}', "
            f"'{r.instrument_id}', "
            f"{_sql_quote(r.isin)}, "
            f"{_sql_quote(r.ticker)}, "
            f"{_sql_quote(r.etf_name)}, "
            f"{_sql_quote(r.etf_category)}, "
            f"{_sql_quote(r.underlying_sector)}, "
            f"{_sql_decimal(r.matrix_conviction_score)}, "
            f"{_sql_decimal(r.sector_strength_score)}, "
            f"{_sql_decimal(r.tracking_quality_score)}, "
            f"{_sql_decimal(r.aum_bracket_score)}, "
            f"{_sql_decimal(r.liquidity_score)}, "
            f"{_sql_decimal(r.expense_ratio_score)}, "
            f"{_sql_decimal(r.composite_score)}, "
            f"{r.rank_in_category if r.rank_in_category is not None else 'NULL'}, "
            f"{r.category_size if r.category_size is not None else 'NULL'}, "
            f"{'TRUE' if r.is_atlas_leader else 'FALSE'}, "
            f"{_sql_quote(r.eli5)}, "
            f"{raw_json}"
            ")"
        )
    if not values_lines:
        return "-- (no rows with instrument_id)\n"
    return (
        "INSERT INTO atlas.atlas_etf_scorecard "
        "(snapshot_date, instrument_id, isin, ticker, etf_name, etf_category, "
        "underlying_sector, matrix_conviction_score, sector_strength_score, "
        "tracking_quality_score, aum_bracket_score, liquidity_score, "
        "expense_ratio_score, composite_score, rank_in_category, category_size, "
        "is_atlas_leader, eli5, raw_metrics) VALUES\n"
        + ",\n".join(values_lines)
        + "\nON CONFLICT (snapshot_date, instrument_id) DO UPDATE SET\n"
        "  etf_category = EXCLUDED.etf_category,\n"
        "  underlying_sector = EXCLUDED.underlying_sector,\n"
        "  matrix_conviction_score = EXCLUDED.matrix_conviction_score,\n"
        "  sector_strength_score = EXCLUDED.sector_strength_score,\n"
        "  tracking_quality_score = EXCLUDED.tracking_quality_score,\n"
        "  aum_bracket_score = EXCLUDED.aum_bracket_score,\n"
        "  liquidity_score = EXCLUDED.liquidity_score,\n"
        "  expense_ratio_score = EXCLUDED.expense_ratio_score,\n"
        "  composite_score = EXCLUDED.composite_score,\n"
        "  rank_in_category = EXCLUDED.rank_in_category,\n"
        "  category_size = EXCLUDED.category_size,\n"
        "  is_atlas_leader = EXCLUDED.is_atlas_leader,\n"
        "  eli5 = EXCLUDED.eli5,\n"
        "  raw_metrics = EXCLUDED.raw_metrics;\n"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _has_write_marker(repo_root: Path) -> bool:
    return (repo_root / ".supabase-write-approved").exists()


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", required=True, help="Snapshot date (YYYY-MM-DD)")
    p.add_argument(
        "--backfill",
        action="store_true",
        help="Marker flag (pure documentation)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Where to write the SQL file when live writes are blocked",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repo root (used to look for .supabase-write-approved marker)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    snapshot_date = date.fromisoformat(args.date)

    from atlas.db import get_engine

    engine = get_engine()
    rows = compute_etf_scorecard(snapshot_date, engine=engine)
    log.info("etf_scorecard_computed", date=str(snapshot_date), n_rows=len(rows))

    if _has_write_marker(args.repo_root):
        log.info("etf_scorecard_live_write", n_rows=len(rows))
        sql = emit_upsert_sql(rows)
        with engine.begin() as conn:
            if sql.strip().startswith("--"):
                print("Nothing to write.")
                return 0
            conn.execute(text(sql))
        print(f"Wrote {len(rows)} rows to atlas_etf_scorecard")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"etf_scorecard_{snapshot_date.isoformat()}.sql"
    out_path.write_text(emit_upsert_sql(rows))
    print(f"Wrote {len(rows)} rows to {out_path}")
    print("Live DB write skipped — .supabase-write-approved marker not present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
