from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()


def insert_proposals(engine: Engine, proposals: list[dict[str, Any]]) -> int:
    """Insert pending proposals. Skip if same param_key already pending."""
    if not proposals:
        return 0
    written = 0
    with engine.begin() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        for p in proposals:
            result = conn.execute(
                text("""
                    INSERT INTO atlas.atlas_cts_param_proposals
                        (as_of_date, param_key, current_value, proposed_value,
                         smoothed_value, direction, expected_lift_delta, rationale, status)
                    SELECT :d, :key, :cur, :prop, :smooth, :dir, :delta, :rat, 'pending'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM atlas.atlas_cts_param_proposals
                        WHERE param_key = :key AND status = 'pending'
                    )
                """),
                {
                    "d": p["as_of_date"],
                    "key": p["param_key"],
                    "cur": p["current_value"],
                    "prop": p["proposed_value"],
                    "smooth": p["smoothed_value"],
                    "dir": p["direction"],
                    "delta": p.get("expected_lift_delta"),
                    "rat": p["rationale"],
                },
            )
            written += result.rowcount
    log.info("cts_proposals_inserted", count=written)
    return written
