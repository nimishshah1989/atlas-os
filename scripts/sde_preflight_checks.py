"""SDE pre-flight data-integrity checks. Run on EC2 before the Phase 0 spike.

Check 1 - corporate-action adjustment coverage: fraction of recent OHLCV
rows with a non-null close_adj. Low coverage means factors computed on
COALESCE(close_adj, close) sit partly on unadjusted prices.

Check 2 - delisted-stock history retention: instruments last seen well in
the past should still carry full history. If dead stocks were purged,
survivorship bias re-enters the universe.

Usage (on EC2 host jsl-wealth-server):
    python -m scripts.sde_preflight_checks
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()

_ADJ_SQL = """
    SELECT count(*) AS total,
           count(close_adj) AS with_adj
      FROM public.de_equity_ohlcv
     WHERE date >= current_date - INTERVAL '2 years'
"""

_DELISTED_SQL = """
    WITH last_seen AS (
      SELECT instrument_id, max(date) AS last_date, count(*) AS n_rows
        FROM public.de_equity_ohlcv
       GROUP BY instrument_id
    )
    SELECT count(*) FILTER (
             WHERE last_date < current_date - INTERVAL '180 days'
           ) AS delisted,
           count(*) FILTER (
             WHERE last_date < current_date - INTERVAL '180 days'
               AND n_rows >= 250
           ) AS delisted_with_history
      FROM last_seen
"""


@dataclass(frozen=True)
class PreflightResult:
    """Raw counts from the two pre-flight queries."""

    adj_total: int
    adj_with: int
    delisted: int
    delisted_with_history: int


def run_preflight(engine: Engine) -> PreflightResult:
    """Execute both pre-flight queries and return the raw counts."""
    with engine.connect() as conn:
        adj = conn.execute(text(_ADJ_SQL)).one()
        dl = conn.execute(text(_DELISTED_SQL)).one()
    return PreflightResult(
        adj_total=int(adj.total),
        adj_with=int(adj.with_adj),
        delisted=int(dl.delisted),
        delisted_with_history=int(dl.delisted_with_history),
    )


def format_preflight(result: PreflightResult) -> str:
    """Render the pre-flight result as a human-readable report.

    Check 1 passes at >= 80% close_adj coverage. Check 2 passes when >= 80%
    of delisted instruments still carry >= 250 rows of history.
    """
    adj_pct = (result.adj_with / result.adj_total * 100) if result.adj_total else 0.0
    hist_pct = (result.delisted_with_history / result.delisted * 100) if result.delisted else 0.0
    check1 = "PASS" if adj_pct >= 80 else "WARN"
    check2 = "PASS" if (result.delisted == 0 or hist_pct >= 80) else "WARN"
    return "\n".join(
        [
            "SDE pre-flight checks",
            f"  close_adj coverage  : {adj_pct:.1f}%  "
            f"({result.adj_with}/{result.adj_total} rows, last 2y)",
            f"  delisted instruments: {result.delisted}",
            f"  ...with >=250 rows  : {result.delisted_with_history} ({hist_pct:.1f}%)",
            "",
            f"  Check 1 {check1}: corporate-action adjustment coverage",
            f"  Check 2 {check2}: delisted-stock history retention",
        ]
    )


def main() -> None:
    report = format_preflight(run_preflight(get_engine()))
    print(report)
    log.info("sde_preflight_done")


if __name__ == "__main__":
    main()
