#!/usr/bin/env python3
"""Book and mark the baskets — the record of every ``atlas_global.basket_*`` book.

    python scripts/global_market/mark_baskets.py                         # every active basket, EOD = eod_cutoff()
    python scripts/global_market/mark_baskets.py --eod 2026-09-08 --report m.csv
    python scripts/global_market/mark_baskets.py --only-new              # baskets with no live NAV row yet (the worker)
    python scripts/global_market/mark_baskets.py --basket-id <uuid> --dry-run

Per active basket, in order:

1. INCEPTION, once. A basket with no live trade yet is booked: one BUY per current-version
   constituent at the instrument's last real close on or before the ANCHOR — the latest SPY
   session on or before the EOD (a halted name looks back at most INCEPTION_LOOKBACK_SESSIONS
   sessions; beyond that the basket is refused, never half-booked). Sizing is India's rule
   with a fractional quantum: ``qty = capital × weight ÷ (1 + buy_rate) ÷ price`` rounded
   DOWN to 6 dp (``basket_trades.qty numeric(18,6)``, Alpaca fractional shares), ``value =
   qty × price`` to the cent, ``cost = value × buy_rate``; whatever the rounding and the cost
   reserve leave over stays cash. Every weight and rate comes from ``atlas_thresholds``.
2. MARK, every run, the WHOLE history. NAV rows are a pure function of (trades, bars): the
   series is replayed from the inception session through the anchor and upserted, so a
   re-run for the same EOD writes identical rows, a vendor revision of a bar is honoured,
   and every row sits on ONE price vintage — no seam between an old base and a new one.

THE ENGINE AS A MARKER, NOT A BOOKER. ``atlas.portfolio.engine.replay`` is the one
accounting engine (plan M2: "reuse replay with a fractional quantum"), and it is what values
every row here — driven on its own resume path: ``start_positions`` / ``start_cash`` in, no
events, no inception picks, no stops, so the day-loop does exactly one thing per session:
mark, carrying a suspended name's last price forward. Its inception sizing is NOT used,
because ``engine._qty_for`` rounds a stock or ETF to WHOLE shares (NSE lots) while every
Global basket is fractional; the six lines of sizing above are this script's, tested in
``tests/unit/global_market/test_mark_baskets.py``.

THE MARK PRICE, and why it is a ratio. ``basket_data`` explains the two closes: the fill is
``close_adj`` (the real print, stable until a split) and the mark is that fill grown by
total return since entry, ``p(d) = fill × close_tr[d] / close_tr[entry]`` with both ends read
in this run. A fixed quantity against the absolute ``close_tr`` level would drop every
dividend on its ex-date, because ``ingest_prices`` re-bases the whole history that night.
Where ``close_tr`` is NULL at either end the ratio falls back to ``close_adj`` and the run
says so (report column ``price_basis``, the summary line's ``fallback`` count).

IDEMPOTENT AND RACE-SAFE. The NAV upsert is keyed by ``(basket_id, run_type, date)`` and the
``run_id`` is uuid5 of ``(basket_id, run_type, anchor)`` — the same run mints the same id
(``write_health_snapshot.py``'s rule). Inception is booked inside one transaction that locks
the ``basket_master`` row and re-checks for trades, so the 5-minute worker and the nightly
cannot both book the same basket.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import uuid
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report, basket_data
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package
import _gdb
import basket_data as data
import pandas as pd
from _report import Report
from sqlalchemy import text

from atlas.global_market import calendar as gcal
from atlas.portfolio.engine import PortfolioConfig, replay

M = _gdb.M
RUN_TYPE = data.RUN_TYPE
QTY_QUANTUM = Decimal("0.000001")  # basket_trades.qty numeric(18,6)
MONEY = Decimal("0.01")  # USD, cents
BPS = Decimal(10000)  # basis points per unit
# A constituent must have printed within this many sessions of the anchor to be booked; a
# name silent for longer has no price a basket can honestly form at.
INCEPTION_LOOKBACK_SESSIONS = 5
# Calendar days of bars loaded before the inception session: the fill look-back above, plus
# the engine's carry-forward for a name whose last print precedes the first NAV session.
PANEL_LOOKBACK_DAYS = 14
# Calendar days before the EOD the anchor is looked for in; wider than any exchange closure.
ANCHOR_LOOKBACK_DAYS = 30

# The idempotency namespace: one run (basket, run_type, anchor) always mints the same run_id.
NS = uuid.UUID("9c4a1b2e-5d6f-4e70-8a91-3b2c4d5e6f70")

REPORT_COLUMNS = (
    "basket_id",
    "name",
    "symbol",
    "trade_date",
    "price",
    "price_basis",
    "qty",
    "value",
    "weight",
    "status",
    "detail",
)
BOOKED, MARKED, REFUSED, SKIPPED = "booked", "marked", "refused", "skipped"

INSERT_TRADE_SQL = f"""
INSERT INTO {M}.basket_trades
    (basket_id, run_type, trade_date, asset_class, instrument_id, symbol, side, qty, price,
     value, cost, reason, run_id, rationale, version)
