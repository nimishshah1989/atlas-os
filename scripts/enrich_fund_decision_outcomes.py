"""Fill 1m and 3m outcome columns in atlas_fund_holdings_changes + scores.

Runs daily. For each change row where outcome_quality_1m IS NULL and
to_date <= today - 30 days, looks up the stock's RS state and return
at to_date + 30 days and fills outcome_rs_state_1m, outcome_ret_1m,
outcome_quality_1m. Same logic for 3m window.

Then recomputes outcome_*_pct and outcome_score in atlas_fund_decision_scores
for affected (mstar_id, period_date) pairs.

Outcome quality definition (per spec):
- entry: outcome_quality = 'good' if outcome_rs_state in {Leader, Strong, Emerging}
- exit:  outcome_quality = 'good' if outcome_rs_state in {Weak, Laggard}
- increase/decrease: outcome_quality = 'neutral' always

Usage:
    python scripts/enrich_fund_decision_outcomes.py [--window 1m|3m|both]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()

_HIGH = frozenset({"Leader", "Strong", "Emerging"})
_LOW = frozenset({"Weak", "Laggard"})


def _derive_outcome_quality(action: str, rs_state: str | None) -> str:
    if rs_state is None:
        return "neutral"
    if action == "entry" and rs_state in _HIGH:
        return "good"
    if action == "entry" and rs_state in _LOW:
        return "bad"
    if action == "exit" and rs_state in _LOW:
        return "good"
    if action == "exit" and rs_state in _HIGH:
        return "bad"
    return "neutral"


def _enrich_window(engine: Engine, days: int, rs_col: str, ret_col: str, quality_col: str) -> int:
    """Fill outcome columns for one time window via single SQL UPDATE...FROM.

    Uses a CTE with DISTINCT ON to find the closest available stock state within
    ±7 days of the outcome target date. No Python loop, no N+1 queries.
    The CASE expression in the UPDATE handles outcome_quality derivation in SQL.
    Returns rows updated.
    """
    cutoff = date.today() - timedelta(days=days)
    interval = timedelta(days=days)
    ret_field = "ret_1m" if days == 30 else "ret_3m"

    with open_compute_session(engine) as conn:
        result = conn.execute(
            text(f"""
            WITH outcome_states AS (
                SELECT DISTINCT ON (c.id)
                    c.id,
                    s.rs_state,
                    sm.{ret_field} AS ret_val
                FROM atlas.atlas_fund_holdings_changes c
                JOIN atlas.atlas_stock_states_daily s
                    ON s.instrument_id::text = c.instrument_id::text
                   AND s.date BETWEEN c.to_date + :interval - INTERVAL '7 days'
                                  AND c.to_date + :interval + INTERVAL '7 days'
                JOIN atlas.atlas_stock_metrics_daily sm
                    ON sm.instrument_id = s.instrument_id AND sm.date = s.date
                WHERE c.{quality_col} IS NULL
                  AND c.to_date <= :cutoff
                ORDER BY c.id, ABS(EXTRACT(EPOCH FROM (s.date::timestamp - (c.to_date + :interval))))
            )
            UPDATE atlas.atlas_fund_holdings_changes c
            SET
                {rs_col}      = o.rs_state,
                {ret_col}     = o.ret_val,
                {quality_col} = CASE
                    WHEN c.action IN ('increase','decrease') THEN 'neutral'
                    WHEN c.action = 'entry' AND o.rs_state IN ('Leader','Strong','Emerging') THEN 'good'
                    WHEN c.action = 'entry' AND o.rs_state IN ('Weak','Laggard') THEN 'bad'
                    WHEN c.action = 'exit'  AND o.rs_state IN ('Weak','Laggard') THEN 'good'
                    WHEN c.action = 'exit'  AND o.rs_state IN ('Leader','Strong','Emerging') THEN 'bad'
                    ELSE 'neutral'
                END,
                updated_at = NOW()
            FROM outcome_states o
            WHERE c.id = o.id
        """),
            {"cutoff": cutoff, "interval": interval},
        )
        updated = result.rowcount
        conn.commit()

    log.info("enrich_window_done", window_days=days, rows_updated=updated)
    return updated


def _recompute_outcome_scores(engine: Engine, window: str) -> int:
    """Recompute outcome_*_pct and outcome_score_* in atlas_fund_decision_scores."""
    if window == "1m":
        quality_col = "outcome_quality_1m"
        entries_pct_col = "outcome_entries_pct_1m"
        exits_pct_col = "outcome_exits_pct_1m"
        score_col = "outcome_score_1m"
    else:
        quality_col = "outcome_quality_3m"
        entries_pct_col = "outcome_entries_pct_3m"
        exits_pct_col = "outcome_exits_pct_3m"
        score_col = "outcome_score_3m"

    with open_compute_session(engine) as conn:
        result = conn.execute(
            text(f"""
            UPDATE atlas.atlas_fund_decision_scores ds
            SET
                {entries_pct_col} = sub.entries_pct,
                {exits_pct_col}   = sub.exits_pct,
                {score_col}       = CASE
                    WHEN sub.entries_pct IS NULL AND sub.exits_pct IS NULL THEN NULL
                    WHEN sub.entries_pct IS NULL THEN sub.exits_pct
                    WHEN sub.exits_pct   IS NULL THEN sub.entries_pct
                    ELSE (sub.entries_pct + sub.exits_pct) / 2
                END,
                updated_at = NOW()
            FROM (
                SELECT
                    mstar_id,
                    to_date AS period_date,
                    AVG(CASE WHEN action = 'entry' AND {quality_col} = 'good' THEN 100.0
                             WHEN action = 'entry' AND {quality_col} = 'bad'  THEN 0.0
                             ELSE NULL END) AS entries_pct,
                    AVG(CASE WHEN action = 'exit'  AND {quality_col} = 'good' THEN 100.0
                             WHEN action = 'exit'  AND {quality_col} = 'bad'  THEN 0.0
                             ELSE NULL END) AS exits_pct
                FROM atlas.atlas_fund_holdings_changes
                WHERE {quality_col} IS NOT NULL
                GROUP BY mstar_id, to_date
            ) sub
            WHERE ds.mstar_id = sub.mstar_id AND ds.period_date = sub.period_date
        """)
        )
        conn.commit()
    log.info("recomputed_outcome_scores", window=window)
    return result.rowcount


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--window", choices=["1m", "3m", "both"], default="both")
    args = p.parse_args(argv)
    engine = get_engine()

    if args.window in ("1m", "both"):
        n = _enrich_window(
            engine, 30, "outcome_rs_state_1m", "outcome_ret_1m", "outcome_quality_1m"
        )
        if n > 0:
            _recompute_outcome_scores(engine, "1m")

    if args.window in ("3m", "both"):
        n = _enrich_window(
            engine, 90, "outcome_rs_state_3m", "outcome_ret_3m", "outcome_quality_3m"
        )
        if n > 0:
            _recompute_outcome_scores(engine, "3m")

    return 0


if __name__ == "__main__":
    sys.exit(main())
