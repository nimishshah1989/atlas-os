#!/usr/bin/env python3
"""Atlas Desk order layer (Desk v2, wave 1) — trade-plan levels, approval queue,
pending settlement, and the nightly Telegram decision memo.

Split from desk_run.py (600-LOC cap): desk_run owns the agent cycle; this module
owns what happens to an order AFTER the PM issues it. Same fail-safe philosophy:
a missing plan or a broken level query means the order carries no plan (auto
desks) or is not queued (approval desks) — never an invented number.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db
from portfolio_run import TradeError, book_trade

from atlas.desk import build_trader_messages, check_plan, validate_trader

M = "atlas_foundation"


# ── trade-plan levels + EXECUTION TRADER call ───────────────────────────────


def plan_levels(symbols: list[str]) -> dict[str, dict]:
    """Real price levels per symbol for the EXECUTION TRADER: latest EMAs/ATR
    from technical_daily + 20-session swing extremes from adjusted OHLCV.
    Symbols with incomplete data are omitted (no plan can be grounded)."""
    out: dict[str, dict] = {}
    for sym in symbols:
        row = _db.read_df(
            f"""select o.close_adj last_close, t.ema_21, t.ema_50, t.ema_200, t.atr_14
                from {M}.instrument_master i
                join {M}.technical_daily t on t.instrument_id = i.instrument_id
                join {M}.ohlcv_stock o
                  on o.instrument_id = i.instrument_id and o.date = t.date
                where i.symbol = :s
                order by t.date desc limit 1""",
            {"s": sym},
        )
        swing = _db.read_df(
            f"""select min(low_adj) low_20d, max(high_adj) high_20d
                from (select o.low_adj, o.high_adj
                      from {M}.ohlcv_stock o
                      join {M}.instrument_master i using (instrument_id)
                      where i.symbol = :s
                      order by o.date desc limit 20) w""",
            {"s": sym},
        )
        if row.empty or swing.empty or row.iloc[0].isna().any():
            continue
        r, s = row.iloc[0], swing.iloc[0]
        out[sym] = {c: round(float(r[c]), 2) for c in row.columns} | {
            "low_20d": round(float(s["low_20d"]), 2),
            "high_20d": round(float(s["high_20d"]), 2),
        }
    return out


def attach_plans(
    buys: list[dict], min_rr: Decimal, llm_call: Callable[..., dict]
) -> tuple[dict[str, dict], dict | None, list[str]]:
    """One TRADER call for the cycle's buy orders → per-symbol validated plans.
    Returns (plans, raw trader reply for the journal, errors). Every level the
    agent may cite comes from plan_levels; geometry + R:R re-checked in code."""
    if not buys:
        return {}, None, []
    levels = plan_levels([o["symbol"] for o in buys])
    if not levels:
        return {}, None, ["trader: no plan levels available"]
    trader = llm_call(
        build_trader_messages({"orders": buys, "levels": levels}, float(min_rr)),
        max_tokens=1200,
    )
    errs = validate_trader(trader, set(levels))
    if errs:
        return {}, trader, [f"trader: {e}" for e in errs]
    plans: dict[str, dict] = {}
    out_errs: list[str] = []
    for pl in trader["plans"]:
        lv = levels[pl["symbol"]]
        entry = Decimal(str(lv["last_close"]))
        stop, target = Decimal(str(pl["stop"])), Decimal(str(pl["target"]))
        rr, perrs = check_plan(entry, stop, target, min_rr)
        if perrs:
            out_errs += [f"{pl['symbol']}: {e}" for e in perrs]
            continue
        plans[pl["symbol"]] = {
            "entry_ref": entry,
            "stop": stop,
            "target": target,
            "rr": round(rr or 0.0, 2),
            "plan_basis": str(pl["basis"]),
        }
    return plans, trader, out_errs


def run_risk_stances(
    llm_call: Callable[..., dict], payload: dict, proposed: set[str], consensus_min: int
) -> dict:
    """Three independent RISK stances (SAFE/NEUTRAL/RISKY) merged by code into
    selective consensus: approve needs >= consensus_min stances; a split vote
    is flagged reduced (sized down by the engine). Fewer than 2 valid stances
    → error and the desk holds — doing nothing is always safe."""
    from atlas.desk import RISK_STANCES, build_risk_messages, validate_risk

    stances: dict[str, dict] = {}
    for name in RISK_STANCES:
        try:
            reply = llm_call(build_risk_messages(payload, name), max_tokens=1500)
        except RuntimeError:
            continue
        if not validate_risk(reply, proposed):
            stances[name.lower()] = reply
    if len(stances) < 2:
        return {
            "stances": stances,
            "verdicts": [],
            "errors": ["risk: <2 valid stances — desk holds"],
        }
    approvals: dict[str, int] = {}
    for reply in stances.values():
        for v in reply["verdicts"]:
            if v["verdict"] == "approve":
                approvals[v["symbol"]] = approvals.get(v["symbol"], 0) + 1
    verdicts = []
    for sym in sorted(proposed):
        n = approvals.get(sym, 0)
        verdict = "approve" if n >= consensus_min else "veto"
        reasons = [
            f"{name}: {v['verdict']} — {v['reason']}"
            for name, reply in stances.items()
            for v in reply["verdicts"]
            if v["symbol"] == sym
        ]
        verdicts.append(
            {
                "symbol": sym,
                "verdict": verdict,
                "consensus": n,
                "reduced": verdict == "approve" and n < len(stances),
                "reason": " | ".join(reasons),
            }
        )
    return {"stances": stances, "verdicts": verdicts, "errors": []}


# ── approval queue ──────────────────────────────────────────────────────────


def queue_order(pid: str, cycle_date: Any, o: dict, ckey: str) -> None:
    """One PM order → one pending approval card (idempotent per desk/sym/day)."""
    _db.exec_sql(
        f"""insert into {M}.desk_pending_orders
            (portfolio_id, cycle_date, symbol, side, instrument_key, thesis,
             invalidation, entry_ref, stop, target, rr, plan_basis)
            values (:p, :d, :sym, :side, :ck, :th, :inv, :e, :st, :tg, :rr, :b)
            on conflict (portfolio_id, symbol, cycle_date) do nothing""",
        {
            "p": pid,
            "d": cycle_date,
            "sym": o["symbol"],
            "side": o["side"],
            "ck": ckey,
            "th": o.get("thesis", ""),
            "inv": o.get("invalidation", ""),
            "e": o.get("entry_ref"),
            "st": o.get("stop"),
            "tg": o.get("target"),
            "rr": o.get("rr"),
            "b": o.get("plan_basis"),
        },
    )


def settle_pending(expiry_days: int, dry: bool = False) -> list[str]:
    """Cycle-start settlement: expire stale cards, book approved ones through
    the audited book_trade path. Returns memo lines."""
    notes: list[str] = []
    stale = _db.read_df(
        f"""select id, symbol from {M}.desk_pending_orders
            where status = 'pending' and cycle_date < current_date - :n""",
        {"n": expiry_days},
    )
    for r in stale.to_dict("records"):
        if not dry:
            _db.exec_sql(
                f"""update {M}.desk_pending_orders set status = 'expired',
                    decided_at = now(), decided_by = 'auto-expiry' where id = :i""",
                {"i": r["id"]},
            )
        notes.append(f"⌛ expired unapproved: {r['symbol']}")
    appr = _db.read_df(
        f"""select id, portfolio_id::text pid, symbol, side, instrument_key
            from {M}.desk_pending_orders where status = 'approved'"""
    )
    for r in appr.to_dict("records"):
        if dry:
            notes.append(f"(dry) would book {r['side']} {r['symbol']}")
            continue
        try:
            res = book_trade(r["pid"], r["side"], r["instrument_key"])
            _db.exec_sql(
                f"""update {M}.desk_pending_orders set status = 'booked',
                    booked_at = now() where id = :i""",
                {"i": r["id"]},
            )
            notes.append(f"✅ booked on approval: {r['side']} {r['symbol']} @ {res.get('price')}")
        except (TradeError, RuntimeError) as e:
            _db.exec_sql(
                f"""update {M}.desk_pending_orders set status = 'failed',
                    note = :n where id = :i""",
                {"i": r["id"], "n": str(e)},
            )
            notes.append(f"❌ booking failed: {r['symbol']} — {e}")
    return notes


def write_journal(pid: str, eod: Any, journal: dict) -> None:
    """Persist one desk cycle — full glass-box record including trader + queue."""
    _db.exec_sql(
        f"""insert into {M}.desk_journal
            (portfolio_id, cycle_date, scout, risk, pm, debates, trader, applied,
             queued, errors, inputs_digest)
            values (:p, :d, cast(:s as jsonb), cast(:r as jsonb), cast(:m as jsonb),
                    cast(:db as jsonb), cast(:tr as jsonb), cast(:ap as jsonb),
                    cast(:qu as jsonb), cast(:er as jsonb), cast(:dig as jsonb))""",
        {
            "p": pid,
            "d": eod,
            "s": json.dumps(journal["scout"], default=str),
            "r": json.dumps(journal["risk"], default=str),
            "m": json.dumps(journal["pm"], default=str),
            "db": json.dumps(journal.get("debates"), default=str),
            "tr": json.dumps(journal.get("trader"), default=str),
            "ap": json.dumps(journal["applied"], default=str),
            "qu": json.dumps(journal.get("queued", []), default=str),
            "er": json.dumps(journal["errors"], default=str),
            "dig": json.dumps(journal.get("inputs_digest"), default=str),
        },
    )


# ── nightly decision memo ───────────────────────────────────────────────────


def _card(tag: str, o: dict) -> str:
    line = f"{tag} {o['side'].upper()} {o['symbol']}"
    if o.get("stop") is not None:
        line += f" · entry {o.get('entry_ref')} · stop {o['stop']} · target {o['target']} · R:R {o.get('rr')}"
    thesis = str(o.get("thesis", "")).strip()
    inval = str(o.get("invalidation", "")).strip()
    if thesis:
        line += f"\n      {thesis}"
    if inval:
        line += f"\n      ✂️ invalid if: {inval}"
    return line


def build_memo(cycle_date: Any, desks: list[dict], settle_notes: list[str]) -> str:
    regime = _db.scalar(
        f"select regime_state from {M}.atlas_market_regime_daily order by date desc limit 1"
    )
    lines = [f"<b>🧭 Atlas Desk — {cycle_date}</b> · regime: {regime}"]
    pending_total = 0
    for d in desks:
        lines.append(f"\n<b>{d['name']}</b>")
        for o in d.get("applied", []):
            lines.append(_card("✅", o))
        for o in d.get("queued", []):
            lines.append(_card("🕐", o))
            pending_total += 1
        if not d.get("applied") and not d.get("queued"):
            lines.append("— no action")
        n_err = len(d.get("errors", []))
        if n_err:
            lines.append(f"⚠️ {n_err} filtered/errors (see desk_journal)")
    lines += settle_notes
    if pending_total:
        lines.append(
            f"\n🕐 {pending_total} order(s) awaiting approval → "
            "python scripts/foundation/desk_approve.py"
        )
    return "\n".join(lines)


def send_memo(text: str) -> None:
    """Telegram delivery; graceful no-op when unconfigured, never fatal."""
    try:
        from atlas.intraday.notify import send_message_sync

        send_message_sync(text)
    except Exception as e:  # memo must never break the desk cycle
        print(f"[desk] memo send failed: {e}", flush=True)