VALUES (CAST(:basket_id AS uuid), :run_type, :trade_date, :asset_class,
        CAST(:instrument_id AS uuid), :symbol, 'buy', :qty, :price, :value, :cost,
        'inception', CAST(:run_id AS uuid), :rationale, :version)
"""
LOCK_SQL = f"SELECT 1 FROM {M}.basket_master WHERE basket_id = CAST(:b AS uuid) FOR UPDATE"
COUNT_TRADES_SQL = (
    f"SELECT count(*) FROM {M}.basket_trades WHERE basket_id = CAST(:b AS uuid) AND run_type = :r"
)
SET_INCEPTION_SQL = f"""
UPDATE {M}.basket_master SET inception_date = :d, updated_at = now()
WHERE basket_id = CAST(:b AS uuid) AND inception_date IS DISTINCT FROM :d
"""


@dataclass(frozen=True)
class Fill:
    """One inception buy — what ``basket_trades`` stores, plus the weight it was sized to."""

    instrument_id: str
    symbol: str
    asset_class: str
    trade_date: dt.date
    price: Decimal
    price_basis: str  # 'close_adj' (the rule) | 'close_tr' (the archive-only fallback)
    weight: Decimal
    qty: Decimal
    value: Decimal
    cost: Decimal


class RefusedError(Exception):
    """A basket this run cannot book or mark honestly — reported, never half-written."""


def run_id(basket_id: str, run_type: str, anchor: dt.date) -> str:
    """Deterministic per (basket, run_type, anchor): the idempotency key of every row a run writes."""
    return str(uuid.uuid5(NS, f"{basket_id}\t{run_type}\t{anchor.isoformat()}"))


# ── pure accounting ──────────────────────────────────────────────────────────


def rate_from_bps(bps: Decimal) -> Decimal:
    return Decimal(bps) / BPS


def size_fill(
    capital: Decimal, weight: Decimal, price: Decimal, buy_rate: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """``(qty, value, cost)`` for one constituent: its weight of capital, the buy cost reserved
    (engine ``_enter`` does the same), fractional shares rounded DOWN to the 6-dp quantum."""
    alloc = Decimal(capital) * Decimal(weight)
    qty = (alloc / (Decimal(1) + buy_rate) / Decimal(price)).quantize(
        QTY_QUANTUM, rounding=ROUND_DOWN
    )
    value = (qty * Decimal(price)).quantize(MONEY)
    cost = (value * buy_rate).quantize(MONEY)
    return qty, value, cost


def cash_after(capital: Decimal, fills: list[Fill]) -> Decimal:
    """What inception leaves in cash: capital − Σ(value + cost), to the cent."""
    return (Decimal(capital) - sum((f.value + f.cost for f in fills), Decimal(0))).quantize(MONEY)


def check_constituents(cons: pd.DataFrame, th: dict[str, Decimal]) -> list[str]:
    """Why a constituent set cannot be booked: empty, an inactive name, weights not summing to
    1, a weight over the position cap or under the floor. Empty list = bookable."""
    if cons.empty:
        return ["no constituents for the current version"]
    problems: list[str] = []
    cap, floor = th["basket_max_position_pct"], th["basket_min_weight_frac"]
    total = Decimal(0)
    for r in cons.to_dict("records"):
        w = Decimal(str(r["target_weight_frac"]))
        total += w
        if not r["is_active"]:
            problems.append(f"{r['symbol']}: instrument is not active")
        if w > cap:
            problems.append(f"{r['symbol']}: weight {w} exceeds basket_max_position_pct {cap}")
        if w < floor:
            problems.append(f"{r['symbol']}: weight {w} is below basket_min_weight_frac {floor}")
    if total != 1:
        problems.append(f"weights sum to {total}, not 1")
    return problems


def _price_of(bar: tuple[Any, Any]) -> tuple[Decimal, str] | None:
    """A bar's fill price and which series it is: ``close_adj`` when present, else the
    archive's ``close_tr``, else nothing (a bar with neither is not a print)."""
    adj, tr = bar
    if adj is not None:
        return Decimal(str(adj)), "close_adj"
    if tr is not None:
        return Decimal(str(tr)), "close_tr"
    return None


