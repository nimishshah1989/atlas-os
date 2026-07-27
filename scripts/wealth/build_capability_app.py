"""Build the Jhaveri capability app — thin CLI shim over the `capability_app`
package (Task 7). Reads the live wealth.* tables at build time via
`capability_app.data.fetch_book(conn)`, renders the three pages (Holdings,
Behaviour, Client 360) via `capability_app.page_*` + `capability_app.render`,
and writes ONE self-contained, CSP-safe HTML file. Rule #0: every number on
screen is computed from the DB inside `fetch_book()` — nothing invented here.

Routes: #holdings (Q1-Q7) · #behaviour (B1-B5) · #client/<id> (Client 360,
one full detail page per id in SAMPLE_CLIENT_IDS below).

Byte-cap reality (measured at Task 7): the full 217-client `client360`
payload alone is ~13.7MB of JSON — before HTML markup, CSS, or chart JS —
which blows past the plan's ≤8MB file cap on its own. Every #client/<id>
route has to be a literal DOM block (constraint 6: no fetch, no CDN, one
self-contained file) — so "render every client" isn't a stylistic choice,
it's a hard byte-budget wall. Book-level Q1-Q7/B1-B5 exhibits + the
searchable client_index table already cover all 217 clients' summary
numbers; only the 3 ids below get a full #client/<id> detail page.
client_link() still points every client id shown anywhere at #client/<id> —
clicking one of the other 214 is a no-op scroll (no matching id="client/N"
element), not a broken link or a console error; this is the same limitation
Task 6 shipped and gated (validate_wealth_app.py's browse routes only ever
covered these 3 real ids).

Output: /home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html.
Not committed — lives outside the repo. Gate it with validate_wealth_app.py.
Constraint 7 (PII): this script's build is a preview for gating only — the
FM republishes the artifact, never this script's own author.

Usage: set -a; source .env; set +a; .venv/bin/python scripts/wealth/build_capability_app.py
"""

from __future__ import annotations

from pathlib import Path

from capability_app import page_behaviour, page_client, page_holdings, render
from capability_app.data import fetch_book
from engine_common import connect

OUT = Path("/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html")

# Real client ids picked from the live book (Task 6): one >=70% coverage
# curve, one <70% coverage curve, one flagged panic seller — see
# task-6-report.md for the live psql query that picked these.
SAMPLE_CLIENT_IDS = [4, 1, 36]


def main() -> int:
    conn = connect()
    try:
        book = fetch_book(conn)
    finally:
        conn.close()

    # The embedded JSON is a trimmed view of `book`: full q1-q7/b1-b5/
    # client_index (all 217 clients' summary numbers) + client360 for only
    # the 3 rendered sample ids (see module docstring — byte cap). The
    # page_*.render_*_page() calls below still take the FULL `book`, since
    # they index book["client360"][cid] themselves for just those 3 ids.
    holdings_keys = ("q1", "q2", "q3", "q4", "q5", "q6", "q7")
    behaviour_keys = ("b1", "b2", "b3", "b4", "b5")
    data = {k: book[k] for k in holdings_keys + behaviour_keys}
    data["client_index"] = book["client_index"]
    data["asof"] = book["asof"]
    data["n_transactions"] = book["n_transactions"]
    data["txn_years"] = book["txn_years"]
    data["client360"] = {cid: book["client360"][cid] for cid in SAMPLE_CLIENT_IDS}

    holdings_html = page_holdings.render_holdings_page(book)
    behaviour_html = page_behaviour.render_behaviour_page(book)
    client_html = page_client.render_client_page(book, client_ids=SAMPLE_CLIENT_IDS)

    html = render.render_document(
        data,
        {"holdings": holdings_html, "behaviour": behaviour_html, "client": client_html},
        active="holdings",
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    size = len(html.encode("utf-8"))
    print(
        f"wrote {OUT} ({size / 1e6:.2f} MB, {len(book['client_index']['rows'])} clients "
        f"in book, {len(SAMPLE_CLIENT_IDS)} rendered as full Client-360 pages "
        f"{SAMPLE_CLIENT_IDS})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
