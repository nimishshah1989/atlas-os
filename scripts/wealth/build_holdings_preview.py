"""Task 4/5 throwaway build harness — produces a real Holdings+Behaviour
build of the wealth capability app so validate_wealth_app.py's Gate 1 has
something real to check today. Task 7 rewires build_capability_app.py into
the permanent thin shim over capability_app.render / page_holdings /
page_behaviour / page_client; this script is NOT that shim (no Client-360
page yet — client360 alone is ~12.8MB and would blow the 6MB cap) — delete
once Task 7 lands, or keep as a fast dev preview, FM's call. Kept the Task 4
filename rather than renaming: Task 6 will extend this same file again for
Client-360, and Task 7 replaces it outright.

Output: /home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html
(overwrites the old monolith's output — same convention, same file).

Usage: set -a; source .env; set +a; .venv/bin/python scripts/wealth/build_holdings_preview.py
"""

from __future__ import annotations

from pathlib import Path

from capability_app import page_behaviour, page_holdings, render
from capability_app.data import fetch_book
from engine_common import connect

OUT = Path("/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html")


def main() -> int:
    conn = connect()
    try:
        book = fetch_book(conn)
    finally:
        conn.close()
    # ponytail: Holdings+Behaviour read q1-q7/b1-b5 + client_index (shared)
    # + asof — client360 is the Client-360 page's data (Task 6) that would
    # otherwise blow the embed to ~12.8MB for pages that never read it.
    # Task 6's driver embeds the full book once that page actually renders it.
    holdings_keys = ("q1", "q2", "q3", "q4", "q5", "q6", "q7")
    behaviour_keys = ("b1", "b2", "b3", "b4", "b5")
    data = {k: book[k] for k in holdings_keys + behaviour_keys}
    data["client_index"] = book["client_index"]
    data["asof"] = book["asof"]
    data["n_transactions"] = book["n_transactions"]
    data["txn_years"] = book["txn_years"]
    holdings_html = page_holdings.render_holdings_page(book)
    behaviour_html = page_behaviour.render_behaviour_page(book)
    html = render.render_document(
        data, {"holdings": holdings_html, "behaviour": behaviour_html}, active="holdings"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(
        f"wrote {OUT} ({len(html.encode('utf-8')) / 1e6:.2f} MB) — "
        "Task 4/5 Holdings+Behaviour preview"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