def bars_by_key(bars: pd.DataFrame) -> dict[tuple[str, dt.date], tuple[Any, Any]]:
    return {
        (r["instrument_id"], r["date"]): (r["close_adj"], r["close_tr"])
        for r in bars.to_dict("records")
    }


def last_print(
    keyed: dict[tuple[str, dt.date], tuple[Any, Any]],
    instrument_id: str,
    cal: list[dt.date],
    anchor: dt.date,
) -> tuple[dt.date, Decimal, str] | None:
    """The instrument's last real print within INCEPTION_LOOKBACK_SESSIONS sessions ending at
    the anchor (inclusive): ``(date, price, basis)`` or ``None``."""
    i = cal.index(anchor)
    for d in reversed(cal[max(0, i - INCEPTION_LOOKBACK_SESSIONS + 1) : i + 1]):
        bar = keyed.get((instrument_id, d))
        priced = _price_of(bar) if bar is not None else None
        if priced is not None:
            return d, priced[0], priced[1]
    return None


def inception_fills(
    capital: Decimal,
    cons: pd.DataFrame,
    keyed: dict[tuple[str, dt.date], tuple[Any, Any]],
    cal: list[dt.date],
    anchor: dt.date,
    buy_rate: Decimal,
) -> list[Fill]:
    """One Fill per constituent at its last print on or before the anchor. Raises RefusedError,
    naming every missing print, rather than booking part of a basket."""
    fills: list[Fill] = []
    problems: list[str] = []
    for r in cons.to_dict("records"):
        found = last_print(keyed, r["instrument_id"], cal, anchor)
        if found is None:
            problems.append(
                f"{r['symbol']}: no print within {INCEPTION_LOOKBACK_SESSIONS} sessions of {anchor}"
            )
            continue
        d, price, basis = found
        weight = Decimal(str(r["target_weight_frac"]))
        qty, value, cost = size_fill(capital, weight, price, buy_rate)
        if qty <= 0:
            problems.append(f"{r['symbol']}: {weight} of {capital} buys nothing at {price}")
            continue
        fills.append(
            Fill(
                instrument_id=r["instrument_id"],
                symbol=str(r["symbol"]),
                asset_class=str(r["asset_class"]),
                trade_date=d,
                price=price,
                price_basis=basis,
                weight=weight,
                qty=qty,
                value=value,
                cost=cost,
            )
        )
    if problems:
        raise RefusedError("; ".join(problems))
    return fills


