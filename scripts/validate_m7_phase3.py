#!/usr/bin/env python3
# scripts/validate_m7_phase3.py
"""End-to-end validation harness for M7 Phase 3 Custom Portfolio Builder.

Runs against the live Postgres DB. Each check is independent — a failure in
one does not block subsequent checks. Final summary gives go/no-go for
frontend work.

Run: python scripts/validate_m7_phase3.py
"""

from __future__ import annotations

import sys
import traceback
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------


class Result:
    def __init__(self, name: str) -> None:
        self.name = name
        self.passed = False
        self.detail = ""
        self.error: str | None = None

    def ok(self, detail: str = "") -> Result:
        self.passed = True
        self.detail = detail
        return self

    def fail(self, error: str) -> Result:
        self.passed = False
        self.error = error
        return self

    def __str__(self) -> str:
        mark = "✓" if self.passed else "✗"
        suffix = f" — {self.detail}" if self.detail else ""
        if self.error:
            suffix = f" — FAIL: {self.error}"
        return f"  [{mark}] {self.name}{suffix}"


def get_real_instruments(engine: Engine, n: int = 3) -> list[str]:
    """Pick n distinct instrument_ids with IDENTICAL trading-day coverage in the
    last 180 days. Identical coverage matters because vectorbt pivots the data
    by date — any mismatch produces NaN cells.
    """
    with engine.connect() as conn:
        # Pick the most common day-count and grab n instruments with exactly that count
        rows = conn.execute(
            text(
                """
                WITH cov AS (
                    SELECT CAST(d.instrument_id AS text) AS iid, COUNT(*) AS n_days
                    FROM atlas.atlas_stock_decisions_daily d
                    JOIN de_equity_ohlcv p
                      ON p.instrument_id = d.instrument_id AND p.date = d.date
                    WHERE d.date >= CURRENT_DATE - INTERVAL '180 days'
                      AND p.close IS NOT NULL
                    GROUP BY d.instrument_id
                ),
                modal AS (
                    SELECT n_days FROM cov GROUP BY n_days
                    ORDER BY COUNT(*) DESC LIMIT 1
                )
                SELECT cov.iid FROM cov, modal
                WHERE cov.n_days = modal.n_days
                ORDER BY cov.iid
                LIMIT :n
                """
            ),
            {"n": n},
        ).fetchall()
    return [r[0] for r in rows]


def get_trigger_instruments(engine: Engine) -> tuple[list[str], date, date]:
    """Return instruments with ≥1 entry trigger, plus the date range that covers them.

    The Atlas methodology has very strict multi-gate entry criteria, so triggers are
    sparse (~7 across 909K rows). For backtest validation we need to target these
    specific instruments.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT CAST(instrument_id AS text) AS iid,
                       MIN(date) AS first_trigger
                FROM atlas.atlas_stock_decisions_daily
                WHERE transition_trigger = true OR breakout_trigger = true
                GROUP BY instrument_id
                ORDER BY first_trigger
                """
            )
        ).fetchall()
    if not rows:
        return [], date.today() - timedelta(days=365), date.today()
    iids = [r[0] for r in rows]
    # Start 30 days before the earliest trigger so the portfolio has context
    earliest = min(r[1] for r in rows)
    start = earliest - timedelta(days=30)
    return iids, start, date.today()


# -----------------------------------------------------------------------------
# checks
# -----------------------------------------------------------------------------


def check_1_schema(engine: Engine) -> Result:
    r = Result("Schema sanity (M7 tables + key columns)")
    try:
        with engine.connect() as conn:
            # strategy_fm_custom_portfolios
            cols_p = {
                row[0]
                for row in conn.execute(
                    text(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'atlas'
                          AND table_name = 'strategy_fm_custom_portfolios'
                        """
                    )
                ).fetchall()
            }
            need_p = {
                "id",
                "name",
                "instruments",
                "backtest_id",
                "paper_trading_active",
                "created_at",
                "updated_at",
            }
            missing_p = need_p - cols_p
            if missing_p:
                return r.fail(f"strategy_fm_custom_portfolios missing columns: {missing_p}")

            # strategy_backtest_results
            cols_b = {
                row[0]
                for row in conn.execute(
                    text(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'atlas'
                          AND table_name = 'strategy_backtest_results'
                        """
                    )
                ).fetchall()
            }
            need_b = {
                "id",
                "strategy_id",
                "custom_portfolio_id",
                "backtest_type",
                "start_date",
                "end_date",
                "sharpe_ratio",
                "max_drawdown",
                "total_return",
            }
            missing_b = need_b - cols_b
            if missing_b:
                return r.fail(f"strategy_backtest_results missing columns: {missing_b}")

        r.ok(
            f"both tables present, columns match (portfolios={len(cols_p)}, backtest={len(cols_b)})"
        )
    except Exception as e:
        r.fail(f"{type(e).__name__}: {e}")
    return r


