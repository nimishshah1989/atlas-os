"""Fund composite + within-category rank + percentile band — the SINGLE source of the
fund-rank math on the Python (backfill) side.

It is a faithful port of the live frontend blend:
  frontend/src/lib/v6/sectorScore.ts  (compositeContributions / sectorComposite)
  frontend/src/lib/v6/fundScore.ts     (rankFundsInCategory)
so the daily history's "today" row equals exactly what the funds page shows. The math
lives here ONCE and is unit-tested against the documented TS outputs
(tests/scripts/test_fund_rank_core.py) — change one side, the parity test breaks.

Weights come from foundation_staging.atlas_thresholds (the /thresholds panel), never
hard-coded. composite() takes them as an argument; the builder reads them once per run.
"""

from __future__ import annotations

# lens key in the weight map  ->  vector key in a fund row
_LENS = (
    ("technical", "v_tech"),
    ("fundamental", "v_fund"),
    ("flow", "v_flow"),
    ("catalyst", "v_cat"),
)


def composite(v: dict, weights: dict) -> float | None:
    """Composite 0-100, or None when no weight>0 lens is present.

    Mirrors sectorScore.ts.compositeContributions: take the lenses actually present
    (non-null), renormalise over the ones with weight > 0, and return Σ (w/tw)·score.
    A present lens with weight 0 is context only — it does not move the score.
    """
    num = 0.0
    tw = 0.0
    for wkey, vkey in _LENS:
        score = v.get(vkey)
        w = float(weights.get(wkey, 0.0) or 0.0)
        if score is None or w <= 0:
            continue
        num += w * float(score)
        tw += w
    if tw == 0:
        return None
    return num / tw


def pct_band(rank: int | None, size: int | None) -> str | None:
    """Percentile tag within the category: Top 10% / Top 20% / Top 50% / Bottom 50%.

    Based on the fraction of the cohort AHEAD of this fund, (rank-1)/size, so the best
    fund in a category of any size is always Top 10% (and ties on the boundary fall to
    the lower band). None when the fund is unranked or the cohort is empty.
    """
    if rank is None or not size or size <= 0:
        return None
    ahead = (rank - 1) / size
    if ahead < 0.10:
        return "Top 10%"
    if ahead < 0.20:
        return "Top 20%"
    if ahead < 0.50:
        return "Top 50%"
    return "Bottom 50%"


def rank_in_category(rows: list[dict]) -> list[dict]:
    """Stamp cat_rank / cat_size / pct_band on each row, ranked WITHIN its category over
    the SCORED cohort (composite not None).

    Order: composite desc, then breadth desc (null = last), then mstar_id asc — a total
    order, so two funds that round to the same score still get distinct, explicable ranks.
    Mirrors fundScore.ts.rankFundsInCategory: unscored funds get cat_rank None but
    cat_size still reflects the scored cohort.
    """
    scored_by_cat: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("composite") is None:
            continue
        scored_by_cat.setdefault(r.get("category") or "—", []).append(r)

    rank_of: dict[str, int] = {}
    for group in scored_by_cat.values():
        group.sort(
            key=lambda r: (
                -float(r["composite"]),
                -(r["breadth"] if r.get("breadth") is not None else float("-inf")),
                r["mstar_id"],
            )
        )
        for i, r in enumerate(group):
            rank_of[r["mstar_id"]] = i + 1

    out = []
    for r in rows:
        size = len(scored_by_cat.get(r.get("category") or "—", []))
        rank = rank_of.get(r["mstar_id"])
        out.append({**r, "cat_rank": rank, "cat_size": size, "pct_band": pct_band(rank, size)})
    return out
