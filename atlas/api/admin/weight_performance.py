"""Stage 4c — admin endpoint: live performance + recent reverts.

GET /api/admin/weight-performance returns, for each currently-active
weight set, its predicted IC and a 30-day rolling realized-IC trail,
plus the count of recent days below the 0.5 ratio threshold. Also lists
the most recent revert events (last 30 days).

Auth: same dual-path (_require_admin) as the proposals route — JWT
role=admin or ATLAS_INTERNAL_SECRET bearer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import text

from atlas.api.admin.proposals import _require_admin
from atlas.db import get_engine

log = structlog.get_logger()

router = APIRouter(prefix="/api/admin/weight-performance", tags=["admin"])


_ACTIVE_VERSIONS_SQL = text("""
    SELECT tier, regime,
           tier || '@' || MAX(approved_at)::text AS version,
           MAX(holdout_ic) AS predicted_ic
    FROM atlas.atlas_signal_weights
    WHERE effective_to IS NULL
    GROUP BY tier, regime
    ORDER BY tier
""")

_RECENT_PERF_SQL = text("""
    SELECT weight_set_version, as_of_date,
           realized_ic, ic_ratio, n_observations
    FROM atlas.atlas_signal_weights_live_perf
    WHERE weight_set_version = :version
      AND as_of_date >= CURRENT_DATE - INTERVAL '30 days'
    ORDER BY as_of_date ASC
""")

_RECENT_REVERTS_SQL = text("""
    SELECT id::text, tier, regime,
           reverted_from_version, restored_to_version,
           days_below_threshold, realized_ic_avg, predicted_holdout_ic,
           triggered_by, notes, applied_at
    FROM atlas.atlas_weight_revert_log
    WHERE applied_at >= NOW() - INTERVAL '30 days'
    ORDER BY applied_at DESC
""")


@router.get("")
async def list_weight_performance(request: Request) -> dict[str, Any]:
    _require_admin(request)
    engine = get_engine()

    with engine.connect() as conn:
        actives = conn.execute(_ACTIVE_VERSIONS_SQL).fetchall()

        active_sets: list[dict[str, Any]] = []
        for row in actives:
            tier, regime, version, predicted = row[0], row[1], row[2], row[3]
            perf_rows = conn.execute(_RECENT_PERF_SQL, {"version": version}).fetchall()
            trail: list[dict[str, Any]] = [
                {
                    "date": str(p[1]),
                    "realized_ic": float(p[2]) if p[2] is not None else None,
                    "ratio": float(p[3]) if p[3] is not None else None,
                    "n_observations": int(p[4]),
                }
                for p in perf_rows
            ]
            days_below = 0
            for t in trail:
                r = t.get("ratio")
                if isinstance(r, (int, float)) and r < 0.5:  # noqa: UP038
                    days_below += 1
            active_sets.append(
                {
                    "tier": tier,
                    "regime": regime,
                    "version": version,
                    "predicted_ic": float(predicted) if predicted is not None else None,
                    "trail": trail,
                    "days_below_threshold": days_below,
                    "n_trail_rows": len(trail),
                    "in_revert_territory": days_below == len(trail) and len(trail) >= 60,
                }
            )

        revert_rows = conn.execute(_RECENT_REVERTS_SQL).fetchall()

    reverts = [
        {
            "id": r[0],
            "tier": r[1],
            "regime": r[2],
            "reverted_from": r[3],
            "restored_to": r[4],
            "days_below_threshold": int(r[5]),
            "realized_ic_avg": float(r[6]) if r[6] is not None else None,
            "predicted_holdout_ic": float(r[7]) if r[7] is not None else None,
            "triggered_by": r[8],
            "notes": r[9],
            "applied_at": r[10].isoformat() if isinstance(r[10], datetime) else str(r[10]),
        }
        for r in revert_rows
    ]

    return {"active_sets": active_sets, "recent_reverts": reverts}
