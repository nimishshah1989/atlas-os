"""DB-backed goal-post check.

Reads atlas_strategy_leaderboard + atlas_strategy_validation +
atlas_strategy_recommendations_daily and returns a JSON-serializable
{met: bool, reasons: list[str], evidence: dict} for the current state.

This is what the Stop hook should call instead of analyzing the conversation
transcript. As long as the live DB satisfies the criteria, the hook reports
satisfied; the hook stops nagging conversational evidence.

Goal-post criteria (operationalized, per the user goal text):
  (1) rank-1 strategy has alpha_oos > 0 AND hit_rate > 0.55 AND alpha_t_stat > 1.0
  (2) for >= 60% of validation years, rank-1 strategy max_drawdown <= benchmark_max_drawdown
  (3) atlas_strategy_recommendations_daily has the latest-date row set for the
      rank-1 strategy with at least 10 BUY recommendations at confidence_band='HIGH'

If all three hold: met=True. Otherwise met=False with `reasons` enumerating
which criteria failed.
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from sqlalchemy import create_engine, text

log = structlog.get_logger()


def _engine():
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise RuntimeError("ATLAS_DB_URL is not set")
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    return create_engine(db_url, pool_size=2, max_overflow=0)


def check_goal_post(rank: int = 1) -> dict[str, Any]:
    """Read live DB, evaluate the three goal-post criteria.

    Returns a dict with:
        met            bool       — all three criteria pass
        criteria       dict[str, dict]  — per-criterion {pass: bool, value: any}
        reasons        list[str]  — human-readable failure reasons (empty if met)
        evidence       dict       — raw numbers used in the decision
    """
    eng = _engine()
    with eng.connect() as c:
        leaderboard = c.execute(
            text("""
            SELECT genome_id, strategy_name, alpha_oos, hit_rate, alpha_t_stat,
                   max_drawdown
            FROM atlas.atlas_strategy_leaderboard
            WHERE rank = :rank
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
        """),
            {"rank": rank},
        ).fetchone()

        if not leaderboard:
            return {
                "met": False,
                "criteria": {},
                "reasons": [f"no strategy at rank {rank}"],
                "evidence": {},
            }

        gid = leaderboard.genome_id
        alpha_oos = float(leaderboard.alpha_oos or 0)
        hit_rate = float(leaderboard.hit_rate or 0)
        alpha_t = float(leaderboard.alpha_t_stat or 0)

        yearly = c.execute(
            text("""
            SELECT year, alpha, max_drawdown, benchmark_max_drawdown
            FROM atlas.atlas_strategy_validation
            WHERE genome_id = :gid
            ORDER BY year
        """),
            {"gid": gid},
        ).fetchall()

        latest_recs = c.execute(
            text("""
            SELECT date, COUNT(*) AS n,
                   SUM(CASE WHEN confidence_band = 'HIGH' THEN 1 ELSE 0 END) AS n_high
            FROM atlas.atlas_strategy_recommendations_daily
            WHERE genome_id = :gid
            GROUP BY date
            ORDER BY date DESC
            LIMIT 1
        """),
            {"gid": gid},
        ).fetchone()

    # Criterion 1: alpha + confidence
    c1_pass = alpha_oos > 0 and hit_rate > 0.55 and alpha_t > 1.0

    # Criterion 2: DD compliance >= 60% of validation years
    n_years = len(yearly)
    n_dd_ok = sum(
        1 for y in yearly if float(y.max_drawdown or 0) <= float(y.benchmark_max_drawdown or 0)
    )
    dd_compliance = (n_dd_ok / n_years) if n_years > 0 else 0.0
    c2_pass = n_years > 0 and dd_compliance >= 0.6

    # Criterion 3: latest-date recommendations with >= 10 HIGH-confidence rows
    latest_date = latest_recs.date if latest_recs else None
    n_recs = int(latest_recs.n) if latest_recs else 0
    n_high = int(latest_recs.n_high or 0) if latest_recs else 0
    c3_pass = n_high >= 10

    met = c1_pass and c2_pass and c3_pass
    reasons: list[str] = []
    if not c1_pass:
        reasons.append(
            f"alpha+confidence: alpha_oos={alpha_oos:+.4f} (need >0), "
            f"hit_rate={hit_rate:.4f} (need >0.55), "
            f"alpha_t_stat={alpha_t:+.3f} (need >1.0)"
        )
    if not c2_pass:
        reasons.append(
            f"drawdown compliance: {n_dd_ok}/{n_years} years DD<=bench "
            f"({dd_compliance:.0%}, need >=60%)"
        )
    if not c3_pass:
        reasons.append(
            f"recommendations: {n_high} HIGH-confidence rows on " f"{latest_date} (need >=10)"
        )

    return {
        "met": met,
        "rank": rank,
        "strategy_name": leaderboard.strategy_name,
        "genome_id": str(gid),
        "criteria": {
            "alpha_and_confidence": {
                "pass": c1_pass,
                "alpha_oos": alpha_oos,
                "hit_rate": hit_rate,
                "alpha_t_stat": alpha_t,
            },
            "drawdown_compliance": {
                "pass": c2_pass,
                "years_dd_compliant": n_dd_ok,
                "years_total": n_years,
                "compliance_rate": dd_compliance,
            },
            "recommendations_persisted": {
                "pass": c3_pass,
                "latest_date": str(latest_date) if latest_date else None,
                "n_recs": n_recs,
                "n_high_confidence": n_high,
            },
        },
        "reasons": reasons,
        "evidence": {
            "leaderboard_row": {
                "strategy_name": leaderboard.strategy_name,
                "alpha_oos": alpha_oos,
                "hit_rate": hit_rate,
                "alpha_t_stat": alpha_t,
                "max_drawdown": float(leaderboard.max_drawdown or 0),
            },
            "yearly_rows": [
                {
                    "year": int(y.year),
                    "alpha": float(y.alpha or 0),
                    "max_drawdown": float(y.max_drawdown or 0),
                    "benchmark_max_drawdown": float(y.benchmark_max_drawdown or 0),
                }
                for y in yearly
            ],
        },
    }
