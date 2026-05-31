"""SP03: breakout candidates handler.

Reads ``mv_breakout_candidates`` — stocks that transitioned INTO Leader or
Strong on the most recent trading day. Streams:
  1. reasoning_step — "Querying breakout candidates"
  2. message_chunk  — count of candidates and context
  3. table          — candidates ordered by rs_pctile_3m DESC
  4. done
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.api.openbb.events import done, message_chunk, reasoning_step, table
from atlas.api.openbb.schemas import TableColumn, TableData

log = structlog.get_logger()

_COLUMNS: list[TableColumn] = [
    TableColumn(name="symbol", dtype="str"),
    TableColumn(name="company_name", dtype="str"),
    TableColumn(name="sector", dtype="str"),
    TableColumn(name="tier", dtype="str"),
    TableColumn(name="new_rs_state", dtype="str"),
    TableColumn(name="prior_rs_state", dtype="str"),
    TableColumn(name="rs_pctile_3m", dtype="float"),
    TableColumn(name="rs_3m_nifty500", dtype="float"),
    TableColumn(name="momentum_state", dtype="str"),
    TableColumn(name="state_since_date", dtype="date"),
]

_COLUMN_NAMES = [c.name for c in _COLUMNS]


async def handle_breakouts(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]:
    """Stream breakout candidates from ``mv_breakout_candidates``."""
    yield reasoning_step(
        name="Querying breakout candidates",
        description=(
            "Reading mv_breakout_candidates — stocks transitioning into "
            "Leader or Strong RS state today."
        ),
    )

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    f"""
                    SELECT {", ".join(_COLUMN_NAMES)}
                    FROM atlas.mv_breakout_candidates
                    ORDER BY rs_pctile_3m DESC NULLS LAST
                    """  # noqa: S608 — _COLUMN_NAMES are constants; no user input
                )
            )
            .mappings()
            .fetchall()
        )

    if not rows:
        yield message_chunk(
            "No breakout candidates were identified for the most recent trading day. "
            "This is normal on non-trading days or when no stocks transition state. "
            "The view is refreshed nightly — check back after the next market session."
        )
        yield done()
        return

    n_leaders = sum(1 for r in rows if r.get("new_rs_state") == "Leader")
    n_strong = sum(1 for r in rows if r.get("new_rs_state") == "Strong")

    yield message_chunk(
        f"{len(rows)} stock{'s' if len(rows) != 1 else ''} transitioned into a "
        "higher RS state on the latest trading day: "
        f"{n_leaders} entered **Leader** and {n_strong} entered **Strong** "
        "classification. "
        "These stocks exhibited an improvement in relative strength vs Nifty 500 "
        "compared to the prior session."
    )

    rows_out = [
        {col: (str(r[col]) if r[col] is not None else None) for col in _COLUMN_NAMES} for r in rows
    ]
    data_as_of = str(rows[0]["state_since_date"]) if rows[0].get("state_since_date") else None
    yield table(
        TableData(
            name="Breakout Candidates",
            description=(
                "Source: mv_breakout_candidates. Stocks entering Leader or Strong RS state today."
            ),
            columns=_COLUMNS,
            rows=rows_out,
            data_as_of=data_as_of,
        )
    )

    log.info("openbb_breakouts_handler_complete", count=len(rows))
    yield done()