def mark_panel(
    fills: list[Fill],
    keyed: dict[tuple[str, dt.date], tuple[Any, Any]],
    index: list[dt.date],
) -> tuple[pd.DataFrame, list[tuple[str, dt.date]]]:
    """The engine's price panel: one Decimal column per held instrument, ``None`` where the
    session had no print (the engine carries the last mark forward). Each value is the fill
    grown by total return since entry — see the module docstring — and every session valued
    on the ``close_adj`` fallback is returned as evidence."""
    cols: dict[str, list[Decimal | None]] = {}
    fallback: list[tuple[str, dt.date]] = []
    for f in fills:
        entry = keyed.get((f.instrument_id, f.trade_date))
        if entry is None or (entry[0] is None and entry[1] is None):
            raise RefusedError(f"{f.symbol}: no bar on its own trade date {f.trade_date}")
        adj0, tr0 = entry
        series: list[Decimal | None] = []
        for d in index:
            bar = keyed.get((f.instrument_id, d))
            if bar is None:
                series.append(None)
                continue
            adj, tr = bar
            if tr0 is not None and tr is not None:
                series.append(f.price * Decimal(str(tr)) / Decimal(str(tr0)))
            elif adj0 is not None and adj is not None:
                series.append(f.price * Decimal(str(adj)) / Decimal(str(adj0)))
                fallback.append((f.symbol, d))
            else:
                series.append(None)
        cols[f.instrument_id] = series
    return pd.DataFrame(cols, index=pd.Index(index), dtype=object), fallback


def replay_navs(
    basket_id: str,
    capital: Decimal,
    max_position_pct: Decimal,
    panel: pd.DataFrame,
    fills: list[Fill],
    cash: Decimal,
    loop_dates: list[dt.date],
) -> pd.DataFrame:
    """``replay`` as a pure marker: positions and cash in, one NAV row per loop date out."""
    cfg = PortfolioConfig(
        portfolio_id=basket_id,
        kind="basket",
        initial_capital=Decimal(capital),
        max_position_pct=Decimal(max_position_pct),
    )
    trades, navs = replay(
        cfg,
        prices=panel,
        events=None,
        inception_state=None,
        composite=None,
        asset_class={f.instrument_id: f.asset_class for f in fills},
        symbols={f.instrument_id: f.symbol for f in fills},
        start_positions={f.instrument_id: f.qty for f in fills},
        start_cash=Decimal(cash),
        loop_dates=loop_dates,
    )
    if not trades.empty:  # the marker booked nothing, by construction
        raise RefusedError(
            f"replay booked {len(trades)} trade(s) while marking — refusing to write"
        )
    return navs


# ── writers ──────────────────────────────────────────────────────────────────


def rationale(f: Fill, capital: Decimal) -> str:
    return (
        f"FM basket pick at inception, sized to its target weight of {f.weight * 100:.2f} percent "
        f"of ${capital:,.2f} capital at the last session close ({f.price_basis})."
    )


def write_inception(
    basket_id: str, version: int, fills: list[Fill], rid: str, anchor: dt.date, capital: Decimal
) -> bool:
    """Insert the inception trades and stamp the inception date, in ONE transaction that locks
    the basket row and re-checks for trades — so two markers cannot both book. Returns False
    when the other one already had."""
    with _gdb.engine().begin() as conn:
        conn.execute(text(LOCK_SQL), {"b": basket_id})
        n = conn.execute(text(COUNT_TRADES_SQL), {"b": basket_id, "r": RUN_TYPE}).scalar()
        if n:
            return False
        conn.execute(
            text(INSERT_TRADE_SQL),
            [
                {
                    "basket_id": basket_id,
                    "run_type": RUN_TYPE,
                    "trade_date": f.trade_date,
                    "asset_class": f.asset_class,
                    "instrument_id": f.instrument_id,
                    "symbol": f.symbol,
                    "qty": f.qty,
                    "price": f.price,
                    "value": f.value,
                    "cost": f.cost,
                    "run_id": rid,
                    "rationale": rationale(f, capital),
                    "version": int(version),
                }
                for f in fills
            ],
        )
        conn.execute(text(SET_INCEPTION_SQL), {"b": basket_id, "d": anchor})
    return True


