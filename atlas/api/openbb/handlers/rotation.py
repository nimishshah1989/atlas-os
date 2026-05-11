"""SP03: sector rotation handler.

Reads ``mv_sector_rotation_state`` (~14 rows, one per NIFTY sector). Streams:
  1. reasoning_step — "Querying sector rotation"
  2. message_chunk  — summary of quadrant distribution
  3. table          — all sectors with RRG quadrant + RS metrics
  4. chart          — scatter: X=rs_velocity, Y=rs_pctile_cross_sector, label=sector_name
  5. done

Chart event note: the OpenBB BYO Copilot SDK contract for chart events was
specified by the plan; if the live SDK rejects the chart type, drop the
chart() call here without touching schemas. The other three event types
(message_chunk, reasoning_step, table) are confirmed in the SDK contract.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.api.openbb.events import chart, done, message_chunk, reasoning_step, table
from atlas.api.openbb.schemas import ChartData, ChartSeries, TableColumn, TableData

log = structlog.get_logger()

_COLUMNS: list[TableColumn] = [
    TableColumn(name="sector_name", dtype="str"),
    TableColumn(name="rrg_quadrant", dtype="str"),
    TableColumn(name="rs_level", dtype="float"),
    TableColumn(name="rs_velocity", dtype="float"),
    TableColumn(name="rs_pctile_cross_sector", dtype="float"),
    TableColumn(name="sector_state", dtype="str"),
    TableColumn(name="bottomup_rs_state", dtype="str"),
    TableColumn(name="bottomup_momentum_state", dtype="str"),
    TableColumn(name="participation_rs_pct", dtype="float"),
    TableColumn(name="constituent_count", dtype="int"),
]

_COLUMN_NAMES = [c.name for c in _COLUMNS]


async def handle_rotation(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]:
    """Stream sector rotation state from ``mv_sector_rotation_state``."""
    yield reasoning_step(
        name="Querying sector rotation",
        description=(
            "Reading mv_sector_rotation_state — RRG quadrant assignments and "
            "RS metrics for all sectors."
        ),
    )

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    f"""
                    SELECT {", ".join(_COLUMN_NAMES)}, date
                    FROM atlas.mv_sector_rotation_state
                    ORDER BY rs_pctile_cross_sector DESC NULLS LAST
                    """  # noqa: S608 — _COLUMN_NAMES are constants; no user input
                )
            )
            .mappings()
            .fetchall()
        )

    if not rows:
        yield message_chunk(
            "Sector rotation data is not yet available. "
            "The materialized view may not be populated — ensure SP02 migrations "
            "have run and the nightly sector pipeline has executed."
        )
        yield done()
        return

    # Quadrant counts for narrative
    quadrant_counts: dict[str, int] = {}
    for r in rows:
        q = r.get("rrg_quadrant") or "Unknown"
        quadrant_counts[q] = quadrant_counts.get(q, 0) + 1

    leading = quadrant_counts.get("Leading", 0)
    improving = quadrant_counts.get("Improving", 0)
    weakening = quadrant_counts.get("Weakening", 0)
    lagging = quadrant_counts.get("Lagging", 0)

    yield message_chunk(
        f"Current sector rotation across {len(rows)} NIFTY sectors: "
        f"**{leading}** Leading, **{improving}** Improving, "
        f"**{weakening}** Weakening, **{lagging}** Lagging. "
        "Sectors are classified by RS level (cross-sectional percentile) and "
        "RS velocity (4-week rate-of-change of relative strength vs Nifty 500)."
    )

    rows_out = [
        {col: (str(r[col]) if r[col] is not None else None) for col in _COLUMN_NAMES} for r in rows
    ]
    data_as_of = str(rows[0]["date"]) if rows[0].get("date") else None
    yield table(
        TableData(
            name="Sector Rotation State",
            description=(
                "Source: mv_sector_rotation_state. "
                "RRG quadrants: Leading/Improving/Weakening/Lagging."
            ),
            columns=_COLUMNS,
            rows=rows_out,
            data_as_of=data_as_of,
        )
    )

    # Chart: RS velocity (X) vs RS percentile (Y) scatter — standard RRG layout.
    # Only include rows with both values non-null.
    scatter_x: list[float | str] = []
    scatter_y: list[float | str] = []
    scatter_labels: list[str] = []
    for r in rows:
        vx = r.get("rs_velocity")
        vy = r.get("rs_pctile_cross_sector")
        if vx is not None and vy is not None:
            try:
                scatter_x.append(float(vx))
                scatter_y.append(float(vy))
                scatter_labels.append(str(r.get("sector_name", "")))
            except (ValueError, TypeError):
                pass

    if scatter_x:
        yield chart(
            ChartData(
                name="Relative Rotation Graph — Sectors",
                kind="scatter",
                x_label="RS Velocity (4-week RoC)",
                y_label="RS Percentile (cross-sector)",
                series=[
                    ChartSeries(
                        name="Sectors",
                        x=scatter_x,
                        y=scatter_y,
                        labels=scatter_labels,
                    )
                ],
            )
        )

    log.info("openbb_rotation_handler_complete", sector_count=len(rows))
    yield done()
