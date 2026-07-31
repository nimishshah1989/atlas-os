#!/usr/bin/env python3
"""Intraday crossover monitor (spec §C) — the PROVISIONAL and 15:15 stages.

Runs every 5 minutes in market hours off atlas_intraday.sh. One batched kite.quote()
for the union of names the notify-enabled crossover books care about, then per name:

    not held, quote >= P*        -> provisional BUY  (arm only; the CLOSE confirms)
    held,     quote <= level     -> provisional SELL (arm only)
    held, armed, at/after 15:15  -> SELL confirmed, or disarmed if it recovered

Levels come from the PRIOR close's confirmed EMAs — never the forming day's — which is
the same no-lookahead basis the backtest uses, so live and replay cannot quietly drift.

READS ONLY. This process never books a trade: the nightly mark remains the single
writer of portfolio_trades. What it writes is crossover_alerts, whose unique constraint
IS the dedup contract — without it a 78-tick session sends 78 identical messages.

The decision itself is pure and lives in atlas.portfolio.monitor, where it is unit
tested against real MRPL levels. This file is the I/O shell around it.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db

from atlas.intraday.auth import get_valid_access_token
from atlas.intraday.notify import send_message_sync
from atlas.portfolio import alerts
from atlas.portfolio.monitor import Tick, decide
from atlas.primitives import ema_cross_price

M = "atlas_foundation"
IST = ZoneInfo("Asia/Kolkata")

# Notify-enabled stock crossover books, every scored name in their universe, that name's
# PRIOR-close confirmed EMAs, its kite token, and whether the book currently holds it.
_WATCH_SQL = f"""
with books as (
    select portfolio_id, name, params
    from {M}.portfolio_master
    where status = 'active' and strategy_key = 'ema_cross'
      and asset_classes = '{{stock}}' and params->>'notify' = 'true'
),
held as (
    select portfolio_id, instrument_key,
           sum(case when side = 'buy' then qty else -qty end) qty
    from {M}.portfolio_trades where run_type = 'live'
    group by 1, 2 having sum(case when side = 'buy' then qty else -qty end) > 0
),
tech as (
    select distinct on (t.instrument_id) t.instrument_id, t.date,
           t.ema_10, t.ema_13, t.ema_21, t.ema_34, t.ema_50, t.ema_200
    from {M}.technical_daily t
    where t.date >= (current_date - interval '10 days')
    order by t.instrument_id, t.date desc
)
select b.portfolio_id::text pid, b.name, b.params::text params,
       i.instrument_id::text iid, i.symbol, i.kite_token,
       tech.ema_10, tech.ema_13, tech.ema_21, tech.ema_34, tech.ema_50, tech.ema_200,
       (h.instrument_key is not null) as held
from books b
cross join {M}.instrument_master i
join tech on tech.instrument_id = i.instrument_id
left join held h on h.portfolio_id = b.portfolio_id
                and h.instrument_key = i.instrument_id::text
where i.asset_class = 'stock' and i.is_active and i.kite_token is not null
"""


def _fired_today() -> set[tuple[str, str, str, str]]:
    """(pid, iid, direction, stage) already recorded today — the dedup memory."""
    df = _db.read_df(
        f"""select portfolio_id::text pid, instrument_id::text iid, direction, stage
            from {M}.crossover_alerts
            where alert_date = (now() at time zone 'Asia/Kolkata')::date"""
    )
    return {(r["pid"], r["iid"], r["direction"], r["stage"]) for r in df.to_dict("records")}


def _levels(row: dict, params: dict) -> tuple[Decimal, Decimal] | None:
    """(buy_level, sell_level) from the prior close's confirmed EMAs, or None if this
    name has no usable EMA pair yet (a recent listing, a data gap — never invented)."""
    fast, slow = int(params["fast"]), int(params["slow"])
    ef, es = row.get(f"ema_{fast}"), row.get(f"ema_{slow}")
    if ef is None or es is None:
        return None
    buy = Decimal(str(ema_cross_price(float(ef), float(es), fast=fast, slow=slow)))
    # fast_ema books sell when price loses the fast EMA itself; death_cross books at the
    # level where fast would cross below slow — the same number as the buy level.
    sell = Decimal(str(ef)) if params.get("exit") == "fast_ema" else buy
    return buy, sell


def _record(pid: str, row: dict, direction: str, stage: str, level: Decimal, quote: Decimal):
    _db.exec_sql(
        f"""insert into {M}.crossover_alerts
              (portfolio_id, instrument_id, symbol, direction, stage, level, quote)
            values (:p, :i, :s, :d, :st, :lv, :q)
            on conflict (portfolio_id, instrument_id, direction, stage, alert_date)
            do nothing""",
        {
            "p": pid,
            "i": row["iid"],
            "s": row["symbol"],
            "d": direction,
            "st": stage,
            "lv": level,
            "q": quote,
        },
    )


def main() -> None:
    rows = _db.read_df(_WATCH_SQL).to_dict("records")
    if not rows:
        print(
            "[crossover_monitor] no notify-enabled crossover books — nothing to watch", flush=True
        )
        return

    from kiteconnect import KiteConnect  # deferred: only needed when there is work

    kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
    kite.set_access_token(get_valid_access_token(conn_str=_db.db_url()))
    tokens = sorted({int(r["kite_token"]) for r in rows})
    raw = cast(dict[str, Any], kite.quote(tokens))  # kiteconnect stubs under-type this
    quotes = {int(v["instrument_token"]): Decimal(str(v["last_price"])) for v in raw.values()}

    now = datetime.now(IST).time()
    fired = _fired_today()
    sent = 0
    for row in rows:
        quote = quotes.get(int(row["kite_token"]))
        if quote is None:
            continue  # no print this tick — never substitute a stale price
        params = json.loads(row["params"]) if isinstance(row["params"], str) else row["params"]
        lv = _levels(row, params)
        if lv is None:
            continue
        buy_level, sell_level = lv
        pid, iid = row["pid"], row["iid"]
        already = frozenset((d, s) for (p, i, d, s) in fired if p == pid and i == iid)
        verdict = decide(
            Tick(
                held=bool(row["held"]),
                buy_level=buy_level,
                sell_level=sell_level,
                quote=quote,
                now=now,
                already=already,
            )
        )
        if verdict is None:
            continue
        direction, stage = verdict
        level = buy_level if direction == "buy" else sell_level
        _record(pid, row, direction, stage, level, quote)
        fired.add((pid, iid, direction, stage))
        # A disarm is recorded but NOT sent: it is the absence of a trade, and the FM
        # asked for a quieter channel. It stays queryable as the near-miss evidence.
        if stage == "provisional":
            send_message_sync(
                alerts.provisional(
                    book=row["name"],
                    symbol=row["symbol"],
                    side=direction,
                    level=level,
                    quote=quote,
                )
            )
            sent += 1
        elif stage == "confirmed":
            send_message_sync(
                alerts.confirmed(
                    book=row["name"],
                    symbol=row["symbol"],
                    side=direction,
                    level=level,
                    quote=quote,
                )
            )
            sent += 1

    print(f"[crossover_monitor] watched={len(rows)} quotes={len(quotes)} sent={sent}", flush=True)


if __name__ == "__main__":
    main()