def check_2_universe_validation(engine: Engine, real_ids: list[str]) -> Result:
    r = Result("Universe validation (real + fake instruments)")
    try:
        from atlas.simulation.custom.builder import InstrumentWeight, validate_custom_portfolio

        # Should pass with real instruments
        portfolio_real = [
            InstrumentWeight(real_ids[0], "stock", 40.0),
            InstrumentWeight(real_ids[1], "stock", 35.0),
            InstrumentWeight(real_ids[2], "stock", 25.0),
        ]
        try:
            validate_custom_portfolio(portfolio_real, engine)
        except ValueError as e:
            return r.fail(f"Real portfolio rejected: {e}")

        # Should fail with fake instrument
        portfolio_fake = [
            InstrumentWeight(real_ids[0], "stock", 50.0),
            InstrumentWeight("ffffffff-aaaa-bbbb-cccc-dddddddddddd", "stock", 50.0),
        ]
        try:
            validate_custom_portfolio(portfolio_fake, engine)
            return r.fail("Fake instrument was NOT rejected")
        except ValueError as e:
            if "not in Atlas universe" not in str(e):
                return r.fail(f"Fake rejected but wrong message: {e}")

        r.ok("real instruments accepted, fake correctly rejected")
    except Exception as e:
        r.fail(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
    return r


def check_3_signal_matrix(engine: Engine, real_ids: list[str]) -> Result:
    r = Result("Signal matrix builder (real data, 90 trading days)")
    try:
        from atlas.simulation.core.signal_adapter import build_stock_etf_signal_matrix

        end = date.today()
        start = end - timedelta(days=180)
        sm = build_stock_etf_signal_matrix(
            engine=engine,
            instrument_ids=real_ids,
            start_date=start,
            end_date=end,
            decisions_table="atlas_stock_decisions_daily",
        )
        if len(sm.instruments) == 0:
            return r.fail(f"empty signal matrix for {real_ids}")
        if sm.prices.shape[0] < 30:
            return r.fail(f"too few trading days: {sm.prices.shape[0]}")
        if sm.prices.shape[1] != len(sm.instruments):
            return r.fail(
                f"price/instrument shape mismatch: {sm.prices.shape} vs {len(sm.instruments)}"
            )
        import numpy as np

        if np.isnan(sm.prices).any():
            return r.fail("NaN values in price matrix")

        r.ok(
            f"shape={sm.prices.shape}, instruments={len(sm.instruments)}, "
            f"date_range={sm.dates[0].date()}..{sm.dates[-1].date()}"
        )
    except Exception as e:
        r.fail(f"{type(e).__name__}: {e}")
    return r


def check_4_backtest_engine(engine: Engine) -> Result:
    r = Result("Backtest engine (vectorbt, instruments with known entry triggers)")
    try:
        from atlas.simulation.backtest.engine import run_backtest
        from atlas.simulation.core.signal_adapter import build_stock_etf_signal_matrix

        trigger_ids, start, end = get_trigger_instruments(engine)
        if not trigger_ids:
            return r.fail(
                "no entry triggers found in atlas_stock_decisions_daily — run M5 backfill"
            )

        sm = build_stock_etf_signal_matrix(
            engine=engine,
            instrument_ids=trigger_ids,
            start_date=start,
            end_date=end,
            decisions_table="atlas_stock_decisions_daily",
        )
        if len(sm.instruments) == 0:
            return r.fail(f"empty signal matrix for trigger instruments {trigger_ids}")

        result = run_backtest(sm, init_cash=10_000_000.0, fees_pct=0.001)
        if result.total_return is None:
            return r.fail("total_return is None on real data")
        if result.start_date is None or result.end_date is None:
            return r.fail("start_date/end_date is None on non-empty matrix")
        sharpe_str = f"{result.sharpe_ratio:.2f}" if result.sharpe_ratio is not None else "None"
        dd = result.max_drawdown
        if dd is not None and dd > 0:
            return r.fail(f"max_drawdown should be ≤ 0, got {dd}")
        r.ok(
            f"n_instruments={len(sm.instruments)}, n_trades={result.n_trades}, "
            f"sharpe={sharpe_str}, "
            + (f"dd={dd:.2%}, " if dd is not None else "dd=None, ")
            + f"total_return={result.total_return:.2%}"
        )
    except Exception as e:
        r.fail(f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}")
    return r


def check_5_full_lifecycle(engine: Engine) -> Result:
    r = Result("Full lifecycle synchronously (create → backtest → DB write)")
    portfolio_id_to_cleanup: str | None = None
    try:
        from atlas.simulation.custom.builder import InstrumentWeight, validate_custom_portfolio
        from atlas.simulation.custom.portfolio import (
            _save_portfolio_record,
            run_custom_portfolio_backtest,
        )

        trigger_ids, _start, _end = get_trigger_instruments(engine)
        if len(trigger_ids) < 2:
            return r.fail("need ≥2 instruments with entry triggers; run M5 backfill first")

        weights = [60.0, 40.0] if len(trigger_ids) == 2 else [40.0, 35.0, 25.0]
        instruments = [
            InstrumentWeight(iid, "stock", w)
            for iid, w in zip(trigger_ids[:3], weights, strict=False)
        ]
        validate_custom_portfolio(instruments, engine)
        portfolio_id_str = _save_portfolio_record(
            f"validate_m7_p3_{uuid4().hex[:8]}", instruments, engine
        )
        portfolio_id_to_cleanup = portfolio_id_str

        # Run backtest synchronously (skip ProcessPoolExecutor)
        run_custom_portfolio_backtest(UUID(portfolio_id_str), engine)

        # Verify backtest_id is now populated
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT CAST(backtest_id AS text) FROM atlas.strategy_fm_custom_portfolios WHERE id = CAST(:pid AS uuid)"
                ),
                {"pid": portfolio_id_str},
            ).fetchone()
            if row is None or row[0] is None:
                return r.fail("backtest_id not populated after run_custom_portfolio_backtest")
            backtest_id = row[0]

            br = conn.execute(
                text(
                    "SELECT sharpe_ratio, total_return, start_date, end_date FROM atlas.strategy_backtest_results WHERE id = CAST(:bid AS uuid)"
                ),
                {"bid": backtest_id},
            ).fetchone()
            if br is None:
                return r.fail("backtest result row not found")

        r.ok(f"portfolio={portfolio_id_str[:8]}, backtest={backtest_id[:8]}, sharpe={br[0]}")
    except Exception as e:
        r.fail(f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}")
    finally:
        # Cleanup test data
        if portfolio_id_to_cleanup:
            try:
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            "DELETE FROM atlas.strategy_backtest_results WHERE custom_portfolio_id = CAST(:pid AS uuid)"
                        ),
                        {"pid": portfolio_id_to_cleanup},
                    )
                    conn.execute(
                        text(
                            "DELETE FROM atlas.strategy_fm_custom_portfolios WHERE id = CAST(:pid AS uuid)"
                        ),
                        {"pid": portfolio_id_to_cleanup},
                    )
                    conn.commit()
            except Exception:
                pass  # Cleanup is best-effort
    return r


