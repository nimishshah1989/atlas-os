"""Task 4 throwaway build harness — produces a real Holdings-only build of
the wealth capability app so validate_wealth_app.py's Gate 1 has something
real to check today. Task 7 rewires build_capability_app.py into the
permanent thin shim over capability_app.render / page_holdings /
page_behaviour / page_client; this script is NOT that shim (Holdings only,
no Behaviour/Client-360 pages yet) — delete once Task 7 lands, or keep as a
fast dev preview, FM's call.

Output: /home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html
(overwrites the old monolith's output — same convention, same file).

Usage: set -a; source .env; set +a; .venv/bin/python scripts/wealth/build_holdings_preview.py
"""

from __future__ import annotations

from pathlib import Path

from capability_app import page_holdings, render
from capability_app.data import fetch_book
from engine_common import connect

OUT = Path("/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html")


def main() -> int:
    conn = connect()
    try:
        book = fetch_book(conn)
    finally:
        conn.close()
    # ponytail: Holdings only reads q1-q7 + client_index + asof — b1-b5 and
    # client360 are Behaviour/Client-360 page data (Task 5/6) that would
    # otherwise blow the embed from ~200KB to ~12MB (client360 alone is
    # ~12.8MB) for a page that never reads them. Task 5/6's driver embeds
    # the full book once those pages actually render it.
    holdings_keys = ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "client_index", "asof")
    data = {k: book[k] for k in holdings_keys}
    holdings_html = page_holdings.render_holdings_page(book)
    html = render.render_document(data, {"holdings": holdings_html}, active="holdings")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html.encode('utf-8')) / 1e6:.2f} MB) — Task 4 Holdings-only preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