def write_navs(basket_id: str, navs: pd.DataFrame, rid: str) -> int:
    df = navs.copy()
    df["basket_id"], df["run_type"], df["run_id"] = basket_id, RUN_TYPE, rid
    df["computed_at"] = dt.datetime.now(ZoneInfo(gcal.NEW_YORK))
    return _gdb.upsert_df(f"{M}.basket_nav_daily", df, ["basket_id", "run_type", "date"])


# ── one basket ───────────────────────────────────────────────────────────────


def fills_from_trades(tr: pd.DataFrame) -> list[Fill]:
    """The stored book as Fills (what the marker needs of a trade). Only inception buys are
    understood here: a later version, a rebalance or a sell needs the versioning work."""
    other = tr.loc[(tr["reason"] != "inception") | (tr["side"] != "buy")]
    if not other.empty:
        raise RefusedError(
            f"{len(other)} non-inception trade(s) on the book — marking a rebalanced book is "
            "not built yet (basket versioning)"
        )
    return [
        Fill(
            instrument_id=str(r["instrument_id"]),
            symbol=str(r["symbol"]),
            asset_class=str(r["asset_class"]),
            trade_date=r["trade_date"],
            price=Decimal(str(r["price"])),
            price_basis="stored",
            weight=Decimal(0),
            qty=Decimal(str(r["qty"])),
            value=Decimal(str(r["value"])),
            cost=Decimal(str(r["cost"])) if r["cost"] is not None else Decimal(0),
        )
        for r in tr.to_dict("records")
    ]


def mark_basket(
    b: dict[str, Any], eod: dt.date, th: dict[str, Decimal], dry_run: bool, report: Report | None
) -> str:
    """Book (if needed) and mark one basket through the EOD; returns the outcome word."""
    basket_id, name, version = str(b["basket_id"]), str(b["name"]), int(b["current_version"])
    tag = f"[baskets] {name} ({basket_id[:8]})"

    def note(status: str, detail: str, f: Fill | None = None) -> None:
        if report is not None:
            report.add(
                basket_id,
                name,
                f.symbol if f else None,
                f.trade_date if f else None,
                f.price if f else None,
                f.price_basis if f else None,
                f.qty if f else None,
                f.value if f else None,
                f.weight if f else None,
                status,
                detail,
            )

    try:
        if b["initial_capital"] is None:
            raise RefusedError("initial_capital is NULL")
        capital = Decimal(str(b["initial_capital"]))
        cons = data.constituents(basket_id, version)
        problems = check_constituents(cons, th)
        if problems:
            raise RefusedError("; ".join(problems))
        recent = data.sessions(eod - dt.timedelta(days=ANCHOR_LOOKBACK_DAYS), eod)
        anchor = gcal.latest_session_on_or_before(recent, eod)
        if anchor is None:
            raise RefusedError(f"no SPY session within {ANCHOR_LOOKBACK_DAYS} days of {eod}")
        tr = data.trades(basket_id)
        booked = 0
        if tr.empty:
            inception = anchor
        else:
            inception = b["inception_date"] or min(tr["trade_date"])
        since = min(inception, anchor) - dt.timedelta(days=PANEL_LOOKBACK_DAYS)
        cal = data.sessions(since, anchor)
        ids = cons["instrument_id"].tolist() + ([] if tr.empty else tr["instrument_id"].tolist())
        keyed = bars_by_key(data.bars(sorted(set(ids)), since, anchor))
        rid = run_id(basket_id, RUN_TYPE, anchor)
        buy_rate = rate_from_bps(th["basket_cost_bps_buy"])
        if tr.empty:
            fills = inception_fills(capital, cons, keyed, cal, anchor, buy_rate)
            if not dry_run and write_inception(basket_id, version, fills, rid, anchor, capital):
                booked = len(fills)
            elif not dry_run:
                # the worker and the nightly met on this basket; the other one booked it
                fills = fills_from_trades(data.trades(basket_id))
            else:
                booked = len(fills)
            for f in fills:
                note(BOOKED, f"{f.weight * 100:.2f} percent at {f.price_basis}", f)
            cash = cash_after(capital, fills)
        else:
            fills = fills_from_trades(tr)
            cash = data.cash_from_trades(capital, tr)
        loop = [d for d in cal if inception <= d <= anchor]
        if not loop:
            raise RefusedError(f"no SPY session between inception {inception} and anchor {anchor}")
        panel, fallback = mark_panel(fills, keyed, cal)
        navs = replay_navs(
            basket_id, capital, th["basket_max_position_pct"], panel, fills, cash, loop
        )
        written = 0 if dry_run else write_navs(basket_id, navs, rid)
        last = navs.iloc[-1]
        fb = f"{len(fallback)} session-name(s) on close_adj" if fallback else "none"
        print(
            f"{tag}: {'booked ' + str(booked) + ' inception fill(s) at ' + str(anchor) + '; ' if booked else ''}"
            f"marked {len(navs)} NAV row(s) {loop[0]}→{loop[-1]} nav=${Decimal(last['nav']):,.2f} "
            f"cash=${Decimal(last['cash']):,.2f} n={int(last['n_positions'])}; close_tr fallback: {fb}"
            f"{' [dry-run: nothing written]' if dry_run else f' [{written} row(s) upserted]'}",
            flush=True,
        )
        note(
            MARKED, f"{len(navs)} NAV rows {loop[0]}..{loop[-1]}; fallback sessions {len(fallback)}"
        )
        return MARKED
    except RefusedError as e:
        print(f"{tag}: REFUSED — {e}", flush=True)
        note(REFUSED, str(e))
        return REFUSED


