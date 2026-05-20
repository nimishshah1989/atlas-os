"""SDE Phase 0 spike - does any pandas-ta factor have tradeable
out-of-sample IC on the liquid Indian-equity universe?

Wires the SDE pure modules to the existing IC engine and writes a ranked
results report with a PROCEED / STOP verdict.

Run on EC2 (Mac psycopg2 is broken - see reference_ec2_access):
    ssh jsl-wealth-server
    cd <atlas-os repo checkout>
    git pull
    python -m scripts.sde_phase0_spike
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import cast

import pandas as pd
import structlog

from atlas.db import get_engine
from atlas.intelligence.validation.ic_engine import compute_ic_over_window
from atlas.research.sde.data import load_liquid_universe, load_ohlcv_panel
from atlas.research.sde.factors import generate_factors, liquidity_mask
from atlas.research.sde.ic_ranking import FactorICRow, evaluate_gate, rank_factors

log = structlog.get_logger()

# ~3m / 6m / 12m in trading days.
HORIZONS = [63, 126, 252]
OUT_PATH = Path("docs/sde/phase0-ic-results.md")


def _write_report(rows: list[FactorICRow], gate: dict[str, object]) -> None:
    verdict = "PROCEED to Phase 1" if gate["proceed"] else "STOP - no tradeable factor IC"
    lines = [
        "# SDE Phase 0 - Factor IC Results",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        f"## Decision: {verdict}",
        "",
        f"Survivors (out-of-sample IC, same sign as train, |IC|>=0.03, |t|>=2.0): "
        f"{len(gate['survivors'])}",  # type: ignore[arg-type]
        "",
        "| Factor | Horizon | Train IC | Train t | Test IC | Test t | N test |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        lines.append(
            f"| {r.factor} | {r.horizon} | {r.train_ic:.4f} | {r.train_t:.2f} "
            f"| {r.test_ic:.4f} | {r.test_t:.2f} | {r.n_test} |"
        )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    engine = get_engine()
    end = date.today()
    start = end - timedelta(days=365 * 6)  # ~5y usable after factor warm-up

    universe = load_liquid_universe(engine, start=start, end=end)
    panel = load_ohlcv_panel(engine, instrument_ids=universe, start=start, end=end)
    if panel.empty:
        raise SystemExit("sde_phase0: OHLCV panel is empty - check the date range/universe")

    factors = generate_factors(panel)
    mask = liquidity_mask(panel)
    close_panel = cast(pd.DataFrame, panel[["date", "instrument_id", "close"]])

    rows = rank_factors(
        factors, close_panel, horizons=HORIZONS, ic_fn=compute_ic_over_window, mask=mask
    )
    gate = evaluate_gate(rows)
    _write_report(rows, gate)

    log.info(
        "sde_phase0_done",
        proceed=gate["proceed"],
        n_survivors=len(gate["survivors"]),  # type: ignore[arg-type]
        report=str(OUT_PATH),
    )
    print(f"Phase 0 complete. Verdict: {'PROCEED' if gate['proceed'] else 'STOP'}")
    print(f"Report written to {OUT_PATH}")


if __name__ == "__main__":
    main()