def check_6_api_e2e(engine: Engine, real_ids: list[str]) -> Result:
    r = Result("API end-to-end (FastAPI TestClient against real DB)")
    portfolio_id: str | None = None
    try:
        from atlas.api.portfolios import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from atlas.db import get_engine as real_get_engine

        app = FastAPI()
        app.include_router(router)
        # Override the dependency to use the real engine (it already would, but make explicit)
        app.dependency_overrides[real_get_engine] = lambda: engine
        client = TestClient(app)

        # POST: create
        body: dict[str, Any] = {
            "name": f"validate_api_e2e_{uuid4().hex[:8]}",
            "instruments": [
                {"instrument_id": real_ids[0], "instrument_type": "stock", "weight_pct": 50.0},
                {"instrument_id": real_ids[1], "instrument_type": "stock", "weight_pct": 50.0},
            ],
        }
        post = client.post("/api/portfolios/custom", json=body)
        if post.status_code != 201:
            return r.fail(f"POST returned {post.status_code}: {post.text}")
        portfolio_id = post.json()["portfolio_id"]
        if post.json()["status"] != "pending":
            return r.fail(f"expected status=pending, got {post.json()}")

        # GET status (should be pending — backtest hasn't completed since ProcessPool is real)
        status = client.get(f"/api/portfolios/custom/{portfolio_id}/status")
        if status.status_code != 200:
            return r.fail(f"GET status returned {status.status_code}: {status.text}")

        # GET detail (will not have backtest yet, but should still 200)
        detail = client.get(f"/api/portfolios/custom/{portfolio_id}")
        if detail.status_code != 200:
            return r.fail(f"GET detail returned {detail.status_code}: {detail.text}")
        if detail.json()["name"] != body["name"]:
            return r.fail(f"detail mismatch: {detail.json()}")

        # LIST
        lst = client.get("/api/portfolios/custom")
        if lst.status_code != 200:
            return r.fail(f"LIST returned {lst.status_code}: {lst.text}")
        if not any(p["id"] == portfolio_id for p in lst.json()):
            return r.fail("created portfolio not in list response")

        # 404
        nf = client.get("/api/portfolios/custom/00000000-0000-0000-0000-000000000000/status")
        if nf.status_code != 404:
            return r.fail(f"unknown ID expected 404, got {nf.status_code}")

        # 422 validation
        bad = client.post(
            "/api/portfolios/custom",
            json={
                "name": "bad",
                "instruments": [
                    {"instrument_id": real_ids[0], "instrument_type": "stock", "weight_pct": 90.0}
                ],
            },
        )
        if bad.status_code != 422:
            return r.fail(f"bad weights expected 422, got {bad.status_code}")

        r.ok("POST 201, GET status 200, GET detail 200, LIST has portfolio, 404+422 correct")
    except Exception as e:
        r.fail(f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}")
    finally:
        # Cleanup
        if portfolio_id:
            try:
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            "DELETE FROM atlas.strategy_backtest_results WHERE custom_portfolio_id = CAST(:pid AS uuid)"
                        ),
                        {"pid": portfolio_id},
                    )
                    conn.execute(
                        text(
                            "DELETE FROM atlas.strategy_fm_custom_portfolios WHERE id = CAST(:pid AS uuid)"
                        ),
                        {"pid": portfolio_id},
                    )
                    conn.commit()
            except Exception:
                pass
    return r


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------


