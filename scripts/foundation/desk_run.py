#!/usr/bin/env python3
"""Atlas Desk orchestrator (Phase B1) — the nightly agent cycle per desk portfolio.

    python desk_run.py            # every active desk (idempotent per cycle date)
    python desk_run.py --portfolio-id X [--force]

Cycle: assemble Atlas snapshot → SCOUT proposes (or correctly proposes nothing)
→ RISK & TAX judges each proposal → PM issues orders with thesis+invalidation →
HARD CODE-ENFORCED filters (order count, sector cap, Risk-Off entry block) →
each order booked through portfolio_run.book_trade (the same audited path as
manual trades: real EOD close, costs, FIFO tax) → full cycle journaled to
desk_journal. A malformed agent reply or a missing LLM key means the desk does
NOTHING that night — doing nothing is always safe (the book still marks).

LLM: OpenAI-compatible endpoint from .env (DESK_LLM_BASE_URL/API_KEY/MODEL —
currently Groq gpt-oss-120b, free tier). Forward-only by design: the desk is
never backtested (Profit Mirage, see spec 2026-07-04).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _db
import portfolio_data as pdata
from portfolio_run import TradeError, book_trade

from atlas.desk import (
    build_pm_messages,
    build_risk_messages,
    build_scout_messages,
    validate_pm,
    validate_risk,
    validate_scout,
)
from atlas.portfolio import get_strategy

M = "atlas_foundation"
_RISK_OFF = ("Risk-Off", "DISLOCATION_SUSPENDED")


# ── LLM client (OpenAI-compatible; env-driven) ──────────────────────────────


def llm_call(messages: list[dict], max_tokens: int = 2500) -> dict:
    """One chat call → parsed JSON dict. One retry with a JSON-only nudge.
    Raises RuntimeError on unusable output (caller journals and does nothing)."""
    base = os.environ.get("DESK_LLM_BASE_URL", "")
    key = os.environ.get("DESK_LLM_API_KEY", "")
    model = os.environ.get("DESK_LLM_MODEL", "")
    if not (base and key and model) or "REPLACE" in key:
        raise RuntimeError("DESK_LLM_* not configured")
    if not base.startswith("https://"):
        raise RuntimeError("DESK_LLM_BASE_URL must be https")
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,  # gpt-oss spends tokens on reasoning first
        "response_format": {"type": "json_object"},
    }
    json_nudged = False
    for attempt in range(6):
        req = urllib.request.Request(  # noqa: S310 — scheme enforced https above
            f"{base}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "User-Agent": "atlas-desk/1.0",  # default Python-urllib UA gets 403 at the edge
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
                out = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode(errors="replace")
            if e.code == 429 and attempt < 5:
                # free-tier TPM pacing: honor the server's retry hint
                m = re.search(r"try again in ([0-9.]+)s", detail)
                wait = min(float(m.group(1)) + 3 if m else 30.0, 90.0)
                print(f"[desk] 429 — pacing {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError(f"LLM HTTP {e.code}: {detail}") from None
        content = (out.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            if json_nudged:
                raise RuntimeError(f"unparseable LLM output: {content[:200]!r}") from None
            json_nudged = True
            body["messages"] = [
                *messages,
                {
                    "role": "user",
                    "content": "Your last reply was not valid JSON. Output ONLY the JSON object.",
                },
            ]
    raise RuntimeError("LLM retries exhausted")


# ── input assembly (all REAL stored data) ───────────────────────────────────


def assemble_inputs(p: dict, knobs: dict) -> dict:
    eod = _db.eod_cutoff()
    watch_n = knobs["watchlist"]
    snapshot = _db.read_df(
        f"""with latest as (select max(date) d from {M}.atlas_lens_scores_daily),
        prev as (select max(date) d from {M}.atlas_lens_scores_daily
                 where date <= (select d from latest) - 7)
        select i.symbol, i.sector, s.composite,
               s.composite - s5.composite as composite_5d_delta,
               t.rs_3m_n500, t.above_ema_50, t.above_ema_200, s.risk_flags
        from {M}.atlas_lens_scores_daily s
        join {M}.instrument_master i on i.instrument_id = s.instrument_id
        left join {M}.atlas_lens_scores_daily s5
          on s5.instrument_id = s.instrument_id and s5.date = (select d from prev)
        left join {M}.technical_daily t
          on t.instrument_id = s.instrument_id and t.date = s.date
        where s.date = (select d from latest) and s.asset_class = 'stock'
        order by s.composite desc"""
    )
    watchlist = snapshot.head(watch_n)
    sector_ranks = (
        snapshot.groupby("sector", as_index=False)["composite"]
        .mean()
        .sort_values("composite", ascending=False)
        .head(12)
    )
    regime = _db.scalar(
        f"select regime_state from {M}.atlas_market_regime_daily order by date desc limit 1"
    )

    holdings = _db.read_df(
        f"""with pos as (
              select instrument_key, symbol,
                     sum(case when side='buy' then qty else -qty end) qty,
                     min(trade_date) filter (where side='buy') first_buy
              from {M}.portfolio_trades where portfolio_id = :p and run_type='live'
              group by 1, 2 having sum(case when side='buy' then qty else -qty end) <> 0)
            select pos.symbol, i.sector, pos.first_buy,
                   (current_date - pos.first_buy) as days_held,
                   s.composite, t.rs_3m_n500, t.above_ema_200
            from pos
            join {M}.instrument_master i on i.instrument_id::text = pos.instrument_key
            left join {M}.atlas_lens_scores_daily s on s.instrument_id = i.instrument_id
              and s.date = (select max(date) from {M}.atlas_lens_scores_daily)
            left join {M}.technical_daily t on t.instrument_id = i.instrument_id
              and t.date = (select max(date) from {M}.technical_daily)""",
        {"p": str(p["portfolio_id"])},
    )
    if not holdings.empty:
        holdings["tax_status"] = holdings["days_held"].map(
            lambda d: "LTCG (12.5%)" if d >= 365 else f"STCG (20%), LTCG in {365 - int(d)}d"
        )
    # standing invalidation conditions from this desk's own past PM orders
    inval = _db.read_df(
        f"""select o->>'symbol' symbol, o->>'invalidation' invalidation
            from {M}.desk_journal dj, jsonb_array_elements(dj.pm->'orders') o
            where dj.portfolio_id = :p and o->>'side' = 'buy'
            order by dj.ts desc""",
        {"p": str(p["portfolio_id"])},
    )
    inval_map = (
        {} if inval.empty else dict(zip(inval["symbol"], inval["invalidation"], strict=False))
    )
    if not holdings.empty:
        holdings["invalidation"] = holdings["symbol"].map(inval_map).fillna("")

    # the deterministic twin's current membership = one candidate signal
    charter = p["params"].get("charter", "sector_leaders")
    twin = get_strategy("rank_policy", {"mode": charter})
    universe = pdata.load_universe(["stock"])
    panel = pdata.load_composite(universe, eod - dt.timedelta(days=140), eod)
    panel = panel.merge(universe[["instrument_key", "sector"]], on="instrument_key", how="left")
    regime_df = _db.read_df(
        f"select date, regime_state from {M}.atlas_market_regime_daily where date >= :a",
        {"a": eod - dt.timedelta(days=140)},
    )
    panel = panel.merge(regime_df, on="date", how="left")
    members = twin.state(panel)
    key2sym = dict(zip(universe["instrument_key"], universe["symbol"], strict=False))
    twin_targets = sorted(key2sym[k] for k, v in members.items() if v and k in key2sym)

    return {
        "cycle_date": str(eod),
        "regime": regime,
        "portfolio": {
            "nav": float(
                _db.scalar(
                    f"select nav from {M}.portfolio_nav_daily where portfolio_id=:p "
                    "and run_type='live' order by date desc limit 1",
                    {"p": str(p["portfolio_id"])},
                )
                or 0
            ),
            "holdings": holdings.to_dict("records"),
        },
        "watchlist_top_by_composite": watchlist.to_dict("records"),
        "sector_strength_ranks": sector_ranks.to_dict("records"),
        "deterministic_twin_targets": twin_targets,
        "_universe_sym2key": {
            str(s): f"stock:{k}" for k, s in key2sym.items()
        },  # stripped before prompting
    }


# ── hard, code-enforced constraints (never delegated to the model) ──────────


def hard_filter(orders: list[dict], inputs: dict, knobs: dict) -> tuple[list[dict], list[str]]:
    ok, rejected = [], []
    held = {h["symbol"] for h in inputs["portfolio"]["holdings"]}
    sector_of = {w["symbol"]: w["sector"] for w in inputs["watchlist_top_by_composite"]}
    for h in inputs["portfolio"]["holdings"]:
        sector_of.setdefault(h["symbol"], h["sector"])
    sector_count: dict[str, int] = {}
    for h in inputs["portfolio"]["holdings"]:
        sector_count[h["sector"]] = sector_count.get(h["sector"], 0) + 1
    risk_off = inputs["regime"] in _RISK_OFF
    seen: set[str] = set()
    for o in orders:
        sym, side = o["symbol"], o["side"]
        if len(ok) >= knobs["max_orders"]:
            rejected.append(f"{sym}: over max_orders_per_cycle")
        elif sym in seen:
            rejected.append(f"{sym}: duplicate order")
        elif side == "buy" and risk_off:
            rejected.append(f"{sym}: regime {inputs['regime']} blocks new entries")
        elif side == "buy" and sym in held:
            rejected.append(f"{sym}: already held")
        elif side == "sell" and sym not in held:
            rejected.append(f"{sym}: not held")
        elif side == "buy" and sector_count.get(sector_of.get(sym, "?"), 0) >= knobs["sector_cap"]:
            rejected.append(f"{sym}: sector cap {knobs['sector_cap']} reached")
        else:
            ok.append(o)
            seen.add(sym)
            if side == "buy":
                sec = sector_of.get(sym, "?")
                sector_count[sec] = sector_count.get(sec, 0) + 1
    return ok, rejected


# ── the cycle ───────────────────────────────────────────────────────────────


def _knobs() -> dict:
    th = _db.read_df(
        f"select threshold_key k, threshold_value v from {M}.atlas_thresholds "
        "where category='portfolio' and is_active"
    )
    m = {r["k"]: Decimal(str(r["v"])) for r in th.to_dict("records")}
    return {
        "max_orders": int(m["desk_max_orders_per_cycle"]),
        "sector_cap": int(m["desk_sector_cap"]),
        "watchlist": int(m["desk_watchlist_size"]),
    }


def run_cycle(p: dict, knobs: dict) -> dict:
    charter = p["params"].get("charter", "sector_leaders")
    inputs = assemble_inputs(p, knobs)
    sym2key = inputs.pop("_universe_sym2key")
    known = set(sym2key) | {h["symbol"] for h in inputs["portfolio"]["holdings"]}
    journal = {"scout": None, "risk": None, "pm": None, "applied": [], "errors": []}

    try:
        scout = llm_call(build_scout_messages(charter, inputs))
        journal["scout"] = scout
        errs = validate_scout(scout, known)
        if errs:
            journal["errors"] += errs
            return journal
        proposals = [x for x in scout["proposals"] if x["action"] in ("add", "exit")]
        if not proposals:
            journal["errors"].append("no actionable proposals — desk holds")
            return journal

        risk = llm_call(
            build_risk_messages(
                {
                    "proposals": proposals,
                    "holdings": inputs["portfolio"]["holdings"],
                    "regime": inputs["regime"],
                }
            )
        )
        journal["risk"] = risk
        errs = validate_risk(risk, {x["symbol"] for x in proposals})
        if errs:
            journal["errors"] += errs
            return journal
        approved = {
            v["symbol"]: next(x["action"] for x in proposals if x["symbol"] == v["symbol"])
            for v in risk["verdicts"]
            if v["verdict"] == "approve"
        }
        if not approved:
            journal["errors"].append("risk approved nothing — desk holds")
            return journal

        pm = llm_call(
            build_pm_messages(
                charter,
                {
                    "approved_proposals": [
                        {
                            **x,
                            "risk_reason": next(
                                v["reason"] for v in risk["verdicts"] if v["symbol"] == x["symbol"]
                            ),
                        }
                        for x in proposals
                        if x["symbol"] in approved
                    ],
                    "portfolio": inputs["portfolio"],
                    "regime": inputs["regime"],
                },
            )
        )
        journal["pm"] = pm
        errs = validate_pm(pm, approved)
        if errs:
            journal["errors"] += errs
            return journal

        orders, rejected = hard_filter(pm.get("orders", []), inputs, knobs)
        journal["errors"] += rejected
        for o in orders:
            ckey = sym2key.get(o["symbol"])
            if ckey is None:
                journal["errors"].append(f"{o['symbol']}: no instrument key")
                continue
            try:
                res = book_trade(str(p["portfolio_id"]), o["side"], ckey)
                journal["applied"].append({**o, **res})
            except TradeError as e:
                journal["errors"].append(f"{o['symbol']}: {e}")
    except RuntimeError as e:
        journal["errors"].append(str(e))
    return journal


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas Desk nightly cycle")
    ap.add_argument("--portfolio-id")
    ap.add_argument("--force", action="store_true", help="rerun even if today's cycle exists")
    a = ap.parse_args()
    eod = _db.eod_cutoff()
    q = f"""select portfolio_id::text pid from {M}.portfolio_master
            where status='active' and kind='basket' and origin='system'
              and params->>'desk' = 'true'"""
    ids = [a.portfolio_id] if a.portfolio_id else _db.read_df(q)["pid"].tolist()
    if not ids:
        print("[desk] no desk portfolios — nothing to do", flush=True)
        return
    knobs = _knobs()
    for pid in ids:
        if not a.force and _db.scalar(
            f"select 1 from {M}.desk_journal where portfolio_id=:p and cycle_date=:d limit 1",
            {"p": pid, "d": eod},
        ):
            print(f"[desk] {pid}: cycle {eod} already ran — skipping", flush=True)
            continue
        p = pdata.load_portfolio(pid)
        journal = run_cycle(p, knobs)
        _db.exec_sql(
            f"""insert into {M}.desk_journal
                (portfolio_id, cycle_date, scout, risk, pm, applied, errors)
                values (:p, :d, cast(:s as jsonb), cast(:r as jsonb), cast(:m as jsonb),
                        cast(:ap as jsonb), cast(:er as jsonb))""",
            {
                "p": pid,
                "d": eod,
                "s": json.dumps(journal["scout"], default=str),
                "r": json.dumps(journal["risk"], default=str),
                "m": json.dumps(journal["pm"], default=str),
                "ap": json.dumps(journal["applied"], default=str),
                "er": json.dumps(journal["errors"], default=str),
            },
        )
        print(
            f"[desk] {p['name']}: applied={len(journal['applied'])} "
            f"errors={len(journal['errors'])}",
            flush=True,
        )


if __name__ == "__main__":
    main()
