#!/usr/bin/env python3
"""End-to-end test: create a model portfolio with stocks + funds and run the backtest.

Portfolio composition (8 instruments, weights sum to 100%):
  Stocks (5 × 10% = 50%):
    - ADANIPORTS  Adani Ports
    - APARINDS    Apar Industries
    - BANDHANBNK  Bandhan Bank
    - BSE         BSE Limited
    - DATAPATTNS  Data Patterns

  Funds (3 × 16.67% = 50%):  IDs must exist in atlas_fund_decisions_daily + de_mf_nav_daily
    - F00001G6N8  360 ONE Flexicap Reg Gr
    - F0GBR06S9H  Aditya BSL Flexi Cap Gr
    - F0GBR06S9J  Aditya BSL Large Cap Gr

Run on EC2 where vectorbt is installed:
    python scripts/test_portfolio_backtest.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

import json

from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine
from atlas.simulation.custom.builder import InstrumentWeight, validate_custom_portfolio
from atlas.simulation.custom.portfolio import run_custom_portfolio_backtest

# ---------------------------------------------------------------------------
# Test portfolio definition
# ---------------------------------------------------------------------------

_TEST_PORTFOLIO_NAME = "Atlas Test Portfolio — Stocks+Funds (auto-created)"

_INSTRUMENTS: list[InstrumentWeight] = [
    # Stocks: 5 × 10% = 50%
    InstrumentWeight("8e6ba353-edc9-4097-86a7-7b4a29389355", "stock", 10.0),  # ADANIGREEN
    InstrumentWeight("01b6ed95-cfba-45bd-87c9-4edc003a6c9d", "stock", 10.0),  # ADANIPORTS
    InstrumentWeight("342bebb2-b5da-4b9a-b33a-c8d7e937c676", "stock", 10.0),  # APARINDS
    InstrumentWeight("03864dd0-6424-4259-839d-401d7ef41933", "stock", 10.0),  # BANDHANBNK
    InstrumentWeight("a0113f34-f459-416f-bac8-68801b14e8e0", "stock", 10.0),  # BSE
    # Funds: 3 × ~16.67% = ~50% (must have data in decisions + NAV tables)
    InstrumentWeight("F00001G6N8", "fund", 16.67),  # 360 ONE Flexicap Reg Gr
    InstrumentWeight("F0GBR06S9H", "fund", 16.67),  # Aditya BSL Flexi Cap Gr
    InstrumentWeight("F0GBR06S9J", "fund", 16.66),  # Aditya BSL Large Cap Gr
]


def _create_portfolio(engine, name: str, instruments: list[InstrumentWeight]) -> str:
    """Insert portfolio record and return its UUID string."""
    instruments_json = json.dumps(
        [
            {
                "instrument_id": i.instrument_id,
                "instrument_type": i.instrument_type,
                "weight_pct": i.weight_pct,
            }
            for i in instruments
        ]
    )
    with open_compute_session(engine) as conn:
        row_id: str = conn.execute(
            text("""
                INSERT INTO atlas.strategy_fm_custom_portfolios
                    (name, instruments)
                VALUES (:name, CAST(:instruments AS jsonb))
                RETURNING id::text
            """),
            {"name": name, "instruments": instruments_json},
        ).scalar_one()
        conn.commit()
    return row_id


def _fetch_backtest_result(engine, portfolio_id: str) -> dict:
    with open_compute_session(engine) as conn:
        row = conn.execute(
            text("""
                SELECT
                    p.name,
                    p.backtest_id,
                    b.sharpe_ratio,
                    b.total_return,
                    b.max_drawdown,
                    b.start_date,
                    b.end_date
                FROM atlas.strategy_fm_custom_portfolios p
                LEFT JOIN atlas.strategy_backtest_results b ON b.id = p.backtest_id
                WHERE p.id = :pid
            """),
            {"pid": portfolio_id},
        ).fetchone()
    if row is None:
        return {}
    return dict(row._mapping)


def main() -> None:
    engine = get_engine()

    print("\nAtlas Model Portfolio — End-to-End Backtest Test")
    print("=" * 60)
    print(f"Portfolio: {_TEST_PORTFOLIO_NAME}")
    print(
        f"Instruments: {len(_INSTRUMENTS)} ({sum(1 for i in _INSTRUMENTS if i.instrument_type=='stock')} stocks, "
        f"{sum(1 for i in _INSTRUMENTS if i.instrument_type=='fund')} funds)"
    )
    total_weight = sum(i.weight_pct for i in _INSTRUMENTS)
    print(f"Total weight: {total_weight:.2f}%")
    print()

    # Step 1: Validate
    print("Step 1: Validating instruments against Atlas universe...")
    try:
        validate_custom_portfolio(_INSTRUMENTS, engine)
        print("  ✓ All instruments valid")
    except ValueError as e:
        print(f"  ✗ Validation failed: {e}")
        sys.exit(1)

    # Step 2: Save to DB
    print("\nStep 2: Saving portfolio to DB...")
    portfolio_id = _create_portfolio(engine, _TEST_PORTFOLIO_NAME, _INSTRUMENTS)
    print(f"  ✓ Portfolio ID: {portfolio_id}")

    # Step 3: Run backtest (synchronous — no background process)
    print("\nStep 3: Running backtest (18-month lookback)...")
    try:
        run_custom_portfolio_backtest(UUID(portfolio_id), engine)
        print("  ✓ Backtest complete")
    except Exception as e:
        print(f"  ✗ Backtest failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Step 4: Print results
    print("\nStep 4: Results")
    print("-" * 60)
    r = _fetch_backtest_result(engine, portfolio_id)
    if not r or r.get("backtest_id") is None:
        print("  ✗ No backtest result found in DB")
        sys.exit(1)

    sharpe = r["sharpe_ratio"]
    ret = r["total_return"]
    dd = r["max_drawdown"]
    start = r["start_date"]
    end = r["end_date"]

    print(f"  Period      : {start} → {end}")
    print(f"  Total return: {ret*100:+.1f}%" if ret is not None else "  Total return: N/A")
    print(f"  Max drawdown: {dd*100:.1f}%" if dd is not None else "  Max drawdown: N/A")
    print(f"  Sharpe ratio: {sharpe:.3f}" if sharpe is not None else "  Sharpe ratio: N/A")
    print(f"\n  Backtest ID : {r['backtest_id']}")
    print(f"  Portfolio ID: {portfolio_id}")
    print()
    print("✓ End-to-end test PASSED — backtest machinery working for mixed stock+fund portfolios")


if __name__ == "__main__":
    main()
