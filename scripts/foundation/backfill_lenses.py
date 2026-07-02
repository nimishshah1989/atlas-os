#!/usr/bin/env python3
"""Chunked, resumable POINT-IN-TIME rebuild of atlas.atlas_lens_scores_daily (Loop C).

Scores the six lenses for every NSE session in [start, end] using ONLY information
knowable on each date — the Loop C journal rebuild (D5/D8/D16). Architecture, for
the shared box (GUARDRAILS §5 — be a good neighbour, never load all in memory):

  • Sessions are split into contiguous CHUNKS, distributed over ≤6 workers.
  • Each worker loads its chunk's panels ONCE (ohlcv + technical_daily date-range,
    all financials, flow/catalyst over the chunk±lookback) instead of re-querying
    per date — so ohlcv is range-scanned a handful of times, not 1,850× full-scanned.
  • Per date it slices those panels in memory and calls the SAME scoring core the
    nightly pipeline uses (atlas.lenses.pipeline.score_all) — identical PIT output.
  • Resumable via a small state file: completed dates are skipped on restart; each
    date is upserted then stale rows for that date purged, so re-running replaces
    the old (leaky) journal day cleanly.

    python backfill_lenses.py --start 2019-01-01 --workers 6 --chunk-days 45
    python backfill_lenses.py --validate-date 2026-06-19   # chunk-path vs run_pipeline
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import _db  # noqa: E402

START = date(2019, 1, 1)
STATE_FILE = Path(__file__).parent / ".loopC_rebuild_state.json"


def _sessions(start: date, end: date) -> list[date]:
    df = _db.read_df(
        "SELECT DISTINCT date FROM atlas_foundation.index_prices "
        "WHERE index_code='NIFTY 50' AND date>=:s AND date<=:e ORDER BY date",
        {"s": start, "e": end},
    )
    return [d.date() if hasattr(d, "date") else d for d in df["date"].tolist()]


def _load_done() -> set[str]:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()).get("done", []))
        except Exception:
            return set()
    return set()


def _mark_done(new_dates: list[str]) -> None:
    done = _load_done() | set(new_dates)
    STATE_FILE.write_text(json.dumps({"done": sorted(done)}))


def _chunks(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _process_chunk(chunk_dates: list[date]) -> dict:
    """Score every date in *chunk_dates* from preloaded panels. Runs in a worker."""
    from decimal import Decimal

    import pandas as pd

    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from atlas.db import get_engine, load_thresholds
    from atlas.lenses.compute.fundamental_pit import (
        build_fundamental_steps,
        fundamental_asof_from_steps,
    )
    from atlas.lenses.compute.thresholds_view import nest_thresholds
    from atlas.lenses.data.adapters import (
        REPORTING_LAG_A,
        REPORTING_LAG_Q,
        load_instrument_sectors,
        load_policy_registry,
        purge_stale_lens_scores,
        write_lens_scores,
    )
    from atlas.lenses.pipeline import score_all

    eng = get_engine()
    th = nest_thresholds(
        {
            k: (float(v) if isinstance(v, Decimal) else v)
            for k, v in load_thresholds(engine=eng).items()
        }
    )
    cstart, cend = chunk_dates[0], chunk_dates[-1]
    look = cstart - timedelta(days=365)

    def rd(sql, p):
        return _db.read_df(sql, p)

    techd = rd(
        """SELECT t.instrument_id, t.symbol, t.asset_class, t.ema_21, t.ema_50, t.ema_200,
                    t.rsi_14, t.ret_1w, t.rs_1m_n500, t.rs_3m_n500, t.rs_6m_n500, t.rs_12m_n500,
                    t.rs_1m_sector, t.rs_3m_sector, t.rs_6m_sector, t.rs_12m_sector,
                    t.atr_14, t.bb_width, t.vol_ratio_30d, t.vol_ratio_60d, t.pos_52w,
                    d.delivery_pct, d.delivery_avg_30d, d.delivery_avg_60d,
                    d.delivery_trend, d.delivery_updown_asym, t.date
                  FROM atlas_foundation.technical_daily t
                  LEFT JOIN atlas_foundation.delivery_daily d
                    ON d.instrument_id = t.instrument_id AND d.date = t.date
                  WHERE t.date BETWEEN :s AND :e""",
        {"s": cstart, "e": cend},
    )
    ohlcv = rd(
        """SELECT instrument_id, date, close_adj, close, volume
                  FROM atlas_foundation.ohlcv_stock WHERE date BETWEEN :s AND :e""",
        {"s": cstart, "e": cend},
    )
    fq = rd(
        """SELECT instrument_id, period_end, consolidated, revenue, ebit, pat, eps,
                 net_margin, finance_costs, debt_equity_ratio
               FROM atlas_foundation.financials_quarterly WHERE period_end <= :e""",
        {"e": cend},
    )
    fa = rd(
        """SELECT instrument_id, period_end, consolidated, equity, total_borrowings
               FROM atlas_foundation.financials_annual
               WHERE period_end <= :e AND equity IS NOT NULL""",
        {"e": cend},
    )
    insider = rd(
        """SELECT instrument_id, symbol, signal_type, value_cr, person_name,
                      pledge_pct_after, transaction_date, price_per_share
                    FROM atlas_foundation.lens_insider
                    WHERE transaction_date BETWEEN :l AND :e""",
        {"l": look, "e": cend},
    )
    sh = rd(
        """SELECT instrument_id, symbol, period_end, promoter_pct, public_pct
               FROM atlas_foundation.lens_shareholding WHERE period_end <= :e""",
        {"e": cend},
    )
    bulk = rd(
        """SELECT instrument_id, symbol, deal_date, client_name, buy_sell, qty, price,
                   is_institutional, is_superstar, superstar_name
                 FROM atlas_foundation.lens_bulk_deals
                 WHERE deal_date BETWEEN :l AND :e""",
        {"l": cstart - timedelta(days=90), "e": cend},
    )
    filings = rd(
        """SELECT instrument_id, symbol, filing_date, category, category_bucket,
                      signal_priority, subject_text, source_url
                    FROM atlas_foundation.lens_filings
                    WHERE filing_date BETWEEN :l AND :e""",
        {"l": look, "e": cend},
    )
    sectors = load_instrument_sectors(eng)
    policies = load_policy_registry(eng)

    # normalise date columns to date objects for fast equality slicing
    for frame, col in (
        (techd, "date"),
        (ohlcv, "date"),
        (insider, "transaction_date"),
        (sh, "period_end"),
        (bulk, "deal_date"),
        (filings, "filing_date"),
    ):
        if not frame.empty:
            frame[col] = pd.to_datetime(frame[col]).dt.date

    # fundamental step functions (built once for the whole chunk)
    qby: dict = {}
    for r in fq.to_dict("records"):
        qby.setdefault(r["instrument_id"], []).append(r)
    aby: dict = {}
    for r in fa.to_dict("records"):
        aby.setdefault(r["instrument_id"], []).append(r)
    steps = build_fundamental_steps(qby, aby, REPORTING_LAG_Q, REPORTING_LAG_A)
    fund_iids = list(steps.keys())

    ohlcv_cols = ["instrument_id", "close_adj", "close", "volume"]
    done, total_scored = [], 0
    for dt in chunk_dates:
        td = techd[techd["date"] == dt]
        if td.empty:
            done.append(str(dt))
            continue
        ov = ohlcv[ohlcv["date"] == dt][ohlcv_cols]
        tech_df = td.drop(columns=["date"]).merge(ov, on="instrument_id", how="left")
        tech_df["price_adj"] = tech_df["close_adj"].where(
            tech_df["close_adj"].notna() & (tech_df["close_adj"] > 0), tech_df["close"]
        )
        tech_df["close_raw"] = tech_df["close"]

        fund_rows = [
            r
            for r in (fundamental_asof_from_steps(steps, iid, dt) for iid in fund_iids)
            if r is not None
        ]
        fund_df = pd.DataFrame(fund_rows) if fund_rows else pd.DataFrame()

        # Inclusive lower bounds to match the nightly adapters exactly
        # (load_catalyst_data / load_flow_data use filing_date >= as_of − lookback).
        cat_df = filings[
            (filings["filing_date"] >= dt - timedelta(days=365)) & (filings["filing_date"] <= dt)
        ]
        flow_data = {
            "insider": insider[
                (insider["transaction_date"] >= dt - timedelta(days=365))
                & (insider["transaction_date"] <= dt)
            ],
            "shareholding": sh[sh["period_end"] <= dt],
            "bulk_deals": bulk[
                (bulk["deal_date"] >= dt - timedelta(days=90)) & (bulk["deal_date"] <= dt)
            ],
        }

        rid = uuid.uuid4()
        results, scored, _ = score_all(
            dt, tech_df, fund_df, cat_df, flow_data, sectors, policies, th, rid
        )
        write_lens_scores(eng, results, rid)
        if scored > 0:
            purge_stale_lens_scores(eng, dt, rid, asset_class="stock")
        total_scored += scored
        done.append(str(dt))

    return {"start": str(cstart), "end": str(cend), "dates": done, "scored": total_scored}


def _validate_date(d: date) -> None:
    """Score one date via the chunk path and via run_pipeline's adapters; compare."""
    import pandas as pd

    from atlas.db import get_engine

    eng = get_engine()
    # chunk path writes to the journal; capture before/after by reading the row set
    res = _process_chunk([d])
    print(f"chunk path: scored {res['scored']} for {d}")
    after = _db.read_df(
        "SELECT instrument_id, technical, fundamental, valuation, catalyst, flow, composite "
        "FROM atlas.atlas_lens_scores_daily WHERE date=:d AND asset_class='stock'",
        {"d": d},
    )
    # independent recompute via the nightly adapters + score_all
    from decimal import Decimal

    from atlas.db import load_thresholds
    from atlas.lenses.compute.thresholds_view import nest_thresholds
    from atlas.lenses.data import adapters
    from atlas.lenses.pipeline import score_all

    th = nest_thresholds(
        {
            k: (float(v) if isinstance(v, Decimal) else v)
            for k, v in load_thresholds(engine=eng).items()
        }
    )
    tech = adapters.load_technical_data(eng, d)
    fund = adapters.load_fundamental_data(eng, d)
    cat = adapters.load_catalyst_data(eng, as_of=d)
    flow = adapters.load_flow_data(eng, as_of=d)
    sec = adapters.load_instrument_sectors(eng)
    pol = adapters.load_policy_registry(eng)
    results, _, _ = score_all(d, tech, fund, cat, flow, sec, pol, th, uuid.uuid4())
    ref = pd.DataFrame(results).set_index("instrument_id")
    a = after.set_index("instrument_id")
    common = a.index.intersection(ref.index)
    mism = 0
    for lens in ["technical", "fundamental", "valuation", "catalyst", "flow", "composite"]:
        x = pd.to_numeric(a.loc[common, lens], errors="coerce")
        y = pd.to_numeric(ref.loc[common, lens], errors="coerce")
        d_ = (x - y).abs()
        bad = int((d_ > 0.1).sum())
        mism += bad
        print(f"  {lens:12s} mismatches>0.1: {bad}/{len(common)}")
    print(
        "VALIDATION",
        "PASS — chunk path == run_pipeline adapters" if mism == 0 else f"FAIL ({mism})",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, default=START)
    ap.add_argument("--end", type=date.fromisoformat, default=None)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--chunk-days", type=int, default=45)
    ap.add_argument("--validate-date", type=date.fromisoformat, default=None)
    ap.add_argument("--reset-state", action="store_true")
    args = ap.parse_args()

    if args.validate_date:
        _validate_date(args.validate_date)
        return
    if args.reset_state and STATE_FILE.exists():
        STATE_FILE.unlink()

    end = args.end or _db.scalar(
        "SELECT max(date) FROM atlas_foundation.index_prices WHERE index_code='NIFTY 50'"
    )
    if hasattr(end, "date"):
        end = end.date()
    workers = min(args.workers, 6)

    all_sessions = _sessions(args.start, end)
    done = _load_done()
    todo = [d for d in all_sessions if str(d) not in done]
    print(
        f"Rebuild {args.start}→{end}: {len(all_sessions)} sessions, "
        f"{len(done)} done, {len(todo)} remaining, workers={workers}"
    )
    if not todo:
        print("Nothing to do.")
        return

    chunks = _chunks(todo, args.chunk_days)
    print(f"{len(chunks)} chunks of ≤{args.chunk_days} days")
    t0 = time.time()
    completed = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_process_chunk, c): c for c in chunks}
        for fut in as_completed(futs):
            c = futs[fut]
            try:
                r = fut.result()
                _mark_done(r["dates"])
                completed += len(r["dates"])
                rate = completed / (time.time() - t0) * 60
                print(
                    f"  chunk {r['start']}→{r['end']}: {len(r['dates'])} dates, "
                    f"scored~{r['scored']} ({rate:.0f} dates/min, {completed}/{len(todo)})"
                )
            except Exception as e:
                print(f"  [FAIL] chunk {c[0]}→{c[-1]}: {e!r}", file=sys.stderr)
    print(f"\nDone: {completed} dates in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
