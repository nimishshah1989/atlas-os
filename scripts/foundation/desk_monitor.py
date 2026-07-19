#!/usr/bin/env python3
"""Intraday desk-position breach monitor (Desk v2 wave 1b).

Every intraday tick (atlas_intraday.sh cron, market hours only): pull one
batched kite.quote() for every open desk position that carries a trade plan,
flag stop breaches / target hits, write desk_alerts (one per position/kind/
IST day), notify Telegram. The cron gates market hours; a missing plan or
token simply means the position is not monitored — never an invented level.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db

from atlas.intraday.auth import get_valid_access_token
from atlas.intraday.notify import send_message_sync

M = "atlas_foundation"

# open desk stock positions × their latest journaled plan × kite token
_MONITORED_SQL = f"""
with cards as (
    select dj.portfolio_id, c->>'symbol' sym, (c->>'stop')::numeric stop,
           (c->>'target')::numeric target, dj.cycle_date cd
    from {M}.desk_journal dj, jsonb_array_elements(dj.applied) c
    where c->>'side' = 'buy' and c ? 'stop'
    union all
    select portfolio_id, symbol, stop, target, cycle_date
    from {M}.desk_pending_orders where status = 'booked' and stop is not null
),
latest as (
    select distinct on (portfolio_id, sym) portfolio_id, sym, stop, target
    from cards order by portfolio_id, sym, cd desc
),
pos as (
    select t.portfolio_id, t.instrument_key,
           sum(case when t.side = 'buy' then t.qty else -t.qty end) qty
    from {M}.portfolio_trades t
    join {M}.portfolio_master m using (portfolio_id)
    where m.status = 'active' and m.params->>'desk' = 'true' and t.run_type = 'live'
    group by 1, 2
    having sum(case when t.side = 'buy' then t.qty else -t.qty end) > 0
)
select l.portfolio_id::text pid, m.name, l.sym, l.stop, l.target, i.kite_token
from latest l
join pos p on p.portfolio_id = l.portfolio_id
join {M}.portfolio_master m on m.portfolio_id = l.portfolio_id
join {M}.instrument_master i
  on i.instrument_id::text = p.instrument_key and i.symbol = l.sym
where i.kite_token is not null
"""


def monitored_positions() -> list[dict]:
    return _db.read_df(_MONITORED_SQL).to_dict("records")


def breaches(rows: list[dict], quotes: dict[int, Decimal]) -> list[dict]:
    """Pure: compare live quotes to plan levels. Returns alert dicts."""
    out = []
    for r in rows:
        ltp = quotes.get(int(r["kite_token"]))
        if ltp is None or ltp <= 0:
            continue
        stop, target = Decimal(str(r["stop"])), Decimal(str(r["target"]))
        if ltp <= stop:
            out.append({**r, "kind": "stop", "level": stop, "quote": ltp})
        elif ltp >= target:
            out.append({**r, "kind": "target", "level": target, "quote": ltp})
    return out


def _today_alerted() -> set[tuple[str, str, str]]:
    df = _db.read_df(
        f"""select portfolio_id::text pid, symbol, kind from {M}.desk_alerts
            where alert_date = (now() at time zone 'Asia/Kolkata')::date"""
    )
    return {(r["pid"], r["symbol"], r["kind"]) for r in df.to_dict("records")}


def record_and_notify(alerts: list[dict]) -> int:
    seen = _today_alerted()
    n = 0
    for a in alerts:
        if (a["pid"], a["sym"], a["kind"]) in seen:
            continue
        _db.exec_sql(
            f"""insert into {M}.desk_alerts (portfolio_id, symbol, kind, level, quote)
                values (:p, :s, :k, :lv, :q)
                on conflict (portfolio_id, symbol, kind, alert_date) do nothing""",
            {"p": a["pid"], "s": a["sym"], "k": a["kind"], "lv": a["level"], "q": a["quote"]},
        )
        emoji = "🛑" if a["kind"] == "stop" else "🎯"
        send_message_sync(
            f"{emoji} <b>{a['sym']}</b> {a['kind']} {'breached' if a['kind'] == 'stop' else 'hit'} "
            f"— quote {a['quote']} vs level {a['level']} ({a['name']})\n"
            "Review: python scripts/foundation/desk_approve.py"
        )
        n += 1
    return n


def main() -> None:
    rows = monitored_positions()
    if not rows:
        print("[desk_monitor] no monitored positions", flush=True)
        return
    from kiteconnect import KiteConnect  # deferred: only needed with positions

    kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
    kite.set_access_token(get_valid_access_token(conn_str=_db.db_url()))
    tokens = [int(r["kite_token"]) for r in rows]
    raw = cast(dict[str, Any], kite.quote(tokens))  # kiteconnect stubs under-type this
    quotes = {int(v["instrument_token"]): Decimal(str(v["last_price"])) for v in raw.values()}
    alerts = breaches(rows, quotes)
    n = record_and_notify(alerts)
    print(f"[desk_monitor] positions={len(rows)} breaches={len(alerts)} new_alerts={n}", flush=True)


if __name__ == "__main__":
    main()
