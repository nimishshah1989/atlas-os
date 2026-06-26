"""Generic per-cell deep-search runner for the v6 24-cell matrix.

Generalises the Phase 0.5e Large/12m/POSITIVE-only runner into a fully
parameterisable ``(tier × tenure × direction)`` engine. Feature panel
computation lives in :mod:`atlas.discovery.deep_search_features`;
candidate generation lives in :mod:`atlas.discovery.deep_search_candidates`;
this module orchestrates evaluation, gates, BH-FDR correction, and JSON
output for parallel cell-runner consumption.

Per the spec, this runner DOES NOT execute the 24-cell sweep. Eight
cell-runner subagents fan out using ``--cell <tier> <tenure> <direction>``.

Validation gate (per cell):
* sign-correct IC vs ``PER_TENURE_IC_FLOOR[tenure]`` (POSITIVE: IC > floor;
  NEGATIVE: IC < -floor),
* ≥ 2/3 walk-forward windows directionally consistent,
* ≥ 30 triggers per window,
* |pooled friction-adjusted excess| > 0.005.

BH-FDR q-values are computed across all candidates within the cell and
attached to per-candidate JSON output — informational only; the gate uses
raw IC + stability + triggers + excess (per spec §4).
"""

# allow-large: per-cell orchestration touches panels, candidates, the
# walk-forward evaluator, BH-FDR correction, and CLI/JSON I/O. Splitting
# further would fragment the audit surface — the runner is the cell's
# atomic unit.

from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd
import structlog

from atlas.decisions.rule_dsl import FeaturePredicate
from atlas.discovery._sector_panels import load_sector_mapping
from atlas.discovery.deep_search_candidates import (
    CandidateRule,
    generate_candidates,
)
from atlas.discovery.deep_search_features import (
    FeaturePanels,
    compute_feature_panels,
    panel_for_feature,
)
from atlas.discovery.engine import (
    DEFAULT_FRICTION_BY_TIER,
    DEFAULT_WINDOWS,
    PER_TENURE_IC_FLOOR,
    WalkForwardWindow,
    _compute_cap_tier_panel,
    _load_cache_files,
)

log = structlog.get_logger()

DEEP_SEARCH_METHODOLOGY_REF = "DEEP_SEARCH_V2_2026-05-24"

Tier = Literal["Large", "Mid", "Small"]
Tenure = Literal["1m", "3m", "6m", "12m"]
Direction = Literal["POSITIVE", "NEGATIVE"]

# Friction-adjusted excess gate (per spec § Phase 4 step 4).
EXCESS_MIN_ABS = 0.005

# Minimum trigger observations *per window* (not just pooled).
MIN_TRIGGERS_PER_WINDOW = 30


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateMetrics:
    """Per-candidate evaluation output. JSON-serialisable via dict cast."""

    name: str
    archetype: str
    rationale: str
    ic: float
    tp_rate: float
    median_excess: float
    mean_excess: float
    friction_adjusted_excess: float
    percentile_10: float
    percentile_25: float
    percentile_50: float
    percentile_75: float
    percentile_90: float
    n_observations: int
    per_window: tuple[dict[str, Any], ...]
    validated: bool
    bh_q_value: float
    predicates: tuple[dict[str, Any], ...]


