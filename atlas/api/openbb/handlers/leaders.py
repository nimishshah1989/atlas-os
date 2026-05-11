"""SP03: top RS stocks handler.

Reads ``mv_rs_leaders_daily``. Optionally filters by sector extracted from
the query text (simple heuristic: ``in <sector>`` or ``for <sector>`` pattern).

Streams:
  1. reasoning_step — "Querying RS leaders"
  2. message_chunk  — brief summary (N stocks in Leader/Strong state)
  3. table          — top-50 rows ordered by rs_pctile_3m DESC
  4. done
"""

from __future__ import annotations

import re
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
    TableColumn(name="rs_state", dtype="str"),
    TableColumn(name="rs_pctile_3m", dtype="float"),
    TableColumn(name="rs_3m_nifty500", dtype="float"),
    TableColumn(name="momentum_state", dtype="str"),
    TableColumn(name="state_since_date", dtype="date"),
]

_COLUMN_NAMES = [c.name for c in _COLUMNS]

# Known NIFTY sector names (for sector hint extraction).
_KNOWN_SECTORS = {
    "it",
    "banking",
    "bank",
    "fmcg",
    "pharma",
    "healthcare",
    "auto",
    "realty",
    "metal",
    "energy",
    "infra",
    "financial",
    "media",
    "psu",
    "consumption",
}

_LIMIT = 50


def _extract_sector_hint(query_text: str) -> str | None:
    """Extract a sector name from the query, or return None.

    Looks for ``in <sector>`` or ``for <sector>`` patterns.
    Returns the matched word (lower-cased, for SQL parameterisation).
    """
    match = re.search(r"\b(?:in|for)\s+([A-Za-z]+)", query_text, re.IGNORECASE)
    if match:
        word = match.group(1).lower()
        if word in _KNOWN_SECTORS:
            return word
    return None


async def handle_leaders(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]:
    """Stream top RS stocks from ``mv_rs_leaders_daily``."""
    sector_hint = _extract_sector_hint(query_text)

    description = (
        "Reading mv_rs_leaders_daily"
        + (f" filtered to sector containing '{sector_hint}'" if sector_hint else " — all sectors")
        + f", top {_LIMIT} by 3-month RS percentile."
    )
    yield reasoning_step(name="Querying RS leaders", description=description)

    with engine.connect() as conn:
        if sector_hint:
            rows = (
                conn.execute(
                    text(
                        f"""
                        SELECT {", ".join(_COLUMN_NAMES)}
                        FROM atlas.mv_rs_leaders_daily
                        WHERE LOWER(sector) LIKE :sector
                        ORDER BY rs_pctile_3m DESC NULLS LAST
                        LIMIT :lim
                        """  # noqa: S608 — _COLUMN_NAMES constants; sector via bind param
                    ),
                    {"sector": f"%{sector_hint}%", "lim": _LIMIT},
                )
                .mappings()
                .fetchall()
            )
        else:
            rows = (
                conn.execute(
                    text(
                        f"""
                        SELECT {", ".join(_COLUMN_NAMES)}
                        FROM atlas.mv_rs_leaders_daily
                        ORDER BY rs_pctile_3m DESC NULLS LAST
                        LIMIT :lim
                        """  # noqa: S608 — _COLUMN_NAMES are constants; no user input
                    ),
                    {"lim": _LIMIT},
                )
                .mappings()
                .fetchall()
            )

    if not rows:
        yield message_chunk(
            "No RS leaders data is available. "
            + ("This may be because no stocks match the sector filter, or " if sector_hint else "")
            + "the materialized view may not yet be populated."
        )
        yield done()
        return

    n_leaders = sum(1 for r in rows if r.get("rs_state") == "Leader")
    n_strong = sum(1 for r in rows if r.get("rs_state") == "Strong")
    sector_str = f" in the {sector_hint.title()} sector" if sector_hint else ""

    yield message_chunk(
        f"{len(rows)} stocks{sector_str} currently exhibit strong relative strength "
        "vs Nifty 500. "
        f"{n_leaders} are classified as **Leader** and {n_strong} as **Strong** "
        "based on RS state. "
        "Ranked by 3-month RS percentile (higher = stronger relative performance)."
    )

    rows_out = [
        {col: (str(r[col]) if r[col] is not None else None) for col in _COLUMN_NAMES} for r in rows
    ]
    data_as_of = str(rows[0]["state_since_date"]) if rows[0].get("state_since_date") else None
    yield table(
        TableData(
            name="Top RS Stocks" + (f" — {sector_hint.title()}" if sector_hint else ""),
            description=(
                "Source: mv_rs_leaders_daily. Leader and Strong RS-state stocks, "
                "ranked by 3m RS percentile."
            ),
            columns=_COLUMNS,
            rows=rows_out,
            data_as_of=data_as_of,
        )
    )

    log.info("openbb_leaders_handler_complete", count=len(rows), sector=sector_hint)
    yield done()
