"""Rank-IC and decile spread for one signal against forward returns.

Pure: no I/O, no DB. Loaders live in scripts/foundation/eval_signal.py.

WHY SPEARMAN, NOT PEARSON: lens scores are ordinal 0-100. The claim being tested is
"a higher score precedes a higher return", which is about ordering, not linearity.

WHY WITHIN (date, cohort): deciles cut across dates measure market direction, and cut
across cap cohorts measure the size effect. Neither is the lens. Cutting within both
isolates it.

WHY AVERAGE RANKS: `policy` is a sector-level score broadcast to its constituents — on
2026-08-21, 87 Financial Services names share one value. `method="first"` would invent an
ordering inside that tie block that the data does not contain, making the IC depend on the
order rows came back from the query. `method="average"` (the pandas default) is the tie
convention Spearman is defined with.
"""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd

MIN_CROSS_SECTION = 20  # below this, a rank correlation is noise


def evaluate(
    df: pd.DataFrame,
    horizon: int,
    deciles: int = 10,
    min_n: int = MIN_CROSS_SECTION,
) -> pd.DataFrame:
    """One row per (date, cohort): rank_ic, n, decile_spread.

    Args:
        df: columns instrument_id, date, score, cap, and fwd_<horizon>.
            Rows whose score or forward return is NULL are DROPPED — a missing value is
            absence of evidence, never a zero.
        horizon: trading sessions ahead; selects the fwd_<horizon> column.
        deciles: buckets per cohort. 10 in production; tests use 4 on small frames.
        min_n: skip a (date, cohort) thinner than this.

    Returns:
        Frame of date, cohort, n, rank_ic, decile_spread. A cohort whose score has no
        variance (one tie block) keeps its row with rank_ic and decile_spread NULL —
        there is no ordering to correlate, and that is not a reading of zero.
    """
    col = f"fwd_{horizon}"
    if col not in df.columns:
        raise KeyError(f"{col} not in frame; got {sorted(df.columns)}")

    work = df.dropna(subset=["score", col])
    if work.empty:
        return _empty()

    out: list[dict[str, object]] = []
    for key, g in work.groupby(["date", "cap"], sort=True):
        date, cohort = cast("tuple[object, object]", key)
        n = len(g)
        if n < min_n:
            continue
        score, fwd = pd.Series(g["score"]), pd.Series(g[col])
        # errstate: a cohort that is one tie block divides by a zero SD and yields NaN.
        # That is the handled case below, not an anomaly — policy hits it on every date.
        with np.errstate(invalid="ignore"):
            ic = float(score.rank().corr(fwd.rank()))  # Spearman == Pearson on ranks
        k = max(1, n // deciles)
        # ponytail: at a tie straddling the decile boundary nlargest keeps whichever rows
        # came first, which is arbitrary but uncorrelated with the return. Cut on the
        # average rank instead (variable k) if a tie-heavy lens ever sits near the bar.
        top = pd.Series(g.nlargest(k, "score")[col]).mean()
        bot = pd.Series(g.nsmallest(k, "score")[col]).mean()
        spread = float(top) - float(bot)
        scored = np.isfinite(ic)  # False iff the score is constant across the cohort
        out.append(
            {
                "date": date,
                "cohort": cohort,
                "n": n,
                "rank_ic": ic if scored else np.nan,
                "decile_spread": spread if scored else np.nan,
            }
        )
    return pd.DataFrame(out) if out else _empty()


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=pd.Index(["date", "cohort", "n", "rank_ic", "decile_spread"]))


def summarise(per_date: pd.DataFrame) -> dict[str, float | int | None]:
    """Collapse a per-date frame into the numbers a human reads.

    t-stat is the plain mean/stderr form. Overlapping horizons autocorrelate, so it reads
    optimistic; that is acceptable for a ranking gate and is stated on the page rather
    than silently corrected. Upgrade to Newey-West only if a lens sits near the bar.
    """
    ic = pd.Series(per_date["rank_ic"]).dropna()
    if ic.empty:
        return {
            "n_dates": 0,
            "mean_ic": None,
            "hit_rate": None,
            "t_stat": None,
            "mean_spread": None,
        }
    n = len(ic)
    sd = float(ic.std())
    spread = pd.Series(per_date["decile_spread"]).dropna()
    return {
        "n_dates": n,
        "mean_ic": float(ic.mean()),
        "hit_rate": float((ic > 0).mean()),
        "t_stat": float(ic.mean() / (sd / np.sqrt(n))) if sd > 0 and n > 1 else None,
        "mean_spread": float(spread.mean()) if not spread.empty else None,
    }
