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
import pandas as pd
import portfolio_data as pdata
from desk_credibility import (
    build_credibility,
    compute_cvar,
    fetch_track_record,
    stamp_outcomes,
)
from desk_orders import (
    attach_plans,
    build_memo,
    load_charter,
    queue_order,
    run_risk_stances,
    send_memo,
    settle_pending,
    write_journal,
)
from portfolio_run import book_trade

from atlas.desk import (
    build_debate_messages,
    build_pm_messages,
    build_scout_messages,
    validate_debate,
    validate_pm,
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
        pd.DataFrame(snapshot.groupby("sector", as_index=False)["composite"].mean())
        .sort_values(by="composite", ascending=False)
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
    inval_map: dict[str, str] = (
        {} if inval.empty else dict(zip(inval["symbol"], inval["invalidation"], strict=False))
    )
    if not holdings.empty:
        holdings["invalidation"] = holdings["symbol"].map(lambda s: inval_map.get(str(s), ""))

    # the deterministic twin's current membership = one candidate signal
    charter = p["params"].get("charter", "sector_leaders")
    twin = get_strategy("rank_policy", {"mode": charter})
    universe = pdata.load_universe(["stock"])
    panel = pdata.load_composite(universe, eod - dt.timedelta(days=140), eod)
    panel = panel.merge(universe[["instrument_key", "sector"]], on="instrument_key", how="left")
    if twin.required_columns():  # e.g. quality_momentum needs RS + 200-EMA state
        tech_extra = pdata.load_tech(
            universe, twin.required_columns(), eod - dt.timedelta(days=140), eod
        )
        panel = panel.merge(tech_extra, on=["instrument_key", "date"], how="left")
    regime_df = _db.read_df(
        f"select date, regime_state from {M}.atlas_market_regime_daily where date >= :a",
        {"a": eod - dt.timedelta(days=140)},
    )
    panel = panel.merge(regime_df, on="date", how="left")
    members = twin.state(panel)
    key2sym = dict(zip(universe["instrument_key"], universe["symbol"], strict=False))
    twin_targets = sorted(key2sym[k] for k, v in members.items() if v and k in key2sym)

    # distilled memory: this desk's active lessons, highest conviction first
    lessons = _db.read_df(
        f"""select lesson, tags, confidence, layer from {M}.desk_lessons
            where portfolio_id = :p and active order by confidence desc, ts desc limit 5""",
        {"p": str(p["portfolio_id"])},
    )

    # payload diet: the scout request rides ~8k tokens against Groq's TPM cap —
    # long floats and verbose lessons were tipping cycles into 413 holds
    watchlist = watchlist.round(3)
    if not holdings.empty:
        holdings = holdings.round(3)
    sector_ranks = sector_ranks.round(2)
    if not lessons.empty:
        lessons["lesson"] = lessons["lesson"].str.slice(0, 240)
    return {
        "cycle_date": str(eod),
        "regime": regime,
        "lessons_from_experience": lessons.to_dict("records"),
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


_CONSTRAINT_CHECKS = {
    # standing constraints a validated reflection can promote (desk_reflect.py);
    # each maps to a field the watchlist snapshot already carries
    "require_rs_positive": lambda w: w.get("rs_3m_n500") is not None and float(w["rs_3m_n500"]) > 0,
    "require_above_200": lambda w: bool(w.get("above_ema_200")),
    "min_composite_60": lambda w: w.get("composite") is not None and float(w["composite"]) >= 60,
}


def hard_filter(
    orders: list[dict], inputs: dict, knobs: dict, constraints: list[str] | None = None
) -> tuple[list[dict], list[str]]:
    ok, rejected = [], []
    held = {h["symbol"] for h in inputs["portfolio"]["holdings"]}
    watch_by_sym = {w["symbol"]: w for w in inputs["watchlist_top_by_composite"]}
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
        elif side == "buy" and inputs.get("derisk"):
            rejected.append(f"{sym}: CVaR tripwire active — de-risk mode blocks new entries")
        elif side == "buy" and sym in held:
            rejected.append(f"{sym}: already held")
        elif side == "sell" and sym not in held:
            rejected.append(f"{sym}: not held")
        elif side == "buy" and sector_count.get(sector_of.get(sym, "?"), 0) >= knobs["sector_cap"]:
            rejected.append(f"{sym}: sector cap {knobs['sector_cap']} reached")
        elif side == "buy" and any(
            not _CONSTRAINT_CHECKS[c](watch_by_sym.get(sym, {}))
            for c in (constraints or [])
            if c in _CONSTRAINT_CHECKS
        ):
            rejected.append(f"{sym}: blocked by standing constraint (earned from reflection)")
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
        "min_rr": m["desk_min_rr"],
        "expiry_days": int(m["desk_pending_expiry_days"]),
        "consensus_min": int(m["desk_stance_consensus_min"]),
        "reduced_frac": m["desk_reduced_frac"],
        "cvar_tail": float(m["desk_cvar_tail_pct"]),
        "cvar_floor": float(m["desk_cvar_floor_pct"]),
        "cvar_min_n": int(m["desk_cvar_min_sessions"]),
    }


def run_cycle(p: dict, knobs: dict, dry: bool = False) -> dict:
    charter = p["params"].get("charter", "sector_leaders")
    inputs = assemble_inputs(p, knobs)
    sym2key = inputs.pop("_universe_sym2key")
    known = set(sym2key) | {h["symbol"] for h in inputs["portfolio"]["holdings"]}
    journal = {
        "scout": None,
        "risk": None,
        "pm": None,
        "debates": None,
        "trader": None,
        "applied": [],
        "queued": [],
        "errors": [],
        "inputs_digest": None,
    }
    # PM-only payload: keep it OUT of `inputs` — the scout request already runs
    # near the LLM's per-request token ceiling (413 above ~8k with Groq free tier)
    track = fetch_track_record(str(p["portfolio_id"]), charter)
    charter_text, charter_sha = load_charter(charter)
    cvar = compute_cvar(
        str(p["portfolio_id"]), knobs["cvar_tail"], knobs["cvar_floor"], knobs["cvar_min_n"]
    )
    inputs["derisk"] = cvar["state"] == "derisk"
    journal["inputs_digest"] = {
        "desk_version": 3,
        "credibility_rows": len(track),
        "charter_sha": charter_sha,
        "cvar": cvar,
    }

    try:
        scout = llm_call(build_scout_messages(charter, inputs, charter_text))
        journal["scout"] = scout
        errs = validate_scout(scout, known)
        if errs:
            journal["errors"] += errs
            return journal
        proposals = [x for x in scout["proposals"] if x["action"] in ("add", "exit")]
        if not proposals:
            journal["errors"].append("no actionable proposals — desk holds")
            return journal

        risk = run_risk_stances(
            llm_call,
            {
                "proposals": proposals,
                "holdings": inputs["portfolio"]["holdings"],
                "regime": inputs["regime"],
            },
            {x["symbol"] for x in proposals},
            knobs["consensus_min"],
        )
        journal["risk"] = risk
        if risk["errors"]:
            journal["errors"] += risk["errors"]
            return journal
        reduced = {v["symbol"] for v in risk["verdicts"] if v.get("reduced")}
        approved = {
            v["symbol"]: next(x["action"] for x in proposals if x["symbol"] == v["symbol"])
            for v in risk["verdicts"]
            if v["verdict"] == "approve"
        }
        if not approved:
            journal["errors"].append("risk approved nothing — desk holds")
            return journal

        # Bull/Bear debate on CONTESTED approved moves (≤2/cycle, token budget):
        # exits of holdings and high-urgency adds — the two places impulsive
        # churn hides. Transcripts go to the PM, who decides with both cases heard.
        debates = {}
        contested = [
            x
            for x in proposals
            if x["symbol"] in approved and (x["action"] == "exit" or x.get("urgency") == "high")
        ][:2]
        for x in contested:
            desc = f"{'selling' if x['action'] == 'exit' else 'buying'} {x['symbol']}"
            evidence = {
                "proposal": x,
                "holding": next(
                    (h for h in inputs["portfolio"]["holdings"] if h["symbol"] == x["symbol"]),
                    None,
                ),
                "watchlist_row": next(
                    (w for w in inputs["watchlist_top_by_composite"] if w["symbol"] == x["symbol"]),
                    None,
                ),
                "regime": inputs["regime"],
            }
            sides = {}
            for side_name in ("BULL", "BEAR"):
                reply = llm_call(build_debate_messages(side_name, desc, evidence), max_tokens=1500)
                if validate_debate(reply):
                    continue  # a broken debate side is dropped, not fatal
                sides[side_name.lower()] = reply
            if sides:
                debates[x["symbol"]] = sides
        journal["debates"] = debates or None

        pm = llm_call(
            build_pm_messages(
                charter,
                {
                    "debates": debates,
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
                    "track_record": track,
                },
                charter_text,
            )
        )
        journal["pm"] = pm
        errs = validate_pm(pm, approved)
        if errs:
            journal["errors"] += errs
            return journal

        orders, rejected = hard_filter(
            pm.get("orders", []), inputs, knobs, p["params"].get("standing_constraints")
        )
        journal["errors"] += rejected
        try:  # trader failure degrades to plan-less orders, never a lost cycle
            plans, trader, perrs = attach_plans(
                [o for o in orders if o["side"] == "buy"], knobs["min_rr"], llm_call
            )
        except RuntimeError as e:
            plans, trader, perrs = {}, None, [f"trader: {e}"]
        journal["trader"] = trader
        journal["errors"] += perrs
        approval = str(p["params"].get("approval", "")).lower() == "true"
        for o in orders:
            ckey = sym2key.get(o["symbol"])
            if ckey is None:
                journal["errors"].append(f"{o['symbol']}: no instrument key")
                continue
            card = {**o, **plans.get(o["symbol"], {})}
            if o["symbol"] in reduced:
                card["reduced"] = True
            if approval:
                if o["side"] == "buy" and o["symbol"] not in plans:
                    journal["errors"].append(f"{o['symbol']}: no valid plan — not queued")
                    continue
                if not dry:
                    queue_order(str(p["portfolio_id"]), _db.eod_cutoff(), card, ckey)
                journal["queued"].append(card)
                continue
            try:
                frac = (
                    knobs["reduced_frac"]
                    if o["side"] == "buy" and o["symbol"] in reduced
                    else Decimal("1")
                )
                res = (
                    {"dry_run": True}
                    if dry
                    else book_trade(str(p["portfolio_id"]), o["side"], ckey, frac=frac)
                )
                journal["applied"].append({**card, **res})
            except Exception as e:  # any booking failure skips the order, never the cycle
                journal["errors"].append(f"{o['symbol']}: {type(e).__name__}: {e}")
    except RuntimeError as e:
        journal["errors"].append(str(e))
    return journal


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas Desk nightly cycle")
    ap.add_argument("--portfolio-id")
    ap.add_argument("--force", action="store_true", help="rerun even if today's cycle exists")
    ap.add_argument("--dry-run", action="store_true", help="full cycle, print memo, no writes")
    a = ap.parse_args()
    eod = _db.eod_cutoff()
    q = f"""select portfolio_id::text pid from {M}.portfolio_master
            where status='active' and kind='basket' and origin='system'
              and params->>'desk' = 'true'"""
    ids = [a.portfolio_id] if a.portfolio_id else _db.read_df(q)["pid"].tolist()
    if not ids:
        print("[desk] no desk portfolios — nothing to do", flush=True)
        return
    try:  # a missing threshold row must not silently kill every desk
        knobs = _knobs()
    except Exception as e:
        print(f"[desk] knobs unavailable — desks do nothing: {e}", flush=True)
        return
    try:  # settlement of approved/expired cards runs before any new cycle
        settle_notes = settle_pending(knobs, dry=a.dry_run)
    except Exception as e:
        settle_notes = [f"❌ settlement failed: {e}"]
    summaries: list[dict] = []
    for pid in ids:
        if not (a.force or a.dry_run) and _db.scalar(
            f"select 1 from {M}.desk_journal where portfolio_id=:p and cycle_date=:d limit 1",
            {"p": pid, "d": eod},
        ):
            print(f"[desk] {pid}: cycle {eod} already ran — skipping", flush=True)
            continue
        p = pdata.load_portfolio(pid)
        try:
            journal = run_cycle(p, knobs, dry=a.dry_run)
        except Exception as e:  # one desk's crash must never starve the others
            journal = {k: None for k in ("scout", "risk", "pm", "debates", "trader")} | {
                "applied": [],
                "queued": [],
                "errors": [f"cycle crashed: {type(e).__name__}: {e}"],
            }
        if not a.dry_run:
            write_journal(pid, eod, journal)
        elif journal["errors"]:
            print(f"[desk][dry] errors: {journal['errors']}", flush=True)
        summaries.append(
            {"name": p["name"], **{k: journal[k] for k in ("applied", "queued", "errors")}}
        )
        print(
            f"[desk] {p['name']}: applied={len(journal['applied'] or [])} "
            f"queued={len(journal['queued'] or [])} errors={len(journal['errors'] or [])}",
            flush=True,
        )
    if not a.dry_run:
        try:  # stamping/credibility failures must never block the decision memo
            stamp_outcomes()
            build_credibility()
        except Exception as e:
            print(f"[desk] stamping/credibility failed: {e}", flush=True)
    memo = build_memo(eod, summaries, settle_notes)
    print(memo, flush=True) if a.dry_run else send_memo(memo)


if __name__ == "__main__":
    main()