@dataclass
class CellSummary:
    """Per-cell aggregate summary."""

    cell: tuple[str, str, str]
    candidates: tuple[CandidateMetrics, ...]
    run_started_at: datetime
    run_completed_at: datetime
    n_candidates: int
    n_gate_pass: int
    top_candidates: tuple[CandidateMetrics, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Panel loading + caching
# ---------------------------------------------------------------------------


PANEL_CACHE_FILENAME = "deep_search_v2_panels.pkl"


def _panels_cache_path(cache_dir: Path) -> Path:
    return cache_dir / PANEL_CACHE_FILENAME


def load_panels(
    cache_dir: Path | None = None,
    use_cache: bool = True,
    cache_path: Path | None = None,
) -> FeaturePanels:
    """Load OHLCV cache + sector mapping; compute or restore feature panels.

    If a pickled panels file exists at ``<cache_dir>/<PANEL_CACHE_FILENAME>``
    and ``use_cache`` is True, restore it. Otherwise compute fresh and cache.

    Args:
        cache_dir: cache root. Defaults to the engine's DEFAULT_CACHE_DIR.
            Used for the sibling files (nifty500_cache.pkl,
            iid_blacklist.json) and as the panel-cache directory.
        use_cache: whether to read/write the panels pickle. Disable in tests
            to force recompute.
        cache_path: optional explicit path to a v3-shape OHLCV cache pickle
            (overrides ``<cache_dir>/sde_ohlcv_cache.pkl``). When set, the
            sibling nifty500 + blacklist files are still read from
            ``cache_dir``. The panel-cache pickle is derived from
            ``cache_path``'s stem so v2 and v3 panel caches don't collide.
    """
    from atlas.discovery.engine import (
        BLACKLIST_FILENAME,
        DEFAULT_CACHE_DIR,
        NIFTY500_CACHE_FILENAME,
    )

    cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
    # When the caller supplies an explicit OHLCV pickle, derive the panel-cache
    # filename from its stem so v2/v3 caches live side-by-side (e.g. for the
    # comparison flow). Otherwise fall back to the default panel-cache name.
    if cache_path is not None:
        panels_pickle = cache_dir / f"{cache_path.stem}_panels.pkl"
    else:
        panels_pickle = _panels_cache_path(cache_dir)
    if use_cache and panels_pickle.exists():
        log.info("deep_search_v2_panels_cache_hit", path=str(panels_pickle))
        with panels_pickle.open("rb") as fh:
            return cast(FeaturePanels, pickle.load(fh))  # noqa: S301

    if cache_path is not None:
        # Explicit OHLCV path: read it directly; sibling nifty500 + blacklist
        # still come from cache_dir.
        if not cache_path.exists():
            raise FileNotFoundError(
                f"--cache-path file not found: {cache_path}. "
                "Run scripts/rebuild_v3_cache.py to produce it."
            )
        ohlcv = cast(pd.DataFrame, pd.read_pickle(cache_path))  # noqa: S301
        nifty500_path = cache_dir / NIFTY500_CACHE_FILENAME
        blacklist_path = cache_dir / BLACKLIST_FILENAME
        if not nifty500_path.exists() or not blacklist_path.exists():
            raise FileNotFoundError(
                f"sibling cache files missing alongside --cache-path: "
                f"{nifty500_path}, {blacklist_path}"
            )
        # pickles are dev-only cache artifacts; never user input.
        nifty500 = cast(pd.Series, pd.read_pickle(nifty500_path))  # noqa: S301
        import json as _json

        with blacklist_path.open() as fh:
            blacklist_raw = _json.load(fh)
        blacklist = [
            str(row["iid"]) if isinstance(row, dict) else str(row) for row in blacklist_raw
        ]
    else:
        ohlcv, nifty500, blacklist = _load_cache_files(cache_dir)
    if blacklist:
        ohlcv = cast(pd.DataFrame, ohlcv[~ohlcv["iid"].isin(list(blacklist))].copy())
    cap_panel = _compute_cap_tier_panel(ohlcv)
    sector_of = load_sector_mapping()
    panels = compute_feature_panels(ohlcv, nifty500, cap_panel, sector_of=sector_of)
    if use_cache:
        with panels_pickle.open("wb") as fh:
            pickle.dump(panels, fh)
        log.info("deep_search_v2_panels_cache_written", path=str(panels_pickle))
    return panels


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------


def _apply_predicate(panel: pd.DataFrame, pred: FeaturePredicate) -> pd.DataFrame:
    """Apply one predicate against its feature panel; returns boolean panel.

    All-NaN panels (e.g. sector features when mapping is absent) produce
    all-False masks — candidates that rely on them are filtered cleanly.
    """
    cmp = pred.cmp
    if cmp == "in_range":
        low, high = cast(tuple[Decimal, Decimal], pred.value)
        return (panel >= float(low)) & (panel <= float(high))
    if cmp == "in_top_quantile":
        if pred.value_quantile_n is None:
            raise ValueError("in_top_quantile requires value_quantile_n")
        ranks = panel.rank(axis=1, pct=True)
        threshold = 1.0 - (1.0 / float(pred.value_quantile_n))
        return ranks >= threshold
    scalar = float(cast(Decimal, pred.value))
    if cmp == ">":
        return panel > scalar
    if cmp == ">=":
        return panel >= scalar
    if cmp == "<":
        return panel < scalar
    if cmp == "<=":
        return panel <= scalar
    if cmp == "==":
        return panel == scalar
    raise ValueError(f"unsupported cmp={cmp!r}")


def _build_test_window_mask(
    reference: pd.DataFrame, windows: tuple[WalkForwardWindow, ...]
) -> pd.DataFrame:
    """2-D mask marking dates inside ANY test window (broadcast to columns)."""
    idx = reference.index
    if isinstance(idx, pd.DatetimeIndex):
        dates64 = idx.values.astype("datetime64[D]")
    else:
        dates64 = pd.to_datetime(idx).values.astype("datetime64[D]")
    mask_1d = np.zeros(len(idx), dtype=bool)
    for win in windows:
        win_lo = np.datetime64(win.test_start)
        win_hi = np.datetime64(win.test_end)
        mask_1d |= (dates64 >= win_lo) & (dates64 <= win_hi)
    return pd.DataFrame(
        np.broadcast_to(mask_1d[:, None], (len(idx), reference.shape[1])).copy(),
        index=idx,
        columns=reference.columns,
    )


def _pooled_spearman_ic(
    score_panel: pd.DataFrame, fwd_panel: pd.DataFrame, mask: pd.DataFrame
) -> float | None:
    """Spearman rank IC between score and forward excess, pooled over mask."""
    s_arr = np.asarray(score_panel.values, dtype=float)
    f_arr = np.asarray(fwd_panel.values, dtype=float)
    m_arr = np.asarray(mask.values, dtype=bool)
    s_vals = s_arr[m_arr]
    f_vals = f_arr[m_arr]
    valid = ~np.isnan(s_vals) & ~np.isnan(f_vals)
    s_vals = s_vals[valid]
    f_vals = f_vals[valid]
    if len(s_vals) < 30:
        return None
    s_ranks = np.asarray(pd.Series(s_vals).rank().values, dtype=float)
    f_ranks = np.asarray(pd.Series(f_vals).rank().values, dtype=float)
    if float(np.std(s_ranks)) == 0 or float(np.std(f_ranks)) == 0:
        return None
    corr = float(np.corrcoef(s_ranks, f_ranks)[0, 1])
    return None if np.isnan(corr) else corr


def _evaluate_candidate(
    candidate: CandidateRule,
    panels: FeaturePanels,
    cap_tier: str,
    tenure: str,
    direction: str,
    windows: tuple[WalkForwardWindow, ...],
) -> CandidateMetrics:
    """Walk-forward evaluate one candidate for the given cell."""
    # --- Build AND-combined entry mask ---
    try:
        masks: list[pd.DataFrame] = []
        for pred in candidate.features:
            panel = panel_for_feature(panels, pred.feature)
            masks.append(_apply_predicate(panel, pred))
    except KeyError as exc:
        # Panel not wired — should not happen post-test, but stay defensive.
        log.error("candidate_panel_missing", name=candidate.name, error=str(exc))
        return _empty_metrics(candidate, reason="panel_missing")

    if not masks:
        return _empty_metrics(candidate, reason="no_predicates")

    entry_mask = masks[0].fillna(False).astype(bool)
    for m in masks[1:]:
        entry_mask &= m.fillna(False).astype(bool)
    # Restrict to cap_tier of interest.
    cap_mask = (panels.cap_tier == cap_tier).fillna(False)
    entry_mask &= cap_mask

    test_mask = _build_test_window_mask(panels.close, windows)
    trigger_mask = entry_mask & test_mask

    fwd_panel = panels.fwd_excess_for_tenure(tenure)

    # Pooled IC: rank-correlate the LAST predicate's panel with forward
    # excess across triggers in test windows. The last predicate is the
    # candidate's most-specific filter.
    last_pred = candidate.features[-1]
    try:
        score_panel = panel_for_feature(panels, last_pred.feature)
    except KeyError:
        return _empty_metrics(candidate, reason="score_panel_missing")
    ic = _pooled_spearman_ic(score_panel, fwd_panel, trigger_mask)

    fwd_arr = np.asarray(fwd_panel.values, dtype=float)
    trig_arr = np.asarray(trigger_mask.values, dtype=bool)
    excess = fwd_arr[trig_arr]
    excess = excess[~np.isnan(excess)]
    n_obs = len(excess)

    per_window: list[dict[str, Any]] = []
    n_windows_pass = 0
    for win in windows:
        wmask = entry_mask & _build_test_window_mask(panels.close, (win,))
        warr = np.asarray(wmask.values, dtype=bool)
        wexc = fwd_arr[warr]
        wexc = wexc[~np.isnan(wexc)]
        wn = len(wexc)
        wmed = float(np.median(wexc)) if wn else float("nan")
        # Direction-correct window check.
        if direction == "POSITIVE":
            consistent = bool(wmed > 0) if wn else False
        else:
            consistent = bool(wmed < 0) if wn else False
        # Trigger floor per window.
        meets_triggers = wn >= MIN_TRIGGERS_PER_WINDOW
        per_window.append(
            {
                "window": f"{win.test_start.isoformat()}_to_{win.test_end.isoformat()}",
                "n_obs": wn,
                "median_excess": wmed,
                "consistent": consistent,
                "meets_triggers": meets_triggers,
            }
        )
        if consistent and meets_triggers:
            n_windows_pass += 1

    if n_obs == 0:
        return _empty_metrics(candidate, reason="no_observations")

    median_excess = float(np.median(excess))
    mean_excess = float(np.mean(excess))
    tp_rate = float(np.mean(excess > 0)) if direction == "POSITIVE" else float(np.mean(excess < 0))

    friction = float(DEFAULT_FRICTION_BY_TIER[cap_tier]) * 2.0  # round-trip
    if direction == "POSITIVE":
        friction_adj = median_excess - friction
    else:
        # NEGATIVE: avoid-rule — costs subtract from |median_excess|.
        friction_adj = median_excess + friction

    p10 = float(np.quantile(excess, 0.10))
    p25 = float(np.quantile(excess, 0.25))
    p50 = float(np.quantile(excess, 0.50))
    p75 = float(np.quantile(excess, 0.75))
    p90 = float(np.quantile(excess, 0.90))

    ic_floor = float(PER_TENURE_IC_FLOOR[tenure])
    if direction == "POSITIVE":
        ic_pass = ic is not None and float(ic) > ic_floor
        excess_pass = abs(friction_adj) > EXCESS_MIN_ABS and friction_adj > 0
    else:
        ic_pass = ic is not None and float(ic) < -ic_floor
        excess_pass = abs(friction_adj) > EXCESS_MIN_ABS and friction_adj < 0
    window_pass = n_windows_pass >= 2

    validated = bool(ic_pass and window_pass and excess_pass)

    return CandidateMetrics(
        name=candidate.name,
        archetype=candidate.archetype,
        rationale=candidate.rationale,
        ic=float(ic) if ic is not None else float("nan"),
        tp_rate=tp_rate,
        median_excess=median_excess,
        mean_excess=mean_excess,
        friction_adjusted_excess=friction_adj,
        percentile_10=p10,
        percentile_25=p25,
        percentile_50=p50,
        percentile_75=p75,
        percentile_90=p90,
        n_observations=n_obs,
        per_window=tuple(per_window),
        validated=validated,
        bh_q_value=float("nan"),  # filled in post-hoc by BH correction
        predicates=tuple(_predicate_to_dict(p) for p in candidate.features),
    )


def _empty_metrics(candidate: CandidateRule, *, reason: str) -> CandidateMetrics:
    """Sentinel zero-metrics row (kept in output so JSON is complete)."""
    return CandidateMetrics(
        name=candidate.name,
        archetype=candidate.archetype,
        rationale=f"{candidate.rationale} [skipped: {reason}]",
        ic=float("nan"),
        tp_rate=float("nan"),
        median_excess=float("nan"),
        mean_excess=float("nan"),
        friction_adjusted_excess=float("nan"),
        percentile_10=float("nan"),
        percentile_25=float("nan"),
        percentile_50=float("nan"),
        percentile_75=float("nan"),
        percentile_90=float("nan"),
        n_observations=0,
        per_window=(),
        validated=False,
        bh_q_value=float("nan"),
        predicates=tuple(_predicate_to_dict(p) for p in candidate.features),
    )


def _predicate_to_dict(pred: FeaturePredicate) -> dict[str, Any]:
    """JSON-safe representation of a FeaturePredicate."""
    out: dict[str, Any] = {"feature": pred.feature, "cmp": pred.cmp}
    if isinstance(pred.value, tuple):
        out["value"] = [str(v) for v in pred.value]
    else:
        out["value"] = str(pred.value)
    if pred.value_quantile_n is not None:
        out["value_quantile_n"] = int(pred.value_quantile_n)
    return out


# ---------------------------------------------------------------------------
# BH-FDR correction
# ---------------------------------------------------------------------------


def _ic_to_p_value(ic: float, n: int) -> float:
    """Approximate two-sided p-value for Spearman IC via Fisher z-transform.

    Standard Fisher-z: z = atanh(r) * sqrt(n - 3); under H0 z ~ N(0,1).
    """
    if n < 4 or np.isnan(ic):
        return 1.0
    r = float(ic)
    r = max(-0.9999, min(0.9999, r))
    z = np.arctanh(r) * np.sqrt(max(n - 3, 1))
    # Two-sided.
    from math import erf, sqrt

    p = 2.0 * (1.0 - 0.5 * (1.0 + erf(abs(z) / sqrt(2.0))))
    return float(max(min(p, 1.0), 0.0))


def _bh_q_values(metrics: list[CandidateMetrics]) -> list[float]:
    """Benjamini-Hochberg q-values for the metrics list (positional ordering).

    Returns list aligned with input order. NaN ICs receive q=1.0.
    """
    p_values: list[float] = []
    for m in metrics:
        p = _ic_to_p_value(m.ic, m.n_observations)
        p_values.append(p)
    p_arr = np.asarray(p_values, dtype=float)
    n = len(p_arr)
    # Sort indices by p ascending.
    order = np.argsort(p_arr)
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(1, n + 1, dtype=float)
    q = p_arr * (n / ranks)
    # Step-up: enforce monotonicity from the top down.
    # Build cumulative-min from largest p (last sorted index) backwards.
    sorted_q = q[order]
    for i in range(n - 2, -1, -1):
        sorted_q[i] = min(sorted_q[i], sorted_q[i + 1])
    q_out = np.empty(n, dtype=float)
    q_out[order] = np.clip(sorted_q, 0.0, 1.0)
    return q_out.tolist()


# ---------------------------------------------------------------------------
# Per-cell runner
# ---------------------------------------------------------------------------


def run_single_cell(
    tier: Tier,
    tenure: Tenure,
    direction: Direction,
    cache_dir: str | Path = "/tmp",
    output_dir: str | Path = "/tmp/deep_search_v2",
    panels: FeaturePanels | None = None,
    use_panel_cache: bool = True,
    cache_path: str | Path | None = None,
) -> CellSummary:
    """Generate, evaluate, BH-correct, persist one cell's deep-search.

    Args:
        tier: Large / Mid / Small.
        tenure: 1m / 3m / 6m / 12m.
        direction: POSITIVE or NEGATIVE.
        cache_dir: where OHLCV / Nifty / blacklist pickles live.
        output_dir: where to write ``<tier>-<tenure>-<direction>.json``.
        panels: optionally inject panels (test seam). If None, load via
            :func:`load_panels`.
        use_panel_cache: pass-through to :func:`load_panels`.
        cache_path: optional explicit OHLCV pickle path (v3 cache support).
            Passes through to :func:`load_panels`; sibling nifty500 +
            blacklist files are still read from ``cache_dir``.
    """
    started = datetime.now(UTC)
    cache_dir_p = Path(cache_dir)
    output_dir_p = Path(output_dir)
    output_dir_p.mkdir(parents=True, exist_ok=True)

    cache_path_p = Path(cache_path) if cache_path is not None else None
    if panels is None:
        panels = load_panels(
            cache_dir_p,
            use_cache=use_panel_cache,
            cache_path=cache_path_p,
        )

    candidates = generate_candidates(tier, tenure, direction)
    log.info(
        "deep_search_v2_cell_start",
        tier=tier,
        tenure=tenure,
        direction=direction,
        n_candidates=len(candidates),
    )

    metrics_list: list[CandidateMetrics] = []
    for c in candidates:
        m = _evaluate_candidate(c, panels, tier, tenure, direction, DEFAULT_WINDOWS)
        metrics_list.append(m)

    # BH-FDR correction across the cell.
    q_values = _bh_q_values(metrics_list)
    metrics_list = [
        CandidateMetrics(**{**asdict(m), "bh_q_value": q})
        for m, q in zip(metrics_list, q_values, strict=True)
    ]

    # Sort: validated first (by friction-adjusted excess descending), then
    # by absolute IC descending.
    def _sort_key(m: CandidateMetrics) -> tuple[int, float, float]:
        v = 1 if m.validated else 0
        f = m.friction_adjusted_excess if not np.isnan(m.friction_adjusted_excess) else 0.0
        i = abs(m.ic) if not np.isnan(m.ic) else 0.0
        # Negate so descending sort works with min-heap semantics.
        return (-v, -f if direction == "POSITIVE" else f, -i)

    metrics_list.sort(key=_sort_key)
    n_gate_pass = sum(1 for m in metrics_list if m.validated)

    summary = CellSummary(
        cell=(tier, tenure, direction),
        candidates=tuple(metrics_list),
        run_started_at=started,
        run_completed_at=datetime.now(UTC),
        n_candidates=len(candidates),
        n_gate_pass=n_gate_pass,
        top_candidates=tuple(metrics_list[:10]),
    )
    _write_cell_json(summary, output_dir_p)
    log.info(
        "deep_search_v2_cell_complete",
        tier=tier,
        tenure=tenure,
        direction=direction,
        n_candidates=summary.n_candidates,
        n_gate_pass=summary.n_gate_pass,
        duration_s=(summary.run_completed_at - summary.run_started_at).total_seconds(),
    )
    return summary


def _write_cell_json(summary: CellSummary, output_dir: Path) -> Path:
    """Persist the cell summary as JSON."""
    tier, tenure, direction = summary.cell
    path = output_dir / f"{tier}-{tenure}-{direction}.json"
    payload: dict[str, Any] = {
        "methodology_lock_ref": DEEP_SEARCH_METHODOLOGY_REF,
        "cell": {"tier": tier, "tenure": tenure, "direction": direction},
        "run_started_at": summary.run_started_at.isoformat(),
        "run_completed_at": summary.run_completed_at.isoformat(),
        "n_candidates": summary.n_candidates,
        "n_gate_pass": summary.n_gate_pass,
        "candidates": [asdict(c) for c in summary.candidates],
        "top_10": [asdict(c) for c in summary.top_candidates],
    }
    if summary.top_candidates:
        # Provide per-window stability for top-1 explicitly (already in
        # candidates, but make it easy for downstream consumers).
        payload["top_1_stability"] = list(summary.top_candidates[0].per_window)
    with path.open("w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_cli_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(
        prog="atlas.discovery.deep_search",
        description="Atlas v6 deep-search v2 — per-cell generic runner",
    )
    parser.add_argument(
        "--cell",
        nargs=3,
        metavar=("TIER", "TENURE", "DIRECTION"),
        required=True,
        help="Cell selector: TIER {Large,Mid,Small} TENURE {1m,3m,6m,12m} "
        "DIRECTION {POSITIVE,NEGATIVE}",
    )
    parser.add_argument(
        "--cache-dir",
        default="/tmp",  # dev-only cache root
        help="Directory containing OHLCV/Nifty cache pickles (default: /tmp)",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/deep_search_v2",  # dev-only output root
        help="Where to write <tier>-<tenure>-<direction>.json (default: /tmp/deep_search_v2)",
    )
    parser.add_argument(
        "--no-panel-cache",
        action="store_true",
        help="Force recompute of the feature panels pickle.",
    )
    parser.add_argument(
        "--cache-path",
        default=None,
        help=(
            "Optional explicit OHLCV pickle path (v3 cache support). When "
            "set, overrides <cache-dir>/sde_ohlcv_cache.pkl. The sibling "
            "nifty500_cache.pkl + iid_blacklist.json are still read from "
            "--cache-dir."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry — exit code 0 = success/no-pass, 1 = cache-missing/error."""
    args = _build_cli_parser().parse_args(argv)
    tier, tenure, direction = args.cell
    if tier not in ("Large", "Mid", "Small"):
        print(json.dumps({"error": f"invalid tier {tier!r}"}))
        return 1
    if tenure not in ("1m", "3m", "6m", "12m"):
        print(json.dumps({"error": f"invalid tenure {tenure!r}"}))
        return 1
    if direction not in ("POSITIVE", "NEGATIVE"):
        print(json.dumps({"error": f"invalid direction {direction!r}"}))
        return 1

    try:
        summary = run_single_cell(
            tier=cast(Tier, tier),
            tenure=cast(Tenure, tenure),
            direction=cast(Direction, direction),
            cache_dir=args.cache_dir,
            output_dir=args.output_dir,
            use_panel_cache=not args.no_panel_cache,
            cache_path=args.cache_path,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"error": f"cache missing: {exc}"}))
        return 1
    except (ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": f"runtime error: {exc}"}))
        return 1

    top3 = [
        {
            "name": c.name,
            "archetype": c.archetype,
            "ic": round(c.ic, 4) if not np.isnan(c.ic) else None,
            "friction_adjusted_excess": (
                round(c.friction_adjusted_excess, 4)
                if not np.isnan(c.friction_adjusted_excess)
                else None
            ),
            "bh_q_value": round(c.bh_q_value, 4) if not np.isnan(c.bh_q_value) else None,
            "validated": c.validated,
        }
        for c in summary.candidates[:3]
    ]
    print(
        json.dumps(
            {
                "cell": list(summary.cell),
                "n_candidates": summary.n_candidates,
                "n_gate_pass": summary.n_gate_pass,
                "top_3": top3,
                "output_dir": str(args.output_dir),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main(sys.argv[1:]))


# ---------------------------------------------------------------------------
# Public re-exports (test seams / external callers).
# ---------------------------------------------------------------------------

__all__ = [
    "DEEP_SEARCH_METHODOLOGY_REF",
    "EXCESS_MIN_ABS",
    "MIN_TRIGGERS_PER_WINDOW",
    "CandidateMetrics",
    "CellSummary",
    "load_panels",
    "main",
    "run_single_cell",
]
