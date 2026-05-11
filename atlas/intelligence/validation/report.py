"""Markdown tearsheet generator for signal validation runs.

One section per forward period. Each section reports mean IC, IC t-stat,
quantile spread, turnover, and PASS/FAIL against SP01 success criteria.
"""

from __future__ import annotations

from datetime import date

from atlas.intelligence.validation.ic_engine import ICResult

# SP01 success criteria — see docs/phase2/00-master-plan.html
_CRITERIA = {
    "mean_ic_min": 0.05,
    "ic_t_stat_min": 2.0,
    "quantile_spread_ann_min": 0.08,
    "turnover_monthly_max": 0.30,
}


def build_tearsheet_markdown(
    *,
    signal_name: str,
    rolling_window: str,
    as_of: date,
    results_by_period: dict[int, tuple[ICResult, float, float]],
) -> str:
    """Render a markdown tearsheet.

    results_by_period: {period_days: (ICResult, quantile_spread_ann, turnover_monthly)}

    PASS verdict requires ALL four criteria: mean_ic >= 0.05, ic_t_stat >= 2.0,
    quantile_spread_ann >= 8%, turnover_monthly <= 30%.
    """
    lines: list[str] = []
    lines.append(f"# Signal Validation — {signal_name}")
    lines.append("")
    lines.append(f"**As of:** {as_of.isoformat()}")
    lines.append(f"**Rolling window:** {rolling_window}")
    lines.append("")
    lines.append("## Summary by forward period")
    lines.append("")
    header = "| Period | Mean IC | IC t-stat | Q-spread (ann) | Turnover/mo | N obs | Verdict |"
    lines.append(header)
    lines.append("|---|---|---|---|---|---|---|")

    for period_days in sorted(results_by_period.keys()):
        ic_result, spread, turnover = results_by_period[period_days]
        verdict = _verdict(ic_result, spread, turnover)
        lines.append(
            f"| {period_days}d | {_fmt(ic_result.mean_ic)} | {_fmt(ic_result.ic_t_stat)} | "
            f"{_fmt(spread)} | {_fmt(turnover)} | {ic_result.n_observations} | {verdict} |"
        )

    lines.append("")
    lines.append("## SP01 success criteria")
    lines.append("")
    lines.append(f"- mean IC ≥ {_CRITERIA['mean_ic_min']:.2f}")
    lines.append(f"- IC t-stat ≥ {_CRITERIA['ic_t_stat_min']:.1f}")
    spread_pct = f"{_CRITERIA['quantile_spread_ann_min']:.2%}"
    lines.append(f"- Quantile spread (Q_top − Q_bot) annualized ≥ {spread_pct}")
    lines.append(f"- Turnover monthly ≤ {_CRITERIA['turnover_monthly_max']:.0%}")
    lines.append("")
    lines.append(
        "> If criteria fail, the answer is informative, not a failure." " It drives SP04 redesign."
    )
    lines.append("")

    return "\n".join(lines)


def _verdict(ic: ICResult, spread: float, turnover: float) -> str:
    passed = (
        ic.mean_ic >= _CRITERIA["mean_ic_min"]
        and ic.ic_t_stat >= _CRITERIA["ic_t_stat_min"]
        and spread >= _CRITERIA["quantile_spread_ann_min"]
        and turnover <= _CRITERIA["turnover_monthly_max"]
    )
    return "PASS ✓" if passed else "FAIL ✗"


def _fmt(x: float) -> str:
    try:
        if x != x:  # NaN
            return "—"
        return f"{x:.4f}"
    except (TypeError, ValueError):
        return "—"
