#!/usr/bin/env python3
"""Pull the three MaaL books out of the CPP database into atlas_foundation.

Reads (read-only, via MAAL_SOURCE_DB_URL): cpp_portfolios, cpp_holdings,
cpp_transactions, cpp_nav_series.
Writes: maal_holding_snapshot, portfolio_nav_daily (run_type='live'),
portfolio_trades + maal_trade_link.

Positions are snapshotted per day and never overwritten, so the series IS the
change log. Prices are NOT taken from CPP — Atlas marks positions with its own
NSE close. CPP is the source of WHAT is held and at what cost, not of what it is
worth: CPP's own weight_pct divides by invested value alone, so its weights always
sum to 100 and cash reads 0%.

Run: PYTHONPATH=<repo>:<repo>/scripts/foundation python sync_maal_books.py [--as-of YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from collections import defaultdict
from decimal import Decimal
from typing import Any

import _db
import pandas as pd
from sqlalchemy import create_engine, text

from atlas.maal.fifo import match_fifo
from atlas.maal.source import (
    CODE_BY_CLIENT_CODE,
    split_cash_and_positions,
    trade_from_txn,
)

log = logging.getLogger("sync_maal_books")

# A HUNG sync is worse than a failed one: cron fires again in twelve hours and now
# two processes are stuck on the box that also serves production, with nothing in any
# log. Both timeouts are deliberately generous — the whole pull is ~2,000 rows for
# these three books, so anything past a minute means CPP is wedged, not busy.
_CONNECT_TIMEOUT_S = 15
_STATEMENT_TIMEOUT_MS = 60_000

_IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _source_engine():
    url = os.environ.get("MAAL_SOURCE_DB_URL", "").strip()
    if not url:
        raise SystemExit("MAAL_SOURCE_DB_URL is not set — see docs/maal-process.md")
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": _CONNECT_TIMEOUT_S,
            "options": f"-c statement_timeout={_STATEMENT_TIMEOUT_MS}",
        },
    )


def _rows(conn, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Query -> list of plain dicts, with postgres `numeric` preserved as Decimal."""
    return [dict(m) for m in conn.execute(text(sql), params).mappings()]


def _pick(rows: list[dict[str, Any]], client_code: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["client_code"] == client_code]


