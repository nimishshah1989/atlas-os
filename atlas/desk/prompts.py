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
DISLOCATION_SUSPENDED. conviction is a 5-tier scale (1 = weak/marginal,
3 = solid, 5 = table-pounding) — your stated tier is later scored against the
realized outcome, so calibrate honestly. Output ONLY JSON:
{{"proposals": [{{"symbol": str, "action": "add"|"exit"|"watch",
  "evidence": [str, ...], "urgency": "low"|"high",
  "conviction": 1|2|3|4|5}}, ...], "note": str}}"""

# three stances, one officer prompt: the desk trades only where at least
# `desk_stance_consensus_min` of the three independent stances agree (enforced
# in code), and a 2/3 split sizes down — disagreement gates size, not prose.
RISK_STANCES = {
    "SAFE": "Your stance is CAPITAL PRESERVATION: when in doubt, defer or veto. "
    "Weight drawdown risk, crowding and tax friction over missed upside.",
    "NEUTRAL": "Your stance is BALANCED: judge each proposal strictly on the "
    "evidence and costs given, with no directional bias.",
    "RISKY": "Your stance is OPPORTUNITY COST: missing a strong move is also a "
    "loss. Approve when the evidence is real even if imperfect; veto only "
    "clear rule-breakers or thesis-free trades.",
}

_RISK_SYS = """You are the RISK & TAX OFFICER of an Indian equity paper-trading desk.
{stance}
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
Position sizing is fixed by the system (one standard slot per buy — halved in
code when the risk stances split 2/3; sells close the full position).
Your payload includes track_record: MEASURED rolling hit-rates and T+20 alpha
vs NIFTY 500 for this desk, its charter, sectors and decision kinds — weight
proposals from historically strong pockets more, and say so in the thesis when
you do. For every order write:
- thesis: what you believe and which Atlas evidence supports it (one sentence);
- invalidation: the observable condition that proves you wrong and triggers exit
  (e.g. "composite < 60 for 5 sessions or sector drops from top-3");
- conviction: 1-5 (scored later against the realized outcome — calibrate honestly).
Doing nothing is a decision — if you place no orders, say why in the note.
Output ONLY JSON:
{{"orders": [{{"symbol": str, "side": "buy"|"sell", "thesis": str,
  "invalidation": str, "conviction": 1|2|3|4|5}}, ...], "note": str}}"""


def _msgs(system: str, payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, default=str)},
    ]


def build_scout_messages(charter_key: str, inputs: dict) -> list[dict]:
    return _msgs(_SCOUT_SYS.format(charter=CHARTERS[charter_key]), inputs)


def build_risk_messages(inputs: dict, stance: str = "NEUTRAL") -> list[dict]:
    return _msgs(_RISK_SYS.format(stance=RISK_STANCES[stance]), inputs)


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
        elif p.get("conviction") not in (1, 2, 3, 4, 5):
            errs.append(f"{p['symbol']}: conviction 1-5 required")
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
        elif o.get("conviction") not in (1, 2, 3, 4, 5):
            errs.append(f"{sym}: conviction 1-5 required")
    return errs


# ── B3: Execution Trader — exit levels for PM buy orders ────────────────────

_TRADER_SYS = """You are the EXECUTION TRADER on an Indian equity paper-trading desk.
The PM has already decided WHAT to buy; you set the exit levels. For each buy
order you get real price levels: last_close (the entry reference), ema_21,
ema_50, ema_200, atr_14, low_20d, high_20d.

Rules:
- stop: a real support level BELOW last_close (an EMA, the 20-day low, or
  last_close minus a small ATR multiple) — never an arbitrary percentage.
- target: a realistic objective ABOVE last_close grounded in the given levels
  (e.g. prior 20-day high, or a level implying reward-to-risk >= {min_rr}).
