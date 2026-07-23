"""Plain-language narration for wealth.audit_packs, with a number validator
that keeps the LLM honest against the payload it was given.

Consumes: wealth.audit_packs.payload (built by build_audit_packs.py — the
full 8-section dict, keys = SECTION_NAMES). Produces: wealth.audit_packs.prose
(jsonb: {section: prose_paragraph}, exactly the 8 SECTION_NAMES keys).

Design: every public function here takes the FULL client payload (all 8
sections), not just one section's slice — `section` only picks the primary
focus. This matches the validator rule literally ("...appear in
json.dumps(payload)...") and lets prose reference other sections for
personalization (e.g. the client's household name from payload["map"]).

Validator rule (exact, from the plan): extract number tokens from prose via
`re.findall(r"[\\d][\\d,]*\\.?\\d*", prose)`; strip commas to normalize. Any
token whose float value is < 10 is unchecked (fractions/percentages/small
counts are noise, not the numbers worth hallucination-checking). For tokens
>= 10: the normalized token must appear as a SUBSTRING of the comma-stripped
`json.dumps(payload)` text (this is what makes "15,625" match a payload float
serialized as 15625.0 — "15625" is a substring of "15625.0"), OR match an
L/cr-scaled form of some number literally present in the payload (payload
value / 1e5 or / 1e7, rounded to 1 or 2 decimals, equals the token — e.g.
payload 7835666.0 -> "78.36" via /1e5). Any banned word (case-insensitive)
is always a violation regardless of numbers.

Violations -> that section's prose is replaced with template_only(section,
payload) (a deterministic, self-validating fallback) and the incident is
counted in the run summary; the client's other sections are untouched.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

from build_audit_packs import SECTION_NAMES
from engine_common import connect
from psycopg2.extras import Json

BANNED_WORDS = ["XIRR", "alpha", "disposition", "PGR", "PLR", "counterfactual"]
_NUM_RE = re.compile(r"[\d][\d,]*\.?\d*")

LANGUAGE_RULES = """
Voice: warm, concrete, plain language for a real Indian investor reading
about their own money. Use "you"/"your" where it reads naturally. Money in
rupees using the ₹ symbol with L (lakh = 1e5) and cr (crore = 1e7) the
way Indian investors actually read numbers -- not raw unbroken digit
strings. No hedging filler ("it appears that", "generally speaking", "may
potentially").

NEVER use these words, in any form, anywhere in your prose:
XIRR, alpha, disposition, PGR, PLR, counterfactual.
Say instead: "yearly growth" (not XIRR), "ahead of / behind an index fund"
(not alpha), "sells winners, keeps losers" (not disposition/PGR/PLR),
"what-if" (not counterfactual).

Every number you write must be one of the exact figures given below for that
section (or a natural L/cr rewrite of one, e.g. 2500000 -> "₹25L"). Do not
invent, estimate, or round a number that isn't given. If a figure is a
share/fraction between 0 and 1 (e.g. a "share" field), describe it in words
("about a quarter", "well under half") rather than converting it to a
percentage digit -- percentage conversions you invent will not match the
source data and will be rejected.
""".strip()

SECTION_ANGLE = {
    "map": "Introduce the client: household, how much they have with us "
           "right now, how many funds and stocks that spans, how long "
           "they've been investing with us.",
    "label_check": "Tell them plainly whether their funds' names match what "
                    "those funds actually hold inside, and name any that "
                    "don't. If a mismatch has a coverage_note, say the check "
                    "is lower-confidence there rather than asserting drift "
                    "as settled fact.",
    "overlap": "Tell them how concentrated their real stock exposure is "
               "(effective independent bets -- the number that matters, not "
               "the fund count), their single biggest stock exposure in "
               "rupees, and which two funds duplicate each other the most.",
    "fees": "Tell them plainly whether any of their funds are quietly "
            "tracking an index while charging active fees, and what that is "
            "costing them a year -- or that none are, if so.",
    "benchmark": "Compare their actual yearly growth to what a plain Nifty "
                 "50 index fund would have given them, replaying the exact "
                 "same money moving in and out on the exact same dates. "
                 "Never say XIRR or alpha.",
    "habits": "Describe their investing behaviour honestly and kindly -- do "
              "they sell winners and keep losers during drops, chase hot "
              "funds, keep SIPs running, let dividends sit in cash instead "
              "of staying invested -- and what that has cost in what-if "
              "terms. Never say PGR, PLR, or disposition.",
    "value": "Tell them, in rupees, what the advice relationship has "
             "actually put in their pocket, versus what more is possible if "
             "a few habits change.",
    "actions": "Tell them plainly what to actually do next -- how many "
               "concrete actions are open, and the size of the tax-harvest "
               "opportunity this FY if any.",
}


def render_prompt(section: str, payload: dict) -> str:
    """Fixed per-section prompt fragment: the narrative angle + the exact
    figures the model may draw on for that section. `payload` is the FULL
    8-section client payload (personalization + validator both key off the
    whole thing); `section` selects the primary focus."""
    sub = payload.get(section, {})
    if sub.get("insufficient"):
        return (
            f"SECTION '{section}': no data available. Reason on file: "
            f"{sub.get('reason', 'not specified')!r}. Write ONE honest, "
            f"plain sentence telling the client why we can't check this "
            f"yet -- do not invent any numbers."
        )
    return (
        f"SECTION '{section}': {SECTION_ANGLE.get(section, '')}\n"
        f"Exact figures for this section (JSON, use only what's here): "
        f"{json.dumps(sub, default=str)}\n"
        f"Write ONE short paragraph (2-4 sentences)."
    )


def _payload_text(payload: dict) -> str:
    return json.dumps(payload, default=str).replace(",", "")


def validate(prose: str, payload: dict) -> list[str]:
    """Return a list of violation strings; empty list = clean prose."""
    violations = []
    lowered = prose.lower()
    for w in BANNED_WORDS:
        if w.lower() in lowered:
            violations.append(f"banned word: {w}")

    payload_text = _payload_text(payload)
    payload_numbers = None  # lazily built only if a scale-check is needed

    for tok in _NUM_RE.findall(prose):
        norm = tok.replace(",", "")
        try:
            val = float(norm)
        except ValueError:
            continue
        if val < 10:
            continue
        if norm in payload_text:
            continue
        if payload_numbers is None:
            payload_numbers = []
            for pv_tok in _NUM_RE.findall(payload_text):
                try:
                    payload_numbers.append(float(pv_tok.replace(",", "")))
                except ValueError:
                    pass
        matched = False
        for pv in payload_numbers:
            for scale in (1e5, 1e7):
                scaled = pv / scale
                if round(scaled, 1) == round(val, 1) or round(scaled, 2) == round(val, 2):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            violations.append(f"unsupported number: {tok}")
    return violations


def _fmt_rs(v) -> str:
    """Rupee amount -> Indian L/cr short form, rounded to 2 decimals (the
    precision validate()'s scale-check rounds to as well)."""
    if v is None:
        return "₹0"
    v = float(v)
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e7:
        return f"{sign}₹{av / 1e7:.2f}cr"
    if av >= 1e5:
        return f"{sign}₹{av / 1e5:.2f}L"
    if av >= 1000:
        return f"{sign}₹{av:,.0f}"
    return f"{sign}₹{av:.0f}"


def _client_name(payload: dict) -> str | None:
    try:
        return payload["map"]["household"]["name"]
    except (KeyError, TypeError):
        return None


def template_only(section: str, payload: dict) -> str:
    """Deterministic fallback text, built only from payload numbers already
    known to pass validate() (money via L/cr, counts/percents quoted as-is,
    fraction shares described in words, never converted to a percent digit)."""
    sub = payload.get(section, {})
    if sub.get("insufficient"):
        return f"We don't have enough data to check this yet: {sub.get('reason', 'reason not on file')}."

    if section == "map":
        hh = sub.get("household") or {}
        name = hh.get("name") or "Your household"
        mv = _fmt_rs(sub.get("total_mv"))
        parts = [f"{name}'s book is worth {mv} as of {sub.get('as_on_date')}"]
        if sub.get("n_funds") is not None and sub.get("n_stocks") is not None:
            parts.append(f"held across {sub['n_funds']} funds reaching into {sub['n_stocks']} stocks")
        if sub.get("tenure_years") is not None:
            parts.append(f"you've been investing with us for {sub['tenure_years']} years")
        return ", ".join(parts) + "."

    if section == "label_check":
        n, m = sub.get("n_funds_checked"), sub.get("n_mismatch")
        if m:
            return (f"We checked {n} of your funds against what they actually hold. "
                     f"{m} of them don't match their own label -- the fund's name says "
                     f"one thing, its real portfolio says another.")
        return f"We checked {n} of your funds against what they actually hold -- every one matches its own label."

    if section == "overlap":
        s = (f"Across your funds you really only have about {sub.get('eff_bets')} "
             f"independent bets running -- that's the number that matters, not the "
             f"fund count.")
        if sub.get("top_stock_name"):
            s += f" Your single biggest stock exposure is {sub['top_stock_name']} at {_fmt_rs(sub.get('top_stock_rs'))}."
        wp = sub.get("worst_fund_pair")
        if wp:
            s += f" {wp['fund_a']} and {wp['fund_b']} overlap the most, at {wp['overlap_pct']}%."
        return s

    if section == "fees":
        fee = sub.get("fee_save_yr_rs") or 0
        if fee > 0:
            return (f"You could save about {_fmt_rs(fee)} a year by moving out of "
                     f"funds that quietly track an index while charging active fees.")
        return "None of your funds are flagged as quietly tracking an index while charging active fees -- no fee saving sitting on the table here."

    if section == "benchmark":
        xc, xb, alpha = sub.get("xirr_client"), sub.get("xirr_bench"), sub.get("alpha") or 0
        direction = "ahead of" if alpha >= 0 else "behind"
        return (f"Replaying every rupee you put in and took out through a plain "
                f"Nifty 50 index fund instead, your money grew {xc}% a year with "
                f"us versus {xb}% a year in the index -- you're {abs(alpha)} "
                f"percentage points a year {direction} what a simple index fund "
                f"would have given you.")

    if section == "habits":
        bits = []
        bits.append("you tend to sell winners and keep losers during drops"
                     if (sub.get("panic_share") or 0) > 0
                     else "you have not sold into a downturn in your history with us")
        if sub.get("cf_no_panic_rs"):
            bits.append(f"that has cost you roughly {_fmt_rs(sub['cf_no_panic_rs'])} in what-if growth")
        if sub.get("cf_sip_alive_rs"):
            bits.append(f"SIPs that stopped early cost you about {_fmt_rs(sub['cf_sip_alive_rs'])} in what-if growth")
        if sub.get("div_leak_rs"):
            bits.append(f"{_fmt_rs(sub['div_leak_rs'])} in dividends were paid out in cash instead of staying invested")
        return "; ".join(bits).capitalize() + "."

    if section == "value":
        s = f"Over your time with us, the advice relationship has put roughly {_fmt_rs(sub.get('realized_total_rs'))} of real, realized value into your book."
        if sub.get("coaching_opportunity_rs"):
            s += f" There's a further {_fmt_rs(sub['coaching_opportunity_rs'])} still on the table if a few habits change."
        return s

    if section == "actions":
        s = f"There are {sub.get('n_actions')} concrete actions open on this account right now."
        tax = sub.get("tax")
        if tax and tax.get("n_gain_candidates"):
            s += (f" That includes {tax['n_gain_candidates']} tax-harvest candidates "
                  f"worth about {_fmt_rs(tax.get('tax_saved_if_harvested'))} in tax "
                  f"saved this FY.")
        return s

    return "No narration available for this section."


def _build_full_prompt(payload: dict) -> str:
    name = _client_name(payload)
    intro = f"You are writing for {name}, a real client, reading their own audit." if name else ""
    parts = [LANGUAGE_RULES, intro] if intro else [LANGUAGE_RULES]
    parts.append(
        "Respond with ONLY a single JSON object, no markdown fences, no "
        "commentary before or after it. Keys must be exactly these 8 "
        f"section names: {json.dumps(SECTION_NAMES)}. Each value is one "
        "short plain-text prose paragraph (2-4 sentences) for that section."
    )
    parts.extend(render_prompt(section, payload) for section in SECTION_NAMES)
    return "\n\n".join(parts)


def _call_claude(prompt: str) -> dict | None:
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text", "--tools", "", "--no-session-persistence"],
            input=prompt, capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def narrate(conn, client_id) -> dict:
    """Narrate one client: one `claude -p` call for all 8 sections, validate
    each, template_only-fallback any that fail, write prose, commit.
    Returns {"client_id":, "incidents": [(section, kind), ...]}."""
    cur = conn.cursor()
    cur.execute("select payload from wealth.audit_packs where client_id = %s", (client_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"no audit pack for client {client_id}")
    payload = row[0]

    parsed = _call_claude(_build_full_prompt(payload))
    prose, incidents = {}, []

    for section in SECTION_NAMES:
        text = parsed.get(section) if parsed else None
        if not isinstance(text, str) or not text.strip():
            prose[section] = template_only(section, payload)
            incidents.append((section, "malformed_json" if parsed is None else "missing_section"))
            continue
        violations = validate(text, payload)
        if violations:
            prose[section] = template_only(section, payload)
            for v in violations:
                kind = "banned_word" if v.startswith("banned word") else "unsupported_number"
                incidents.append((section, kind))
        else:
            prose[section] = text.strip()

    cur.execute("update wealth.audit_packs set prose = %s where client_id = %s",
                (Json(prose), client_id))
    conn.commit()
    return {"client_id": client_id, "incidents": incidents}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="narrate at most N clients (smoke runs)")
    args = ap.parse_args()

    conn = connect()
    cur = conn.cursor()
    q = "select client_id from wealth.audit_packs where prose is null order by client_id"
    if args.limit:
        q += f" limit {int(args.limit)}"
    cur.execute(q)
    client_ids = [r[0] for r in cur.fetchall()]

    fallback_sections = 0
    violation_counts: dict[str, int] = {}
    for cid in client_ids:
        result = narrate(conn, cid)
        for _section, kind in result["incidents"]:
            fallback_sections += 1
            violation_counts[kind] = violation_counts.get(kind, 0) + 1

    print(f"clients narrated: {len(client_ids)}")
    print(f"sections fallback-templated: {fallback_sections}")
    for kind, n in sorted(violation_counts.items()):
        print(f"  {kind}: {n}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