def run(
    eod: dt.date,
    basket_ids: list[str] | None,
    only_new: bool,
    dry_run: bool,
    report: Report | None,
) -> int:
    """Mark the selected baskets; exit 1 if any was refused (the others are still written)."""
    th = data.thresholds()
    baskets = data.active_baskets()
    if only_new:
        wanted = set(data.unmarked_basket_ids())
        baskets = baskets.loc[baskets["basket_id"].isin(list(wanted))]
    if basket_ids:
        baskets = baskets.loc[baskets["basket_id"].isin(list(set(basket_ids)))]
    if baskets.empty:
        print(f"[baskets] EOD={eod}: no active basket to mark", flush=True)
        return 0
    outcomes = [mark_basket(b, eod, th, dry_run, report) for b in baskets.to_dict("records")]
    refused = outcomes.count(REFUSED)
    print(
        f"[baskets] EOD={eod} COMPLETE marked={outcomes.count(MARKED)} refused={refused}"
        f"{' (dry-run)' if dry_run else ''}",
        flush=True,
    )
    return 1 if refused else 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None)
    ap.add_argument(
        "--basket-id", action="append", default=None, help="only this basket (repeatable)"
    )
    ap.add_argument(
        "--only-new", action="store_true", help="only baskets with no live NAV row (the worker)"
    )
    ap.add_argument("--dry-run", action="store_true", help="compute and print, write nothing")
    ap.add_argument(
        "--report", type=Path, default=None, help="per-fill CSV: what was booked and why"
    )
    return ap


def main() -> int:
    args = parser().parse_args()
    eod = args.eod or _gdb.eod_cutoff()
    report = Report(args.report, REPORT_COLUMNS) if args.report else None
    try:
        return run(eod, args.basket_id, args.only_new, args.dry_run, report)
    finally:
        if report is not None:
            report.close()


if __name__ == "__main__":
    sys.exit(main())
