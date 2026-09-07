#!/usr/bin/env python3
"""Read-only board diagnostic — run ON THE BOX when the India board renders an empty panel.

Two failures got conflated on 2026-09-07 and this script separates them in one pass:

  P1  Market Pulse renders "No regime data" while atlas_market_regime_daily is full.
      MarketPulseV4 wraps every panel query in a catch that returned a fallback and
      logged nothing, so "the query threw" and "the query returned no rows" looked
      identical from outside, and the public URL sits behind an nginx cache that can
      serve a stale copy of either.
  P2  The nightly deploy is frozen. atlas_daily.sh rebuilds only when every gate()
      passes; validate_lenses --check B is a gate (validate_portfolios, validate_desk
      and validate_fund_categories are step() and never block), so B alone can hold
      the board on its last-good build indefinitely.

Reports. Asserts nothing, writes nothing, and prints no credential — the connection
string is read from the frontend's own env file so this exercises the SAME role,
host and port the board uses, which is the whole point: psql as the postgres
superuser proves nothing about what the app can see.

    uv run python scripts/ops/diagnose_board.py
"""

from __future__ import annotations

import re
import sys
import traceback
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

BOX_ROOT = Path(__file__).resolve().parents[2]
ENV_CANDIDATES = ("frontend/.env.local", "frontend/.env", ".env")
BOARD_URL = "http://localhost:3004"
EMPTY_PANEL_MARKER = "No regime data"

# The exact statement frontend/src/lib/queries/regime.ts sends. Kept verbatim so a
# difference here IS a difference the board would see.
REGIME_SQL = """
WITH latest_full AS (
  SELECT * FROM atlas_foundation.atlas_market_regime_daily
  WHERE pct_above_ema_50 IS NOT NULL ORDER BY date DESC LIMIT 1
),
latest_any AS (
  SELECT * FROM atlas_foundation.atlas_market_regime_daily
  ORDER BY date DESC LIMIT 1
)
SELECT la.date, la.regime_state, la.deployment_multiplier,
       COALESCE(la.pct_above_ema_50, lf.pct_above_ema_50) AS pct_above_ema_50
FROM latest_any la LEFT JOIN latest_full lf ON true
"""


def _find_db_url() -> tuple[str, str]:
    """Return (url, source_path). Prefers the frontend's env: that is the board's identity."""
    for rel in ENV_CANDIDATES:
        p = BOX_ROOT / rel
        if not p.exists():
            continue
        m = re.search(r"^\s*(?:export\s+)?ATLAS_DB_URL\s*=\s*(.+)$", p.read_text(), re.M)
        if m:
            return m.group(1).strip().strip("'\""), str(p)
    raise SystemExit(f"no ATLAS_DB_URL in any of {ENV_CANDIDATES} under {BOX_ROOT}")


def _redact(url: str) -> str:
    s = urlsplit(url)
    user = s.username or "?"
    return f"{user}@{s.hostname}:{s.port}/{(s.path or '/').lstrip('/')}"


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main() -> int:
    url, src = _find_db_url()
    print(f"connection taken from {src} -> {_redact(url)}")

    import psycopg2

    section("P1a — identity the BOARD connects as (not your psql session)")
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute(
            "select current_user, session_user, current_database(), current_setting('search_path')"
        )
        row = cur.fetchone() or ("?", "?", "?", "?")
        print(f"  current_user={row[0]}  session_user={row[1]}  db={row[2]}  search_path={row[3]}")

    section("P1b — the regime query, run as that role")
    try:
        with conn.cursor() as cur:
            cur.execute(REGIME_SQL)
            rows = cur.fetchall()
        print(f"  rows returned: {len(rows)}")
        for r in rows:
            print(
                f"    date={r[0]}  regime_state={r[1]}  deployment_multiplier={r[2]}  pct_above_ema_50={r[3]}"
            )
        if not rows:
            print("  -> ZERO ROWS. The board's null check fires and the empty panel is CORRECT")
            print("     behaviour for what this role can see. Look at row visibility for this")
            print("     role (RLS / GRANT), not at the pipeline.")
        else:
            print("  -> The query works for this role, so the board's null came from an")
            print("     EXCEPTION in the node layer, not from missing data.")
    except Exception:
        print("  -> The query RAISED. This is the error MarketPulseV4 was swallowing:")
        traceback.print_exc(file=sys.stdout)

    section("P1c — table visibility for this role")
    with conn.cursor() as cur:
        for q, label in (
            ("select count(*) from atlas_foundation.atlas_market_regime_daily", "total rows"),
            ("select max(date) from atlas_foundation.atlas_market_regime_daily", "max(date)"),
            (
                "select relrowsecurity from pg_class where oid = "
                "'atlas_foundation.atlas_market_regime_daily'::regclass",
                "RLS enabled",
            ),
            (
                "select has_table_privilege(current_user, "
                "'atlas_foundation.atlas_market_regime_daily', 'SELECT')",
                "has SELECT",
            ),
        ):
            try:
                cur.execute(q)
                fetched = cur.fetchone()
                print(f"  {label}: {fetched[0] if fetched else None}")
            except Exception as exc:  # a denied privilege is itself the answer
                print(f"  {label}: RAISED {type(exc).__name__}: {exc}")
                conn.rollback()

    section("P2 — the three assertions inside validate_lenses --check B")
    with conn.cursor() as cur:
        cur.execute("select count(distinct sector) from atlas_foundation.sector_lens_daily")
        fetched = cur.fetchone()
        print(
            f"  distinct sectors in sector_lens_daily: {fetched[0] if fetched else None}  (gate wants >= 20)"
        )

        cur.execute("""select symbol, name from atlas_foundation.instrument_master
                       where asset_class='stock' and kite_token is not null and is_active
                         and (sector is null or sector='') order by symbol""")
        unmapped = cur.fetchall()
        print(f"  active scored stocks with NO sector: {len(unmapped)}  (gate wants 0)")
        for sym, name in unmapped:
            print(f"      {sym:<16} {name}")

        cur.execute("""with latest as (select max(date) d from atlas_foundation.sector_lens_daily)
                       select s.sector, s.technical from atlas_foundation.sector_lens_daily s, latest
                       where s.date=latest.d and (s.technical < 0 or s.technical > 100)""")
        oob = cur.fetchall()
        print(f"  sector scores outside 0-100 on the latest date: {len(oob)}  (gate wants 0)")
        for sector, technical in oob:
            print(f"      {sector:<28} technical={technical}")
    conn.close()

    section("P1d — the board as served by node, BYPASSING the nginx cache")
    try:
        with urllib.request.urlopen(BOARD_URL, timeout=20) as resp:  # noqa: S310 — fixed localhost
            out = resp.read().decode("utf-8", "replace")
        hits = out.count(EMPTY_PANEL_MARKER)
        print(f"  {BOARD_URL}: {len(out)} bytes, '{EMPTY_PANEL_MARKER}' x{hits}")
        print(
            "  -> node itself is serving the empty panel."
            if hits
            else "  -> node serves DATA. The public URL is stale: an nginx/CDN cache, not the app."
        )
    except Exception as exc:
        print(f"  request to {BOARD_URL} failed: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
