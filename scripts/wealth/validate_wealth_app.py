"""Post-build gate for the wealth capability app (glass-box redesign).

Runs AFTER a build (today: build_holdings_preview.py; Task 7 rewires
build_capability_app.py into the real multi-page shim). Written before the
builder existed so it FAILS red on the missing file, then goes green once
the app is emitted.

Checks (all must pass):
  1. output file exists
  2. the embedded <script id="data" type="application/json"> block parses
     under json.loads (strict — a NaN/Infinity token would raise)
  3. the literal token `NaN` appears nowhere in the JSON data embed (scoped
     to the embed, not the whole document — inline chart JS legitimately
     contains "NaN" as a substring of isNaN(...))
  4. byte size < 6 MB
  5. every exhibit id q1..q7 is present, both in the embed and as a rendered
     `id="qN"` exhibit in the Holdings page HTML
  6. every exhibit's `working` object round-trips through the embed with all
     five parts (inputs/rule/assumptions/steps/sample_rows) non-empty — q6 is
     the documented honest empty-state (constraint 3: no factsheet/SID feed),
     exempted from the four list parts but its `rule` text must still exist
  7. every headline number rendered inside `.kpi-value`/`.exhibit__verdict`
     also exists in the JSON data embed (raw, or its lakh/crore/rounded
     transform) — no JS-invented numbers
  8. zero occurrences of the deleted routes #book, #calls, #cohort,
     #segment/, #guide anywhere in the output HTML
  9. banned-word walk over all renderable JSON strings + rendered HTML text
  10. headless browse: ZERO console errors on #holdings
      (#behaviour / #client/<id> — TODO(Task 5/6): add once those routes
      exist; don't fake them here)
      (GSTACK_CHROMIUM_NO_SANDBOX=1, file copied under /tmp)

Usage: .venv/bin/python scripts/wealth/validate_wealth_app.py
Exit 0 = all green; non-zero = a specific failure printed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path("/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html")
MAX_BYTES = 6 * 1024 * 1024
BROWSE = Path.home() / ".claude/skills/gstack/browse/dist/browse"
DATA_RE = re.compile(r'<script id="data" type="application/json">(.*?)</script>', re.DOTALL)

# Jargon that must never reach a client-facing screen (plain-language rule).
BANNED = re.compile(r"\b(xirr|alpha|disposition|pgr|plr|counterfactual)\b", re.I)
# Keys whose VALUES are proper nouns (real fund/stock/person names — e.g. the
# fund literally named "Tata Nifty200 Alpha 30") or are embedded-but-never-
# rendered: excluded so the gate flags only jargon in narration we author.
SKIP_KEYS = {
    "name",
    "fund",
    "fund_a",
    "fund_b",
    "top_stock_name",
    "household_name",
    "full_name",
    "from",
    "to",
    "detail",
    "summary",
    "basis",
}


def renderable_strings(obj):
    """Yield string VALUES the app renders as prose/labels (dict keys, proper
    nouns and non-rendered fields excluded)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in SKIP_KEYS:
                yield from renderable_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from renderable_strings(v)
    elif isinstance(obj, str):
        yield obj


def banned_hits(data: dict, html: str) -> list[str]:
    """Banned words in the JSON blob's renderable fields + static HTML text."""
    hits = []
    for s in renderable_strings(data):
        m = BANNED.search(s)
        if m:
            hits.append(f"json[{m.group(0).lower()}]: …{s[max(0, m.start() - 20) : m.end() + 20]}…")
    # static HTML text nodes (strip <script>/<style> — those are code/CSS)
    stripped = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.I)
    text = re.sub(r"<[^>]+>", " ", stripped)
    for m in BANNED.finditer(text):
        hits.append(
            f"html-text[{m.group(0).lower()}]: …{text[max(0, m.start() - 20) : m.end() + 20]}…"
        )
    return hits


def fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def extract_data(html: str) -> dict:
    m = DATA_RE.search(html)
    if not m:
        raise ValueError('no <script id="data" type="application/json"> block found')
    return json.loads(m.group(1))  # strict: NaN/Infinity -> raises


def browse_routes(html_path: Path, routes: list[str]) -> list[str]:
    """Return list of 'route: error' strings for routes with console errors."""
    env = {**os.environ, "GSTACK_CHROMIUM_NO_SANDBOX": "1"}
    url = html_path.as_uri()
    problems = []

    def run(*args):
        # BROWSE is a fixed local binary path, not attacker-controlled input.
        return subprocess.run(  # noqa: S603
            [str(BROWSE), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )

    for i, route in enumerate(routes):
        # distinct query string forces a full reload so each route's router
        # run gets a clean console (hash-only changes don't reload).
        target = f"{url}?r={i}#{route}"
        nav = run("goto", target)
        if nav.returncode != 0 or "(200)" not in nav.stdout:
            problems.append(
                f"#{route}: navigation failed ({nav.stdout.strip()} {nav.stderr.strip()})"
            )
            continue
        run("wait", "--load")
        con = run("console", "--errors")
        out = con.stdout
        if "(no console errors)" not in out:
            # strip the untrusted-content wrapper lines for a compact report
            body = "\n".join(
                l for l in out.splitlines() if "UNTRUSTED EXTERNAL CONTENT" not in l
            ).strip()
            problems.append(f"#{route}: {body}")
        run("console", "--clear")
    run("stop")
    return problems


EXHIBIT_IDS = tuple(f"q{i}" for i in range(1, 8))
WORKING_LIST_PARTS = ("inputs", "assumptions", "steps", "sample_rows")
DELETED_ROUTES = ("#book", "#calls", "#cohort", "#segment/", "#guide")


def _collect_numbers(obj: object, out: set[float] | None = None) -> set[float]:
    """Every numeric leaf in the embedded JSON, walked recursively."""
    if out is None:
        out = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, int | float):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_numbers(v, out)
    return out


def _number_traceable(n: float, pool: set[float], tol: float = 0.05) -> bool:
    """n is traceable if it equals a raw embed value, or that value's
    lakh/crore/rounded transform (the same transforms lcr_py/enIN apply when
    turning a raw rupee figure into display text). Crore/lakh transforms get
    a wider tolerance (0.5) because some call sites format with 0 decimals
    (":.0f") rather than lcr_py's 2 — a legitimate display choice, not drift."""
    for x in pool:
        if (
            abs(n - x) <= tol
            or abs(n - round(x)) <= tol
            or abs(n - round(x / 1e5, 2)) <= 0.5
            or abs(n - round(x / 1e7, 2)) <= 0.5
        ):
            return True
    return False