- reward-to-risk (target - last_close) / (last_close - stop) must be >= {min_rr}.
- basis: one line naming WHICH level anchors the stop and target.
- Ground every number in the provided levels; never invent prices.
Output ONLY JSON:
{{"plans": [{{"symbol": str, "stop": number, "target": number, "basis": str}}, ...]}}"""


def build_trader_messages(inputs: dict, min_rr: float) -> list[dict]:
    return _msgs(_TRADER_SYS.format(min_rr=min_rr), inputs)


def validate_trader(out: dict, expected: set[str]) -> list[str]:
    errs = []
    plans = out.get("plans")
    if not isinstance(plans, list) or len(plans) > len(expected):
        return [f"plans must be list of <={len(expected)}"]
    for p in plans:
        if not isinstance(p, dict) or p.get("symbol") not in expected:
            errs.append(f"plan for unexpected symbol: {p}")
        elif not isinstance(p.get("stop"), (int, float)) or not isinstance(
            p.get("target"), (int, float)
        ):
            errs.append(f"{p['symbol']}: stop/target must be numbers")
        elif not _str(p.get("basis", "")):
            errs.append(f"{p['symbol']}: basis required")
    return errs


def check_plan(entry, stop, target, min_rr) -> tuple[float | None, list[str]]:
    """Pure sanity gate on a buy plan (Decimal in, code-enforced — never the model).
    Returns (reward_to_risk, errors); rr is None when the geometry is invalid."""
    if not stop < entry:
        return None, [f"stop {stop} must be below entry {entry}"]
    if not target > entry:
        return None, [f"target {target} must be above entry {entry}"]
    rr = float((target - entry) / (entry - stop))
    if rr < float(min_rr):
        return rr, [f"reward-to-risk {rr:.2f} below minimum {min_rr}"]
    return rr, []


# ── B2: Bull/Bear debate (contested moves only) + weekly Reflection ─────────

_DEBATE_SYS = """You are the {side} in a structured debate on an Indian equity
paper-trading desk. The desk is considering: {action_desc}.
Argue the strongest HONEST {stance} case, grounded ONLY in the provided Atlas
data — attack the weakest point of the opposing thesis. No invented facts.
Output ONLY JSON:
{{"points": [str, str, str], "confidence": 0.0-1.0}}"""


def build_debate_messages(side: str, action_desc: str, evidence: dict) -> list[dict]:
    stance = "supporting" if side == "BULL" else "opposing"
    return _msgs(_DEBATE_SYS.format(side=side, action_desc=action_desc, stance=stance), evidence)


def validate_debate(out: dict) -> list[str]:
    pts = out.get("points")
    conf = out.get("confidence")
    if not isinstance(pts, list) or not (1 <= len(pts) <= 4) or not all(_str(p) for p in pts):
        return ["points must be 1-4 non-empty strings"]
    if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        return ["confidence must be 0..1"]
    return []


_REFLECT_SYS = """You are the weekly REFLECTION of an Indian equity paper-trading
desk. Charter: {charter}

You are given: the desk's decisions with FORWARD outcomes (T+5/T+20/T+60 price
moves after each booked order, and what deferred/vetoed names did afterwards),
plus the desk's existing lessons with confidences.

Tasks:
1. For each EXISTING lesson, judge from this week's outcomes whether it was
   confirmed, contradicted, or untested → new confidence (0.1-0.95; small steps,
   ±0.1 max; untested decays slightly).
2. Write AT MOST 3 NEW lessons — only patterns the outcomes actually support,
   phrased as actionable guidance. No platitudes; cite the pattern. Each lesson
   gets a memory layer: "fast" = this week's regime/market observation (fades in
   weeks), "medium" = sector/style pattern (fades in months), "slow" = durable
   principle (near-permanent). Choose honestly — durable claims need repeated
   evidence.
3. If contrast_candidates are provided (your BEST and WORST stamped outcomes),
   extract the ONE conceptual difference between what worked and what failed —
   not a description, a transferable rule. Cite at least one symbol from each
   side. If none are provided, set contrast_insight to null.
Output ONLY JSON:
{{"updates": [{{"id": int, "confidence": float, "basis": str}}, ...],
  "new_lessons": [{{"lesson": str, "layer": "fast"|"medium"|"slow",
     "tags": {{"regime": str|null, "sector": str|null, "action": str|null}},
     "basis": str}}, ...],
  "contrast_insight": {{"insight": str, "layer": "fast"|"medium"|"slow",
     "best_cited": [str, ...], "worst_cited": [str, ...]}} | null}}"""


def build_reflect_messages(charter_key: str, inputs: dict) -> list[dict]:
    return _msgs(_REFLECT_SYS.format(charter=CHARTERS[charter_key]), inputs)


_LAYERS = ("fast", "medium", "slow")


def validate_reflect(
    out: dict, known_ids: set[int], contrast_syms: tuple[set[str], set[str]] | None = None
) -> list[str]:
    """contrast_syms = (best, worst) symbol sets when candidates were provided —
    the contrast insight must cite at least one real symbol from each side."""
    errs = []
    ups = out.get("updates", [])
    news = out.get("new_lessons", [])
    if not isinstance(ups, list) or not isinstance(news, list) or len(news) > 3:
        return ["updates must be a list and new_lessons a list of ≤3"]
    for u in ups:
        if not isinstance(u, dict) or u.get("id") not in known_ids:
            errs.append(f"update for unknown lesson id: {u}")
        elif (
            not isinstance(u.get("confidence"), (int, float)) or not 0.05 <= u["confidence"] <= 0.95
        ):
            errs.append(f"lesson {u.get('id')}: confidence out of range")
    for n in news:
        if not isinstance(n, dict) or not _str(n.get("lesson", "")) or not _str(n.get("basis", "")):
            errs.append(f"bad new lesson: {n}")
        elif n.get("layer") not in _LAYERS:
            errs.append(f"new lesson needs layer fast|medium|slow: {n.get('lesson', '')[:40]}")
    ci = out.get("contrast_insight")
    if contrast_syms is not None:
        best, worst = contrast_syms
        if not isinstance(ci, dict):
            errs.append("contrast_insight required when candidates provided")
        else:
            b, w = set(ci.get("best_cited") or []), set(ci.get("worst_cited") or [])
            if (
                not _str(ci.get("insight", ""))
                or ci.get("layer") not in _LAYERS
                or not b
                or not w
                or not b <= best  # every citation verbatim from the candidate list —
                or not w <= worst  # no decorated symbols like "MCX (sell)"
            ):
                errs.append("contrast_insight citations must come verbatim from candidates")
    return errs
