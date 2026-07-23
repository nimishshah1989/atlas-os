"""Post-build gate for the wealth capability app (Task 9).

Runs AFTER build_capability_app.py. Written before the builder existed so it
FAILS red on the missing file, then goes green once the app is emitted.

Checks (all must pass):
  1. output file exists
  2. the embedded <script id="data" type="application/json"> block parses
     under json.loads (strict — a NaN/Infinity token would raise)
  3. the literal token `NaN` appears nowhere in the file
  4. every client_id referenced anywhere (call_lists, chapters) resolves to a
     client present in `clients` (the datalist source)
  5. byte size < 6 MB
  6. headless browse: ZERO console errors on #book, #calls and 3 real
     #client/<id> pages (GSTACK_CHROMIUM_NO_SANDBOX=1, file copied under /tmp)

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
DATA_RE = re.compile(
    r'<script id="data" type="application/json">(.*?)</script>', re.DOTALL)


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
        return subprocess.run([str(BROWSE), *args], env=env,
                              capture_output=True, text=True, timeout=90)

    for i, route in enumerate(routes):
        # distinct query string forces a full reload so each route's router
        # run gets a clean console (hash-only changes don't reload).
        target = f"{url}?r={i}#{route}"
        nav = run("goto", target)
        if nav.returncode != 0 or "(200)" not in nav.stdout:
            problems.append(f"#{route}: navigation failed ({nav.stdout.strip()} {nav.stderr.strip()})")
            continue
        run("wait", "--load")
        con = run("console", "--errors")
        out = con.stdout
        if "(no console errors)" not in out:
            # strip the untrusted-content wrapper lines for a compact report
            body = "\n".join(l for l in out.splitlines()
                             if "UNTRUSTED EXTERNAL CONTENT" not in l).strip()
            problems.append(f"#{route}: {body}")
        run("console", "--clear")
    run("stop")
    return problems


def main() -> int:
    if not APP.exists():
        return fail(f"{APP} does not exist (run build_capability_app.py first)")

    html = APP.read_text(encoding="utf-8")
    size = len(html.encode("utf-8"))
    if size >= MAX_BYTES:
        return fail(f"file is {size/1e6:.2f} MB (>= 6 MB cap)")

    if "NaN" in html:
        return fail("literal token 'NaN' present in file (strict-JSON violation)")

    try:
        data = extract_data(html)
    except Exception as e:
        return fail(f"embedded JSON did not parse: {e}")

    for key in ("book", "chapters", "call_lists", "clients", "asof"):
        if key not in data:
            return fail(f"embedded data missing top-level key '{key}'")

    clients = data["clients"]
    client_ids = set(clients.keys())
    if not client_ids:
        return fail("no clients in embedded data")

    # every referenced client resolves to the datalist source (clients)
    referenced = set()
    for lst in data["call_lists"].values():
        referenced.update(str(r["id"]) for r in lst)
    for card in data["chapters"].get("ch4", []):
        for cid in card.get("sample_ids", []):
            referenced.add(str(cid))
    missing = referenced - client_ids
    if missing:
        return fail(f"{len(missing)} referenced client(s) not resolvable in datalist: "
                    f"{sorted(missing)[:10]}")

    # each client must carry a name (datalist label) and a pack
    for cid, c in clients.items():
        if not c.get("name"):
            return fail(f"client {cid} has no name for the datalist")
        if not c.get("pack"):
            return fail(f"client {cid} has no pack payload")

    print(f"static checks PASS: {size/1e6:.2f} MB, {len(client_ids)} clients, "
          f"{len(referenced)} referenced ids all resolvable, strict JSON, no NaN")

    # ---- headless browse gate ----
    if not BROWSE.exists():
        return fail(f"browse binary not found at {BROWSE}")
    tmp = Path(tempfile.gettempdir()) / "jhaveri-capability-app.html"
    shutil.copy(APP, tmp)

    sample = sorted(client_ids, key=lambda x: int(x))[:3]
    routes = ["book", "calls"] + [f"client/{cid}" for cid in sample]
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
