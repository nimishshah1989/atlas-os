"""Atlas — Adaptive Technical Lens for Asset States.

Reads from JIP Data Core's ``public.de_*`` tables and writes to its own
``atlas`` schema. Per ``docs/01_BACKEND_ARCHITECTURE.md`` Section 1.

The package is laid out per architecture Section 11:

- ``atlas.universe``  — Layer 2 reference data (M1)
- ``atlas.compute``   — Layer 3 metric, state, and decision pipelines (M2-M5)
- ``atlas.validation`` — Five-tier validation framework
- ``atlas.orchestration`` — Pipeline runner, stage definitions, notifications
- ``atlas.api``       — Thin FastAPI serving layer (post-M5)
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