def main() -> int:
    if not APP.exists():
        return fail(f"{APP} does not exist (run scripts/wealth/build_holdings_preview.py first)")

    html = APP.read_text(encoding="utf-8")
    size = len(html.encode("utf-8"))
    if size >= MAX_BYTES:
        return fail(f"file is {size / 1e6:.2f} MB (>= 6 MB cap)")

    m = DATA_RE.search(html)
    if not m:
        return fail('no <script id="data" type="application/json"> block found')
    # scoped to the data embed's raw text, not the whole document — inline
    # chart JS legitimately contains "NaN" as a substring of isNaN(...).
    if "NaN" in m.group(1):
        return fail("literal token 'NaN' present in data embed (strict-JSON violation)")

    try:
        data = extract_data(html)
    except Exception as e:
        return fail(f"embedded JSON did not parse: {e}")

    # ---- (a) every exhibit id q1..q7 present, in embed and rendered HTML ----
    for qid in EXHIBIT_IDS:
        if qid not in data:
            return fail(f"embedded data missing exhibit '{qid}'")
        if f'id="{qid}"' not in html:
            return fail(f"exhibit '{qid}' not rendered in HTML (no id=\"{qid}\")")

    # ---- (b) working object round-trips with all five parts non-empty ----
    # q6 is the documented honest empty-state (constraint 3: no factsheet/SID
    # feed exists) — its rule is real text but inputs/assumptions/steps/
    # sample_rows are legitimately [] by design, so it's exempted from the
    # four list-part checks (its working dict must still exist + have a rule).
    for qid in EXHIBIT_IDS:
        working = data[qid].get("working")
        if not isinstance(working, dict):
            return fail(f"exhibit '{qid}' has no working object")
        if not working.get("rule"):
            return fail(f"exhibit '{qid}'.working.rule is empty")
        if qid == "q6":
            continue
        for part in WORKING_LIST_PARTS:
            if not working.get(part):
                return fail(f"exhibit '{qid}'.working.{part} is empty")

    # ---- (c) headline numbers traceable to the JSON embed ----
    embed_numbers = _collect_numbers(data)
    embed_text = m.group(1)  # raw JSON text — verdict/message strings are
    # stored here verbatim, so a digit token from one of them (e.g. a date
    # like "2026", or a count baked into a pre-composed sentence) is already
    # traceable to real data even though it isn't a standalone numeric leaf.
    # NOTE: this must be a delimited-token match, not a bare substring test —
    # "12" is not traceable just because "112233" appears somewhere in a
    # 500KB JSON blob. `(?<!\d)...(?!\d)` anchors each token to its full
    # contiguous digit run, so "112233" only ever matches "112233", never "12".
    embed_number_tokens = {
        t.replace(",", "") for t in re.findall(r"(?<!\d)\d[\d,]*\.?\d*(?!\d)", embed_text)
    }
    headline_texts = re.findall(r'kpi-value">(.*?)</div>', html) + re.findall(
        r'exhibit__verdict">(.*?)</p>', html
    )
    untraceable = []
    for text in headline_texts:
        plain = re.sub(r"<[^>]+>", "", text)
        for tok in re.findall(r"\d[\d,]*\.?\d*", plain):
            if tok.replace(",", "") in embed_number_tokens:
                continue
            n = float(tok.replace(",", ""))
            if n and not _number_traceable(n, embed_numbers):
                untraceable.append((plain.strip()[:60], tok))
    if untraceable:
        print(f"FAIL: {len(untraceable)} headline number(s) not traceable to the JSON embed:")
        for t in untraceable[:15]:
            print(f"  - {t}")
        return 1

    # ---- (d) deleted routes fully gone ----
    for dead in DELETED_ROUTES:
        if dead in html:
            return fail(f"deleted route '{dead}' still referenced in output HTML")

    print(
        f"static checks PASS: {size / 1e6:.2f} MB, {len(EXHIBIT_IDS)} exhibits present, "
        f"working objects round-trip, {len(headline_texts)} headline figures traceable, "
        "strict JSON, no NaN, no deleted routes"
    )
    headroom = (MAX_BYTES - size) / 1e6
    print(f"byte-headroom watch: app {size / 1e6:.2f} MB, {headroom:.2f} MB under the 6 MB cap")

    # ---- banned-word gate (plain-language rule, defense-in-depth) ----
    hits = banned_hits(data, html)
    if hits:
        print(f"FAIL: {len(hits)} banned jargon word(s) in UI-visible text:")
        for h in hits[:15]:
            print(f"  - {h}")
        return 1
    print(
        "banned-word gate PASS: no xirr/alpha/disposition/pgr/plr/counterfactual in rendered text"
    )

    # ---- headless browse gate ----
    if not BROWSE.exists():
        return fail(f"browse binary not found at {BROWSE}")
    tmp = Path(tempfile.gettempdir()) / "jhaveri-capability-app.html"
    shutil.copy(APP, tmp)

    # TODO(Task 5/6): add "behaviour" and a few real "client/<id>" routes once
    # those pages exist — don't fake routes that aren't built yet.
    routes = ["holdings"]
    problems = browse_routes(tmp, routes)
    if problems:
        print("FAIL: console errors in headless browse:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"browse gate PASS: 0 console errors across {routes}")
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
