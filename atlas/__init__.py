"""Atlas — equity-intelligence compute modulith.

Reads and writes the single ``atlas_foundation`` Postgres schema. Bounded contexts:

- ``atlas.compute``   — index metrics, breadth, regime
- ``atlas.intraday``  — current-day live indices/sector engine
- ``atlas.lenses``    — the lens scorers + composite

Shared kernel: ``atlas.primitives`` / ``atlas.db`` / ``atlas.config``. Ingestion
lives in ``scripts/foundation/``; the nightly orchestrator in ``scripts/ops/``.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import structlog

__version__ = "0.1.0"

_IST = ZoneInfo("Asia/Kolkata")


def _ist_timestamper(_logger, _name, event_dict):
    """structlog processor: emit timestamps in Asia/Kolkata regardless of system TZ.

    Internal logic (date.today(), cron scheduling, DB UTC storage) is untouched;
    only the user-visible log line is rendered in IST.
    """
    event_dict["timestamp"] = datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")
    return event_dict


structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        _ist_timestamper,
        structlog.dev.ConsoleRenderer(),
    ],
)