def main() -> int:
    print("=" * 72)
    print("M7 Phase 3 — Custom Portfolio Builder validation")
    print("=" * 72)

    engine = get_engine()
    real_ids = get_real_instruments(engine, n=3)
    if len(real_ids) < 3:
        print(
            f"\n✗ Cannot proceed: need 3 real instruments with prices+decisions; got {len(real_ids)}"
        )
        return 1
    print(f"\nUsing {len(real_ids)} real instruments: {[r[:8] for r in real_ids]}\n")

    results: list[Result] = []
    print("[1/6] schema ...")
    results.append(check_1_schema(engine))
    print(results[-1])
    print("[2/6] universe validation ...")
    results.append(check_2_universe_validation(engine, real_ids))
    print(results[-1])
    print("[3/6] signal matrix ...")
    results.append(check_3_signal_matrix(engine, real_ids))
    print(results[-1])
    print("[4/6] backtest engine ...")
    results.append(check_4_backtest_engine(engine))
    print(results[-1])
    print("[5/6] full lifecycle ...")
    results.append(check_5_full_lifecycle(engine))
    print(results[-1])
    print("[6/6] api e2e ...")
    results.append(check_6_api_e2e(engine, real_ids))
    print(results[-1])

    print("\n" + "=" * 72)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    if passed == total:
        print(f"ALL PASS ({passed}/{total}) — backend is real. SAFE to start frontend.")
        return 0
    else:
        print(f"FAIL ({passed}/{total} passed) — fix before frontend.")
        for r in results:
            if not r.passed:
                print(f"  • {r.name}: {r.error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
