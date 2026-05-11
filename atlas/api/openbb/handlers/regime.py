"""SP03: market regime handler.

Reads ``mv_current_market_regime`` (one row). Streams:
  1. reasoning_step — "Querying market regime"
  2. message_chunk  — 2-sentence summary of current regime state
  3. table          — all regime columns formatted for display
  4. done

SEBI: all narrative is research language only. No buy/sell/invest verbs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.api.openbb.events import done, message_chunk, reasoning_step, table
from atlas.api.openbb.schemas import TableColumn, TableData

log = structlog.get_logger()

# Columns to surface in the table event (subset of mv_current_market_regime).
# Ordered for analyst readability — regime state first, then supporting signals.
_COLUMNS: list[TableColumn] = [
    TableColumn(name="date", dtype="date"),
    TableColumn(name="regime_state", dtype="str"),
    TableColumn(name="deployment_multiplier", dtype="float"),
    TableColumn(name="dislocation_active", dtype="bool"),
    TableColumn(name="india_vix", dtype="float"),
    TableColumn(name="pct_above_ema_50", dtype="float"),
    TableColumn(name="pct_above_ema_200", dtype="float"),
    TableColumn(name="pct_in_strong_states", dtype="float"),
    TableColumn(name="ad_ratio", dtype="float"),
    TableColumn(name="net_new_highs", dtype="int"),
    TableColumn(name="mcclellan_oscillator", dtype="float"),
]

_COLUMN_NAMES = [c.name for c in _COLUMNS]


async def handle_regime(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]:
    """Stream the current market regime from ``mv_current_market_regime``."""
    yield reasoning_step(
        name="Querying market regime",
        description="Reading mv_current_market_regime — latest regime row with breadth signals.",
    )

    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    SELECT {", ".join(_COLUMN_NAMES)}
                    FROM atlas.mv_current_market_regime
                    LIMIT 1
                    """  # noqa: S608 — _COLUMN_NAMES are module constants, no user input
                )
            )
            .mappings()
            .fetchone()
        )

    if row is None:
        yield message_chunk(
            "Market regime data is not yet available. "
            "The materialized view may not have been populated. "
            "Run the nightly pipeline and refresh mv_current_market_regime."
        )
        yield done()
        return

    regime = row["regime_state"] or "Unknown"
    multiplier = row["deployment_multiplier"]
    dislocation = row["dislocation_active"]
    as_of: date = row["date"]

    # SEBI-compliant narrative: describes state, no buy/sell language.
    narrative_parts = [
        f"As of {as_of.strftime('%d-%b-%Y')}, "
        f"the Indian equity market is classified as **{regime}**.",
    ]
    if multiplier is not None:
        narrative_parts.append(
            f"The deployment multiplier stands at {float(multiplier):.2f}x, "
            "reflecting current breadth and momentum conditions."
        )
    if dislocation:
        narrative_parts.append(
            "A **market dislocation** is currently active — "
            "breadth signals are diverging from price."
        )

    yield message_chunk(" ".join(narrative_parts))

    rows_out = [{col: (str(row[col]) if row[col] is not None else None) for col in _COLUMN_NAMES}]
    yield table(
        TableData(
            name="Current Market Regime",
            description=(
                f"Atlas market regime as of {as_of.strftime('%d-%b-%Y')}. "
                "Source: mv_current_market_regime."
            ),
            columns=_COLUMNS,
            rows=rows_out,
            data_as_of=str(as_of),
        )
    )

    log.info("openbb_regime_handler_complete", regime=regime, as_of=str(as_of))
    yield done()
