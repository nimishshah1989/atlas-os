#!/usr/bin/env python3
"""Loop C Step 6/7 — IC calibration: learn the per-lens weights the composite consumes.

Walk-forward (purge+embargo) IC of each lens vs TRUE forward returns over the
rebuilt PIT journal → IC-proportional, regularized, floor-gated, sign-stable weights
→ persisted so the composite ACTUALLY uses them (D8/D15). Per-lens IC is independent
of the composite weights (it correlates a lens score with forward returns), so it is
valid on a journal whose composite was written with the default weights; after we
write the learned weights we recompute ONLY the composite/conviction/coverage columns
from the stored (unchanged) lens scores.

  python calibrate_loopC.py                 # DRY RUN — compute + print, write nothing
  python calibrate_loopC.py --commit        # persist weights + recompute composites
                                            # (FM-approved methodology write)

Writes on --commit:
  • atlas_signal_ic        — per-lens × horizon IC rows (supersedes stale NaN rows)
  • atlas_signal_weights   — active lens weight rows (old ones expired)
  • atlas_thresholds       — lens_weight_* (consumed by compute_composite) +
                             fundamental_reporting_lag_days / annual_reporting_lag_days
  • atlas_lens_scores_daily — composite/conviction_tier/coverage_factor/lenses_active
                             recomputed with the new weights (lens sub-scores untouched)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import _db  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402

from atlas.db import get_engine, load_thresholds  # noqa: E402
from atlas.lenses.calibration import (  # noqa: E402
    _load_close_panel,
    _load_lens_scores,
    calibrate_lens_ic,
    walk_forward_folds,
)
from atlas.lenses.compute.composite import compute_composite  # noqa: E402
from atlas.lenses.compute.thresholds_view import nest_thresholds  # noqa: E402

# Conviction lenses that enter the composite's weighted average. POLICY is excluded
# (FM decision, Loop C — static/selection-biased, kept as FYI overlay only); valuation
# is a multiplier, not averaged. So calibration learns weights over these four.
AVG_LENSES = ["technical", "fundamental", "catalyst", "flow"]
HORIZONS = [21, 63, 126]
FLOOR = 0.03
SIGN_STABILITY = 0.60  # fraction of folds the IC must keep its mean sign


def aggregate_oos_ic(eng, scores, panel) -> dict[str, list[float]]:
    """OOS test ICs per lens across all folds × horizons (walk-forward, purged),
    from preloaded panels (loaded once; reloading per horizon timed the run out)."""
    agg: dict[str, list[float]] = {}
    for h in HORIZONS:
        print(f"  walk-forward folds @ h={h}…", flush=True)
        folds = walk_forward_folds(
            eng, forward_days=h, n_folds=5, embargo=h, scores=scores, close_panel=panel
        )
        for fo in folds:
            for lens, ic in fo["test_ic"].items():
                if ic is not None and not (isinstance(ic, float) and np.isnan(ic)):
                    agg.setdefault(lens, []).append(float(ic))
    return agg


REG_LAMBDA = 0.5  # shrink IC-proportional toward equal-weight (regularization)
MAX_WEIGHT = 0.40  # concentration cap so no single conviction lens dominates


def compute_weights(agg: dict[str, list[float]]):
    """Regularized, capped IC-tilt weights over the four conviction lenses.

    On clean PIT data single-lens OOS ICs are modest (0.01–0.03) and close, so a
    hard drop-below-floor rule is too brittle. Instead we keep every conviction lens
    that is POSITIVELY predictive and sign-stable across folds, weight it by
    IC × sign-stability, shrink toward equal-weight (REG_LAMBDA), and cap at
    MAX_WEIGHT — a gentle, defensible tilt toward the more predictive lenses. Falls
    back to equal-weight if nothing is positively predictive (never degenerate).
    `kept` flags lenses that individually clear the 0.03 floor (reporting only)."""
    stats = {}
    for lens in AVG_LENSES:
        ics = np.array(agg.get(lens, []), dtype=float)
        if ics.size == 0:
            stats[lens] = {"mean_ic": float("nan"), "sign_stab": 0.0, "n": 0, "kept": False}
            continue
        m = float(ics.mean())
        sign_stab = float((np.sign(ics) == np.sign(m)).mean())
        stats[lens] = {
            "mean_ic": m,
            "sign_stab": sign_stab,
            "n": int(ics.size),
            "kept": abs(m) >= FLOOR and sign_stab >= SIGN_STABILITY,
        }
    cand = {
        l: stats[l]["mean_ic"] * stats[l]["sign_stab"]
        for l in AVG_LENSES
        if stats[l]["mean_ic"] > 0 and stats[l]["sign_stab"] >= SIGN_STABILITY
    }
    if not cand:
        return {l: 1.0 / len(AVG_LENSES) for l in AVG_LENSES}, stats
    tot = sum(cand.values())
    eq = 1.0 / len(cand)
    w = {l: REG_LAMBDA * (cand[l] / tot) + (1 - REG_LAMBDA) * eq for l in cand}
    for _ in range(10):  # concentration cap with proportional redistribution
        over = {l: v for l, v in w.items() if v > MAX_WEIGHT}
        if not over:
            break
        excess = sum(v - MAX_WEIGHT for v in over.values())
        under = {l: v for l, v in w.items() if v < MAX_WEIGHT}
        usum = sum(under.values()) or 1.0
        for l in over:
            w[l] = MAX_WEIGHT
        for l in under:
            w[l] += excess * w[l] / usum
    s = sum(w.values())
    weights = {l: 0.0 for l in AVG_LENSES}
    weights.update({l: w[l] / s for l in cand})
    return weights, stats


def add_composite_factors(scores, weights):
    """Add normalized weighted-average composite factors (learned vs equal weights)
    over the averaged lenses — the inputs whose OOS IC we compare to prove the
    learned weighting adds value (spec IC step 5)."""
    s = scores.copy()
    M = s[AVG_LENSES].astype(float)
    present = M.notna()
    wl = pd.Series({l: float(weights.get(l, 0.0)) for l in AVG_LENSES})
    we = pd.Series({l: 1.0 for l in AVG_LENSES})
    s["composite_learned"] = M.fillna(0).mul(wl, axis=1).sum(axis=1) / present.mul(wl, axis=1).sum(
        axis=1
    ).replace(0, np.nan)
    s["composite_eq"] = M.fillna(0).mul(we, axis=1).sum(axis=1) / present.mul(we, axis=1).sum(
        axis=1
    ).replace(0, np.nan)
    return s


def composite_uplift(eng, weights, scores, panel) -> tuple[float, float]:
    """Mean OOS IC of the learned-weighted composite vs the equal-weighted composite,
    across horizons × folds. Returns (learned_ic, equal_ic)."""
    s2 = add_composite_factors(scores, weights)
    learned, equal = [], []
    for h in HORIZONS:
        for fo in walk_forward_folds(
            eng,
            forward_days=h,
            n_folds=5,
            embargo=h,
            scores=s2,
            close_panel=panel,
            lenses=("composite_learned", "composite_eq"),
        ):
            li, ei = fo["test_ic"].get("composite_learned"), fo["test_ic"].get("composite_eq")
            if li is not None and not np.isnan(li):
                learned.append(li)
            if ei is not None and not np.isnan(ei):
                equal.append(ei)
    return (
        float(np.mean(learned)) if learned else float("nan"),
        float(np.mean(equal)) if equal else float("nan"),
    )


def recompute_composites(eng, th_nested, commit: bool) -> int:
    """Recompute composite/conviction/coverage for the whole stock journal from the
    STORED lens sub-scores using the new weights. Lens scores are not touched."""
    df = _db.read_df(
        "SELECT instrument_id, date, technical, fundamental, valuation, catalyst, flow, policy, "
        "valuation_multiplier, smart_money_score, degradation_score "
        "FROM atlas.atlas_lens_scores_daily WHERE asset_class='stock'"
    )
    n = len(df)
    print(f"  recompute: {n} journal rows", flush=True)
    if not commit:
        return n

    def f(v):
        return float(v) if v is not None and pd.notna(v) else None

    df["date"] = pd.to_datetime(df["date"]).dt.date
    dates = sorted(df["date"].unique())
    # Batch by date-chunk and commit per batch — a single 3.9M-row UPDATE exceeds the
    # 600s statement timeout, so we apply ~BATCH dates (~tens of thousands of rows) at
    # a time. Deterministic + idempotent, so a re-run safely resumes.
    BATCH = 60
    from psycopg2.extras import execute_values

    done = 0
    for i in range(0, len(dates), BATCH):
        chunk = set(dates[i : i + BATCH])
        sub = df[df["date"].isin(chunk)]
        updates = []
        for r in sub.itertuples(index=False):
            res = compute_composite(
                technical=f(r.technical),
                fundamental=f(r.fundamental),
                valuation_score=f(r.valuation),
                catalyst=f(r.catalyst),
                flow=f(r.flow),
                policy=f(r.policy),
                valuation_multiplier=f(r.valuation_multiplier) or 1.0,
                smart_money_score=f(r.smart_money_score) or 0.0,
                degradation_score=f(r.degradation_score) or 0.0,
                thresholds=th_nested,
            )
            updates.append(
                (
                    float(res.final_score),
                    res.conviction_tier,
                    float(res.coverage_factor),
                    int(res.lenses_active),
                    r.instrument_id,
                    r.date,
                )
            )
        raw = get_engine().raw_connection()
        try:
            with raw.cursor() as cur:
                cur.execute(
                    "CREATE TEMP TABLE _cmp(composite numeric, conviction_tier text, "
                    "coverage_factor numeric, lenses_active int, instrument_id uuid, date date) "
                    "ON COMMIT DROP"
                )
                execute_values(cur, "INSERT INTO _cmp VALUES %s", updates, page_size=5000)
                cur.execute(
                    "UPDATE atlas.atlas_lens_scores_daily l SET composite=c.composite, "
                    "conviction_tier=c.conviction_tier, coverage_factor=c.coverage_factor, "
                    "lenses_active=c.lenses_active FROM _cmp c "
                    "WHERE l.instrument_id=c.instrument_id AND l.date=c.date AND l.asset_class='stock'"
                )
            raw.commit()
        finally:
            raw.close()
        done += len(updates)
        print(
            f"    recomputed {done}/{n} rows ({i // BATCH + 1}/{(len(dates) + BATCH - 1) // BATCH} batches)",
            flush=True,
        )
    return n


# atlas_signal_weights is tier-scoped (chk_weights_tier). Lens weights are
# universe-wide, so we replicate the same weight across all five tiers.
_TIERS = (
    "tier_1_megacap",
    "tier_2_largecap",
    "tier_3_uppermid",
    "tier_4_lowermid",
    "tier_5_smallcap",
)


def persist_weights(eng, weights, stats, as_of: date) -> None:
    """Expire prior active lens weights, insert the new set (per tier), update thresholds."""
    with eng.begin() as conn:
        conn.execute(
            text(
                "UPDATE atlas.atlas_signal_weights SET effective_to=:d "
                "WHERE signal_name LIKE 'lens_%' AND effective_to IS NULL"
            ),
            {"d": as_of},
        )
        for lens, w in weights.items():
            note = (
                f"IC walk-forward (purge+embargo) as_of={as_of}; "
                f"mean_oos_ic={stats[lens]['mean_ic']:.4f}, sign_stab={stats[lens]['sign_stab']:.2f}, "
                f"n_folds={stats[lens]['n']}, kept={stats[lens]['kept']}"
            )
            hic = None if np.isnan(stats[lens]["mean_ic"]) else round(stats[lens]["mean_ic"], 6)
            for tier in _TIERS:
                conn.execute(
                    text(
                        "INSERT INTO atlas.atlas_signal_weights "
                        "(tier, regime, signal_name, weight, flipped, effective_from, effective_to, "
                        " train_ic, holdout_ic, approved_by, approved_at, notes) VALUES "
                        "(:t,:r,:s,:w,false,:ef,NULL,:tic,:hic,:by,now(),:n)"
                    ),
                    {
                        "t": tier,
                        "r": "all",
                        "s": f"lens_{lens}",
                        "w": round(w, 6),
                        "ef": as_of,
                        "tic": None,
                        "hic": hic,
                        "by": "loopC-calibration",
                        "n": note,
                    },
                )
        # weights the composite reads (the four conviction lenses)
        _set = (
            "UPDATE atlas.atlas_thresholds SET threshold_value=:v, "
            "last_modified_at=now(), last_modified_by='loopC-calibration' WHERE threshold_key=:k"
        )
        for lens, w in weights.items():
            conn.execute(text(_set), {"v": round(w, 6), "k": f"lens_weight_{lens}"})
        # policy is FYI-only now — zero its composite weight for clarity (unused by
        # compute_composite, which excludes policy from _LENS_NAMES).
        conn.execute(text(_set), {"v": 0, "k": "lens_weight_policy"})
        # reporting-lag thresholds (so the gate + adapters read the DB, not code defaults)
        lag_desc = {
            "fundamental_reporting_lag_days": "Days after a quarter's period_end before its income "
            "statement is treated as knowable (PIT as-of proxy).",
            "annual_reporting_lag_days": "Days after a fiscal year's period_end before the annual "
            "balance sheet is treated as knowable (PIT as-of proxy).",
        }
        for k, v in (("fundamental_reporting_lag_days", 60), ("annual_reporting_lag_days", 90)):
            exists = conn.execute(
                text("SELECT 1 FROM atlas.atlas_thresholds WHERE threshold_key=:k"), {"k": k}
            ).scalar()
            if exists:
                conn.execute(text(_set), {"v": v, "k": k})
            else:
                conn.execute(
                    text(
                        "INSERT INTO atlas.atlas_thresholds(threshold_key, threshold_value, category, "
                        "description, min_allowed, max_allowed, default_value, units, methodology_section, "
                        "last_modified_by, is_active) VALUES "
                        "(:k,:v,'fundamental',:d,0,365,:v,'days','fundamental','loopC-calibration',true)"
                    ),
                    {"k": k, "v": v, "d": lag_desc[k]},
                )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="persist weights + recompute composites")
    ap.add_argument(
        "--recompute-only",
        action="store_true",
        help="just recompute journal composites from already-persisted DB weights",
    )
    ap.add_argument("--as-of", type=date.fromisoformat, default=None)
    args = ap.parse_args()
    eng = get_engine()

    if args.recompute_only:
        th = nest_thresholds(
            {
                k: (float(v) if isinstance(v, Decimal) else v)
                for k, v in load_thresholds(engine=eng).items()
            }
        )
        print(
            "== recompute-only: applying persisted DB weights to journal composites ==", flush=True
        )
        recompute_composites(eng, th, commit=True)
        print("  ✅ recompute done.")
        return
    as_of = args.as_of or _db.scalar(
        "SELECT max(date) FROM atlas.atlas_lens_scores_daily WHERE asset_class='stock'"
    )
    if hasattr(as_of, "date"):
        as_of = as_of.date()

    print(f"== Loop C IC calibration (as_of={as_of}, commit={args.commit}) ==")
    print("  loading lens-score + close panels once…", flush=True)
    scores = _load_lens_scores(eng)
    panel = _load_close_panel(eng)
    agg = aggregate_oos_ic(eng, scores, panel)
    weights, stats = compute_weights(agg)

    print("\n  lens          mean_oos_ic  sign_stab  n_folds  kept   weight")
    for lens in AVG_LENSES:
        s = stats[lens]
        print(
            f"  {lens:12s}  {s['mean_ic']:+.4f}      {s['sign_stab']:.2f}      "
            f"{s['n']:>3d}     {s['kept']!s:5s}  {weights[lens]:.4f}"
        )
    print(f"  weight sum = {sum(weights.values()):.4f}")

    if not weights or abs(sum(weights.values()) - 1.0) > 1e-6:
        print("\n  ❌ degenerate weights — refusing to persist")
        sys.exit(1)

    if not args.commit:
        # Dry run: also measure the composite uplift (the spec's value test) and
        # preview the journal impact — write nothing.
        print("\n  measuring composite uplift (learned vs equal weights)…", flush=True)
        learned_ic, equal_ic = composite_uplift(eng, weights, scores, panel)
        print(
            f"  composite OOS IC: learned={learned_ic:+.4f}  equal={equal_ic:+.4f}  "
            f"uplift={learned_ic - equal_ic:+.4f}"
        )
        recompute_composites(eng, None, commit=False)
        print("\n  DRY RUN — nothing written. Re-run with --commit to persist.")
        return

    # Commit. IC rows + uplift were validated in the dry run; skip those sweeps and
    # only (re)persist if the IC rows aren't already present, then write weights and
    # recompute the journal composites with the learned weights.
    existing_ic = _db.scalar(
        "SELECT count(*) FROM atlas.atlas_signal_ic WHERE signal_name LIKE 'lens_%' "
        "AND mean_ic IS NOT NULL AND as_of_date >= CURRENT_DATE - 7"
    )
    if not existing_ic or existing_ic < 5:
        print("\n  persisting IC rows (atlas_signal_ic)…")
        calibrate_lens_ic(eng, as_of_date=as_of, forward_periods=HORIZONS)
    else:
        print(f"\n  IC rows already persisted ({existing_ic}) — skipping IC sweep.")
    print("  persisting weights (atlas_signal_weights + atlas_thresholds)…")
    persist_weights(eng, weights, stats, as_of)
    # Composite is ON-READ (D19) — NOT materialised. We persist the learned weights + IC
    # only; the composite/conviction/coverage reflect them at query time, so there is no
    # 3.9M-row rewrite (that repeatedly hung + bloated Supabase — the abandoned design).
    print("  ✅ committed (weights + IC persisted; composite is on-read, not materialised).")


if __name__ == "__main__":
    main()