def _fetch_source(engine, codes: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Holdings, the latest NAV row, and every transaction for the three UCCs.

    Rows come back as plain dicts via SQLAlchemy, NOT through pandas.read_sql, which
    coerces postgres `numeric` to float64 — quantities, prices and costs would silently
    become binary floats and every downstream Decimal arithmetic would either raise or,
    worse, drift. psycopg2 hands back real Decimals; keeping them is the whole point.

    Every query filters on client_code. The source tables hold ~221k transactions and
    ~401k NAV rows across all ~372 portfolios; an unfiltered pull is a different order
    of magnitude from the ~2,000 rows these three books actually contain.
    """
    p = {"codes": codes}
    with engine.connect() as conn:
        holdings = _rows(
            conn,
            """
            SELECT p.client_code, h.symbol, h.isin, h.asset_class,
                   h.quantity, h.avg_cost
            FROM cpp_holdings h
            JOIN cpp_portfolios p ON p.id = h.portfolio_id
            WHERE p.client_code = ANY(:codes) AND h.quantity > 0
              AND h.isin IS NOT NULL
        """,
            p,
        )
        nav = _rows(
            conn,
            """
            SELECT DISTINCT ON (p.client_code)
                   p.client_code, n.nav_date, n.current_value,
                   n.invested_amount, n.cash_value, n.bank_balance, n.etf_value
            FROM cpp_nav_series n
            JOIN cpp_portfolios p ON p.id = n.portfolio_id
            WHERE p.client_code = ANY(:codes)
            ORDER BY p.client_code, n.nav_date DESC
        """,
            p,
        )
        # FIFO needs an instrument's WHOLE history to know the cost basis of the lots
        # a sell consumes, so this is deliberately not incremental.
        txns = _rows(
            conn,
            """
            SELECT t.id, p.client_code, t.txn_date, t.txn_type, t.symbol,
                   t.isin, t.quantity, t.price, t.cost_rate, t.amount
            FROM cpp_transactions t
            JOIN cpp_portfolios p ON p.id = t.portfolio_id
            WHERE p.client_code = ANY(:codes) AND NOT t.is_deleted
              AND t.isin IS NOT NULL
              AND t.quantity IS NOT NULL AND t.price IS NOT NULL
            ORDER BY p.client_code, t.isin, t.txn_date, t.id
        """,
            p,
        )
    return {"holdings": holdings, "nav": nav, "txns": txns}


def _resolve_isins(isins: list[str]) -> dict[str, tuple[str, str, str]]:
    """ISIN -> (instrument_id UUID, asset_class, symbol). Missing ISINs are absent.

    The UUID is what portfolio_trades.instrument_key holds — the engine's existing
    convention, and the portfolio detail page casts that column with ::uuid[]. The
    readable "stock:SYMBOL" form belongs only in maal_holding_snapshot, which is
    our own table and feeds the book UI.
    """
    if not isins:
        return {}
    df = _db.read_df(
        """
        SELECT isin, instrument_id::text AS iid, symbol, asset_class
        FROM atlas_foundation.instrument_master
        WHERE isin = ANY(CAST(:isins AS text[]))
        """,
        {"isins": isins},
    )
    return {
        str(i): (str(u), str(a), str(s))
        for i, u, s, a in zip(df["isin"], df["iid"], df["symbol"], df["asset_class"], strict=False)
    }


def _write_trades(rows: list[dict[str, Any]]) -> int:
    """Insert only trades we have never seen, and link them. Returns rows inserted.

    portfolio_trades has no natural key, so idempotency lives in maal_trade_link.
    The insert and the link MUST share one transaction: a crash between them would
    leave an unlinked trade that the next run inserts again, silently doubling the
    book's history.
    """
    if not rows:
        return 0
    known = set(
        _db.read_df("SELECT source_txn_id FROM atlas_foundation.maal_trade_link")["source_txn_id"]
    )
    fresh = [r for r in rows if r["source_txn_id"] not in known]
    log.info("trades: %d already linked, %d new", len(rows) - len(fresh), len(fresh))
    if not fresh:
        return 0

    with _db.engine().begin() as conn:
        for r in fresh:
            payload = dict(r)
            txn_id = payload.pop("source_txn_id")
            trade_id = conn.execute(
                text("""
                    INSERT INTO atlas_foundation.portfolio_trades
                        (portfolio_id, run_type, trade_date, asset_class, instrument_key,
                         symbol, side, qty, price, value, cost, reason,
                         realized_pnl, holding_days, tax_bucket)
                    VALUES (:portfolio_id, :run_type, :trade_date, :asset_class,
                            :instrument_key, :symbol, :side, :qty, :price, :value,
                            :cost, :reason, :realized_pnl, :holding_days, :tax_bucket)
                    RETURNING trade_id
                """),
                payload,
            ).scalar_one()
            conn.execute(
                text("""
                    INSERT INTO atlas_foundation.maal_trade_link (source_txn_id, trade_id)
                    VALUES (:txn_id, :trade_id)
                """),
                {"txn_id": txn_id, "trade_id": trade_id},
            )
    return len(fresh)


def _fifo_by_instrument(txns: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """source_txn_id -> {realized_pnl, holding_days, tax_bucket} for every SELL.

    Matched per (client_code, isin) over the instrument's whole history, because a
    sell's cost basis lives in the buys that preceded it.
    """
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in txns:
        grouped[(t["client_code"], t["isin"])].append(t)

    out: dict[int, dict[str, Any]] = {}
    for rows in grouped.values():
        sells = [r for r in rows if str(r["txn_type"]).strip().upper() == "SELL"]
        results = match_fifo(rows)
        # match_fifo returns one row per SELL in date order; zip back onto the
        # source rows sorted the same way so each result keeps its source id.
        for src, res in zip(
            sorted(sells, key=lambda r: (r["txn_date"], r["id"])), results, strict=False
        ):
            out[src["id"]] = {
                "realized_pnl": res["realized_pnl"],
                "holding_days": res["holding_days"],
                "tax_bucket": res["tax_bucket"],
            }
    return out


def sync(as_of: dt.date) -> int:
    """Returns the count of unresolved CURRENT-HOLDING ISINs — non-zero fails the run."""
    codes = list(CODE_BY_CLIENT_CODE)
    src = _fetch_source(_source_engine(), codes)

    if not src["holdings"]:
        raise SystemExit("CPP returned zero holdings for all three books — refusing to write")

    held_isins = sorted({r["isin"] for r in src["holdings"] if r["isin"]})
    txn_isins = sorted({r["isin"] for r in src["txns"] if r["isin"]})
    resolved = _resolve_isins(sorted(set(held_isins) | set(txn_isins)))

    # Two different failure classes, deliberately not conflated:
    #  - a CURRENT holding we cannot resolve means the Monday book would render an
    #    incomplete portfolio. Fatal.
    #  - an old TRANSACTION we cannot resolve is a delisted or merged name (GDL,
    #    TINPLATE...). Permanent, historical, and no reason to block tonight's sync.
    unresolved_held = [i for i in held_isins if i not in resolved]
    unresolved_txn = [i for i in txn_isins if i not in resolved and i not in held_isins]

    ids = _db.read_df(
        """
        SELECT portfolio_id::text AS portfolio_id, params->>'client_code' AS client_code
        FROM atlas_foundation.portfolio_master
        WHERE params->>'source' = 'cpp'
        """
    )
    pid_by_code = dict(zip(ids["client_code"], ids["portfolio_id"], strict=False))
    if len(pid_by_code) != 3:
        raise SystemExit(f"expected 3 registered CPP books, found {len(pid_by_code)}")

    fifo = _fifo_by_instrument(src["txns"])

    snap_rows: list[dict[str, Any]] = []
    nav_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []

    for client_code, maal_code in CODE_BY_CLIENT_CODE.items():
        pid = pid_by_code[client_code]
        rows = _pick(src["holdings"], client_code)

        # The data's OWN date, not today's. cpp_nav_series.nav_date is CPP's statement
        # of when this portfolio was last valued. Refuse to write a snapshot without it
        # rather than silently stamping today: a book dated Monday that actually holds
        # Thursday's positions is how the desk sells a name that was already sold.
        nav_row = _pick(src["nav"], client_code)
        if not nav_row:
            log.error("no cpp_nav_series row for %s — skipping this book entirely", client_code)
            continue
        n = nav_row[0]
        source_as_of = n["nav_date"]
        if isinstance(source_as_of, pd.Timestamp):
            source_as_of = source_as_of.date()

        positions, _cash_rows = split_cash_and_positions(rows)
        for r in rows:
            key_ac = resolved.get(r["isin"])
            snap_rows.append(
                {
                    "as_of": as_of,
                    "source_as_of": source_as_of,
                    "maal_code": maal_code,
                    "isin": r["isin"],
                    "source_symbol": r["symbol"],
                    # Readable key here on purpose: this is our table, and the book UI
                    # keys positions as "stock:SYMBOL" / "etf:SYMBOL".
                    "instrument_key": f"{key_ac[1]}:{key_ac[2]}" if key_ac else None,
                    "asset_class": r["asset_class"],
                    "quantity": r["quantity"],
                    "avg_cost": r["avg_cost"],
                }
            )

        # Cash = idle balance + bank + the LIQUID-ETF sleeve. etf_value is where CPP
        # keeps the value of LIQUIDBEES / LIQUIDCASE / LIQUIDETF, and the FM's rule is
        # that those ARE cash (2026-07-31). Verified against CPP's own cash_pct on all
        # three books: BJ53 33.29%, BJ53IND 45.26%, JR100PASS 6.45% — reproduced exactly.
        # Omitting etf_value understated JR100PASS's cash as 0.1% against a true 6.45%.
        # GOLDBEES and SILVERBEES are NOT in here: they are asset-class exposure, and
        # CPP classifies them EQUITY, so they stay positions.
        cash = (
            Decimal(str(n["cash_value"] or 0))
            + Decimal(str(n["bank_balance"] or 0))
            + Decimal(str(n["etf_value"] or 0))
        )
        total = Decimal(str(n["current_value"] or 0))
        nav_rows.append(
            {
                "portfolio_id": pid,
                "run_type": "live",
                "date": source_as_of,
                "nav": total,
                "cash": cash,
                "invested": total - cash,
                "n_positions": len(positions),
            }
        )
        lag = (as_of - source_as_of).days
        if lag > 0:
            log.warning(
                "%s data is %d day(s) behind: source_as_of=%s run=%s",
                client_code,
                lag,
                source_as_of,
                as_of,
            )

        for t in _pick(src["txns"], client_code):
            key_ac = resolved.get(t["isin"])
            if key_ac is None:
                continue  # counted in unresolved_txn and reported below
            # UUID here — portfolio_trades.instrument_key is the engine's convention
            # and the detail page casts it ::uuid[].
            trade = trade_from_txn(
                t, instrument_key=key_ac[0], asset_class=key_ac[1], symbol=key_ac[2]
            )
            if trade is None:
                continue
            trade.update(fifo.get(t["id"], {}))
            trade_rows.append(
                {
                    **trade,
                    "portfolio_id": pid,
                    "run_type": "live",
                    "realized_pnl": trade.get("realized_pnl"),
                    "holding_days": trade.get("holding_days"),
                    "tax_bucket": trade.get("tax_bucket"),
                }
            )

    _db.upsert_df(
        "atlas_foundation.maal_holding_snapshot",
        pd.DataFrame(snap_rows),
        ["as_of", "maal_code", "isin"],
    )
    _db.upsert_df(
        "atlas_foundation.portfolio_nav_daily",
        pd.DataFrame(nav_rows),
        ["portfolio_id", "run_type", "date"],
    )
    inserted = _write_trades(trade_rows)

    log.info(
        "as_of=%s snapshot=%d nav=%d trades_new=%d unresolved_held=%d unresolved_txn=%d",
        as_of,
        len(snap_rows),
        len(nav_rows),
        inserted,
        len(unresolved_held),
        len(unresolved_txn),
    )
    if unresolved_txn:
        log.warning(
            "%d historical-only ISIN(s) unresolved (delisted/merged, expected): %s",
            len(unresolved_txn),
            ", ".join(unresolved_txn),
        )
    if unresolved_held:
        log.error(
            "FATAL — %d CURRENT holding ISIN(s) not in instrument_master: %s. "
            "Run scripts/foundation/build_universe.py, then re-run this sync.",
            len(unresolved_held),
            ", ".join(unresolved_held),
        )
    return len(unresolved_held)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD, defaults to today IST")
    args = ap.parse_args()
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.datetime.now(_IST).date()
    return 0 if sync(as_of) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
