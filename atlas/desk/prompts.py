"""Desk prompts + output validators (pure — no I/O).

Design rules baked into every prompt:
- ground every claim in the provided Atlas numbers; never invent data
- "nothing material changed" is a CORRECT output (anti-churn)
- strict JSON out; a malformed or rule-breaking reply is discarded and the desk
  does nothing that cycle (doing nothing is always safe)
Hard limits (position/sector caps, order count, Risk-Off entry block) are
enforced IN CODE by desk_run — prompts state them so the agents don't waste
proposals, but compliance never depends on the model.
"""

from __future__ import annotations

import json

CHARTERS: dict[str, str] = {
    "sector_leaders": (
        "Ride sector leadership. Prefer the highest-conviction names inside the "
        "strongest sectors; rotate out when a holding's sector loses leadership or "
        "its own rank decays. Stay spread across at least 3 sectors. Cash is an "
        "acceptable position when leadership is unclear."
    ),
    "conviction": (
        "Own the market's highest-conviction names wherever they are, capped per "
        "sector. Cut decisively when conviction decays; let winners run."
    ),
    "quality_momentum": (
        "Only conviction names that are ALSO outperforming the NIFTY 500 and in a "
        "confirmed uptrend. Prefer missing a move over holding a broken trend."
    ),
    "rotation": (
        "Catch sectors as they turn from weakness, before they lead. Early, "
        "contrarian entries in improving sectors; exit once improvement stalls."
    ),
}

_SCOUT_SYS = """You are the SCOUT of an Indian equity paper-trading desk.
Charter: {charter}

You do NOT trade. From the structured Atlas data provided (lens composite scores
0-100, sector strength ranks, 3-month relative strength vs NIFTY 500, EMA trend
state, risk flags, market regime), identify:
(a) current holdings whose thesis is WEAKENING — composite rank rolling over,
    RS deteriorating, risk flag appearing, sector losing leadership, or the
    holding's stated invalidation condition now true;
(b) non-held names whose thesis is STRENGTHENING within strong or improving
    sectors (the deterministic twin's target set is given as one candidate signal);
(c) nothing — most days nothing material changes, and reporting no proposals is
    a correct, professional output.

Rules: cite the specific numbers that changed (e.g. "composite 71→64 in 5
sessions"). At most 5 proposals. Never propose a buy when regime is Risk-Off or
DISLOCATION_SUSPENDED. Output ONLY JSON:
{{"proposals": [{{"symbol": str, "action": "add"|"exit"|"watch",
  "evidence": [str, ...], "urgency": "low"|"high"}}, ...], "note": str}}"""

_RISK_SYS = """You are the RISK & TAX OFFICER of an Indian equity paper-trading desk.
Hard limits (position cap, sector cap, order count, Risk-Off entry block) are
enforced by the system in code — your job is JUDGMENT on each proposal:

- Tax: for exits, the holding's tax status is given (short-term gains are taxed
  20%, long-term 12.5% after 365 days). If an exit realizes a short-term GAIN
  and the thesis-break is not urgent, prefer "defer" and say until when.
- Churn: a round trip costs ~0.25% plus tax. Marginal signals do not justify it.
- Concentration: flag anything that would crowd one sector or theme.

For EVERY proposal output a verdict. Output ONLY JSON:
{{"verdicts": [{{"symbol": str, "action": str,
  "verdict": "approve"|"defer"|"veto", "reason": str}}, ...]}}"""

_PM_SYS = """You are the PORTFOLIO MANAGER of an Indian equity paper-trading desk.
Charter: {charter}

Decide today's orders. You may ONLY act on proposals the Risk officer APPROVED
(list provided). You may drop approved proposals; you may not add new names.
Position sizing is fixed by the system (one standard slot per buy; sells close
the full position). For every order write:
- thesis: what you believe and which Atlas evidence supports it (one sentence);
- invalidation: the observable condition that proves you wrong and triggers exit
  (e.g. "composite < 60 for 5 sessions or sector drops from top-3").
Doing nothing is a decision — if you place no orders, say why in the note.
Output ONLY JSON:
{{"orders": [{{"symbol": str, "side": "buy"|"sell",
  "thesis": str, "invalidation": str}}, ...], "note": str}}"""


def _msgs(system: str, payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, default=str)},
    ]


def build_scout_messages(charter_key: str, inputs: dict) -> list[dict]:
    return _msgs(_SCOUT_SYS.format(charter=CHARTERS[charter_key]), inputs)


def build_risk_messages(inputs: dict) -> list[dict]:
    return _msgs(_RISK_SYS, inputs)


def build_pm_messages(charter_key: str, inputs: dict) -> list[dict]:
    return _msgs(_PM_SYS.format(charter=CHARTERS[charter_key]), inputs)


# ── validators: strict shape checks; any violation rejects the whole reply ──


def _str(x) -> bool:
    return isinstance(x, str) and 0 < len(x) <= 2000


def validate_scout(out: dict, known_symbols: set[str]) -> list[str]:
    errs = []
    props = out.get("proposals")
    if not isinstance(props, list) or len(props) > 5:
        return ["proposals must be a list of ≤5"]
    for p in props:
        if not isinstance(p, dict) or p.get("action") not in ("add", "exit", "watch"):
            errs.append(f"bad proposal shape/action: {p}")
        elif not _str(p.get("symbol", "")) or p["symbol"] not in known_symbols:
            errs.append(f"unknown symbol: {p.get('symbol')}")
        elif not isinstance(p.get("evidence"), list) or not p["evidence"]:
            errs.append(f"{p['symbol']}: evidence required")
        elif p.get("urgency") not in ("low", "high"):
            errs.append(f"{p['symbol']}: bad urgency")
    return errs


def validate_risk(out: dict, proposed_symbols: set[str]) -> list[str]:
    errs = []
    vs = out.get("verdicts")
    if not isinstance(vs, list):
        return ["verdicts must be a list"]
    for v in vs:
        if not isinstance(v, dict) or v.get("verdict") not in ("approve", "defer", "veto"):
            errs.append(f"bad verdict shape: {v}")
        elif v.get("symbol") not in proposed_symbols:
            errs.append(f"verdict for unproposed symbol: {v.get('symbol')}")
        elif not _str(v.get("reason", "")):
            errs.append(f"{v['symbol']}: reason required")
    return errs


def validate_pm(out: dict, approved: dict[str, str]) -> list[str]:
    """approved: symbol -> action ('add'/'exit') that survived Risk review."""
    errs = []
    orders = out.get("orders")
    if not isinstance(orders, list):
        return ["orders must be a list"]
    for o in orders:
        if not isinstance(o, dict) or o.get("side") not in ("buy", "sell"):
            errs.append(f"bad order shape/side: {o}")
            continue
        sym = str(o.get("symbol") or "")
        want = "add" if o["side"] == "buy" else "exit"
        if approved.get(sym) != want:
            errs.append(f"{sym}: {o['side']} was not Risk-approved")
        if not _str(o.get("thesis", "")) or not _str(o.get("invalidation", "")):
            errs.append(f"{sym}: thesis and invalidation required")
    return errs
