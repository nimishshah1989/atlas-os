"""Atlas-M2 daily incremental run.

Computes T-1 metrics + states for stocks and ETFs. Runs nightly from EC2
cron at 21:00 IST (after JIP T-1 ingest completes). Budget: ≤8 minutes total.

Usage::

    python scripts/m2_daily.py                # T-1 (yesterday)
    python scripts/m2_daily.py --date 2026-05-05
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import structlog
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.compute.etfs import run_etf_daily  # noqa: E402
from atlas.compute.stocks import run_stock_daily  # noqa: E402
from atlas.intelligence.aggregations.etf import (  # noqa: E402
    aggregate_etf_states,
    load_etf_holdings_panel,
)
from atlas.intelligence.aggregations.fund import (  # noqa: E402
    aggregate_fund_composition,
    load_fund_holdings_panel,
)
from atlas.intelligence.aggregations.persistence import (  # noqa: E402
    persist_etf_state_v2,
    persist_fund_state_v2,
    persist_sector_state_v2,
)
from atlas.intelligence.aggregations.sector import (  # noqa: E402
    aggregate_sector_states,
    load_stock_panel,
)

log = structlog.get_logger()


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _build_engine() -> Engine:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise SystemExit("ATLAS_DB_URL is not set. Source .env first.")
    return create_engine(db_url, pool_size=2, max_overflow=0, pool_pre_ping=True)


def run_state_engine_daily(as_of_date: date) -> None:
    """Classify states via state-engine and run all three aggregators.

    Phase:
    1. Shell out to 'atlas-lab states classify' for as_of_date (UPSERT-safe).
    2. Load stock panel for as_of_date -> aggregate sector states -> persist.
    3. Load fund holdings panel (monthly, uses latest on-or-before date) -> aggregate -> persist.
    4. Load ETF panel for as_of_date -> aggregate -> persist.

    All aggregators are idempotent (ON CONFLICT DO UPDATE). Row counts are
    logged at each step. Legacy atlas_stock_states_daily continues to receive
    writes from run_stock_daily() in the same nightly run (coexistence phase).
    """
    date_str = str(as_of_date)
    log.info("state_engine_daily_starting", as_of_date=date_str)

    # Step 1: classify states via CLI (builds its own engine, UPSERT-safe).
    cmd = [
        sys.executable,
        "-m",
        "atlas.trading.cli",
        "states",
        "classify",
        "--start",
        date_str,
        "--end",
        date_str,
        "--classifier-version",
        "v2.0-validated",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))  # noqa: S603 — cmd is a fixed internal list, no user input
    if result.returncode != 0:
        log.error(
            "state_engine_classify_failed",
            returncode=result.returncode,
            stderr=result.stderr[-500:] if result.stderr else "",
        )
        raise RuntimeError(
            f"states classify failed (rc={result.returncode}): {result.stderr[-200:]}"
        )
    classify_output = result.stdout.strip()
    log.info("state_engine_classify_done", output=classify_output)
    print(f"[state-engine classify] {classify_output}")

    engine = _build_engine()

    # Step 2: sector aggregation.
    stock_panel = load_stock_panel(engine, as_of_date=date_str)
    log.info("state_engine_sector_panel_loaded", rows=len(stock_panel))
    sector_agg = aggregate_sector_states(stock_panel)
    sector_rows = persist_sector_state_v2(engine, sector_agg)
    log.info(
        "state_engine_sector_persisted", rows_upserted=sector_rows, input_rows=len(stock_panel)
    )
    print(f"[state-engine sectors] panel={len(stock_panel)} upserted={sector_rows}")

    # Per-asset-class error tracking: a failure in one step does not block others,
    # but the script exits non-zero so ops monitoring catches partial failures.
    _step_errors: list[str] = []

    # Step 3: fund aggregation (monthly cadence; use most recent disclosure on-or-before date).
    # Pass None to load all disclosed months — the persist call is idempotent.
    try:
        fund_panel = load_fund_holdings_panel(engine, as_of_date=None)
        log.info("state_engine_fund_panel_loaded", rows=len(fund_panel))
        fund_agg = aggregate_fund_composition(fund_panel)
        fund_rows = persist_fund_state_v2(engine, fund_agg)
        log.info("state_engine_fund_persisted", rows_upserted=fund_rows, input_rows=len(fund_panel))
        print(f"[state-engine funds] panel={len(fund_panel)} upserted={fund_rows}")
    except Exception as exc:
        log.error(
            "state_engine_fund_failed",
            error=str(exc)[:400],
            exc_type=type(exc).__name__,
        )
        _step_errors.append(f"fund: {type(exc).__name__}: {str(exc)[:200]}")
        print(f"[state-engine funds] FAILED — {type(exc).__name__}: {str(exc)[:120]}")

    # Step 4: ETF aggregation.
    try:
        etf_panel = load_etf_holdings_panel(engine, as_of_date=date_str)
        log.info("state_engine_etf_panel_loaded", rows=len(etf_panel))
        etf_agg = aggregate_etf_states(etf_panel)
        etf_rows = persist_etf_state_v2(engine, etf_agg)
        log.info("state_engine_etf_persisted", rows_upserted=etf_rows, input_rows=len(etf_panel))
        print(f"[state-engine etfs] panel={len(etf_panel)} upserted={etf_rows}")
    except Exception as exc:
        log.error(
            "state_engine_etf_failed",
            error=str(exc)[:400],
            exc_type=type(exc).__name__,
        )
        _step_errors.append(f"etf: {type(exc).__name__}: {str(exc)[:200]}")
        print(f"[state-engine etfs] FAILED — {type(exc).__name__}: {str(exc)[:120]}")

    engine.dispose()

    if _step_errors:
        log.error("state_engine_partial_failure", errors=_step_errors)
        raise RuntimeError(
            f"state_engine_daily partial failure ({len(_step_errors)} step(s) failed): "
            + "; ".join(_step_errors)
        )

    log.info("state_engine_daily_done", as_of_date=date_str)


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas-M2 daily incremental run")
    parser.add_argument(
        "--date",
        type=_parse_date,
        default=datetime.now(UTC).date(),
        help="Target date (YYYY-MM-DD). Defaults to today UTC (pinned to UTC regardless of TZ env).",
    )
    args = parser.parse_args()

    log.info("m2_daily_starting", target_date=str(args.date))

    # Legacy compute — continues writing to atlas_stock_states_daily.
    # Coexists with the new state engine until Phase 9 burn-in completes.
    stock_result = run_stock_daily(args.date)
    print(f"[stocks] {stock_result}")

    etf_result = run_etf_daily(args.date)
    print(f"[etfs] {etf_result}")

    # New state engine + aggregators — writes to atlas_stock_state_daily (v2),
    # atlas_sector_state_v2, atlas_fund_state_v2, atlas_etf_state_v2.
    try:
        run_state_engine_daily(args.date)
    except RuntimeError as exc:
        # Partial failure: logged inside run_state_engine_daily.
        # Exit code 2 = partial success; allows ops alerts to distinguish from
        # exit code 1 (hard failure in run_stock_daily / run_etf_daily).
        log.error("m2_daily_partial_failure", error=str(exc)[:400])
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
