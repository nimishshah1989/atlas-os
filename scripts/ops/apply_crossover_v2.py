#!/usr/bin/env python3
"""Turn crossover v2 on (or off) in one command — see docs/adr/0005.

    .venv/bin/python scripts/ops/apply_crossover_v2.py --dry-run   # show, change nothing
    .venv/bin/python scripts/ops/apply_crossover_v2.py             # apply
    .venv/bin/python scripts/ops/apply_crossover_v2.py --rollback  # undo the params

Three steps, in this order, inside ONE transaction:

  1. schema   — portfolio_trades.composite_at_signal + the crossover_alerts table
  2. rules    — intraday / entry_confirm=close / exit=death_cross on the 4 STOCK books
  3. telegram — notify=true on 13/34 only

Order is load-bearing. If the params landed before the column, the very next nightly
mark would book a trade carrying `composite_at_signal` into a table without that column
and die on the INSERT. Doing both in one transaction removes the window entirely.

Every step is idempotent (IF NOT EXISTS, and `params || …` re-applies cleanly), so
running it twice is a no-op rather than a mess.

The 5 MF golden-cross books are excluded by the asset_classes filter and MUST stay
excluded: a fund prints one NAV a day, so it has no intraday, no high/low and no open.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import sqlalchemy as sa

REPO = Path(__file__).resolve().parents[2]
RULES = '{"intraday": true, "entry_confirm": "close", "exit": "death_cross"}'
STOCK_BOOKS = "strategy_key = 'ema_cross' AND asset_classes = '{stock}'"
NOTIFY_BOOK = "EMA Crossover 13/34"

SCHEMA_SQL = [
    """ALTER TABLE atlas_foundation.portfolio_trades
         ADD COLUMN IF NOT EXISTS composite_at_signal numeric(20,4)""",
    """CREATE TABLE IF NOT EXISTS atlas_foundation.crossover_alerts (
         alert_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
         portfolio_id  uuid NOT NULL
                       REFERENCES atlas_foundation.portfolio_master(portfolio_id),
         instrument_id uuid NOT NULL,
         symbol        text NOT NULL,
         direction     text NOT NULL CHECK (direction in ('buy','sell')),
         stage         text NOT NULL
                       CHECK (stage in ('provisional','confirmed','disarmed')),
         alert_date    date NOT NULL
                       DEFAULT (now() AT TIME ZONE 'Asia/Kolkata')::date,
         level         numeric(20,4) NOT NULL,
         quote         numeric(20,4) NOT NULL,
         ema_fast      numeric(20,4),
         ema_slow      numeric(20,4),
         created_at    timestamptz NOT NULL DEFAULT now(),
         CONSTRAINT crossover_alerts_dedup
           UNIQUE (portfolio_id, instrument_id, direction, stage, alert_date))""",
    """CREATE INDEX IF NOT EXISTS ix_crossover_alerts_portfolio_date
         ON atlas_foundation.crossover_alerts (portfolio_id, alert_date)""",
    """CREATE INDEX IF NOT EXISTS ix_crossover_alerts_instrument
         ON atlas_foundation.crossover_alerts (instrument_id)""",
]


def db_url() -> str:
    """The pooler URL, built from whichever .env carries ATLAS_DB_URL.

    The stored value points at db.<ref>.supabase.co:5432, which is IPv6-only and
    unreachable from macOS. The aws-1 pooler on 6543 is the path that works from a
    laptop — and it is aws-1, not aws-0, whatever the .env comment claims.
    """
    for rel in (".env", "frontend/.env.local"):
        f = REPO / rel
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if not line.startswith("ATLAS_DB_URL"):
                continue
            raw = line.split("=", 1)[1].strip().strip("\"'")
            m = re.match(
                r"postgresql(?:\+psycopg2)?://([^:]+):([^@]+)@db\.([^.]+)\.supabase\.co:\d+/(\w+)",
                raw,
            )
            if not m:
                return raw  # already a pooler URL, or some other host — use as given
            _user, pw, ref, name = m.groups()
            return (
                f"postgresql://postgres.{ref}:{pw}@aws-1-ap-south-1.pooler.supabase.com:6543/{name}"
            )
    raise SystemExit("ATLAS_DB_URL not found in .env or frontend/.env.local")


def show(conn) -> None:
    col = conn.execute(
        sa.text(
            """select count(*) from information_schema.columns
               where table_schema='atlas_foundation' and table_name='portfolio_trades'
                 and column_name='composite_at_signal'"""
        )
    ).scalar()
    tbl = conn.execute(
        sa.text(
            """select count(*) from information_schema.tables
               where table_schema='atlas_foundation' and table_name='crossover_alerts'"""
        )
    ).scalar()
    print(
        f"  schema: composite_at_signal={'yes' if col else 'NO'}  "
        f"crossover_alerts={'yes' if tbl else 'NO'}"
    )
    for r in conn.execute(
        sa.text(
            "select name, coalesce(params->>'entry_confirm','-') ec, "
            "coalesce(params->>'exit','-') ex, coalesce(params->>'intraday','-') intra, "
            "coalesce(params->>'notify','-') notify "
            f"from atlas_foundation.portfolio_master where {STOCK_BOOKS} order by name"
        )
    ):
        print(
            f"  {r.name:<24} entry={r.ec:<7} exit={r.ex:<12} intraday={r.intra:<5} notify={r.notify}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply (or roll back) crossover v2")
    ap.add_argument("--dry-run", action="store_true", help="print current state, change nothing")
    ap.add_argument("--rollback", action="store_true", help="remove the params (schema stays)")
    a = ap.parse_args()

    engine = sa.create_engine(db_url(), connect_args={"connect_timeout": 20})
    with engine.connect() as conn:
        print("BEFORE:")
        show(conn)
    if a.dry_run:
        print("\n--dry-run: nothing changed.")
        return

    with engine.begin() as conn:
        if a.rollback:
            # schema stays — it is additive and harmless; only behaviour is reverted
            n = conn.execute(
                sa.text(
                    "update atlas_foundation.portfolio_master set params = "
                    "params - 'intraday' - 'entry_confirm' - 'exit' - 'notify' "
                    f"where {STOCK_BOOKS}"
                )
            ).rowcount
            print(f"\nrolled back params on {n} book(s)")
        else:
            for stmt in SCHEMA_SQL:
                conn.execute(sa.text(stmt))
            print("\napplied: schema")
            n = conn.execute(
                sa.text(
                    f"update atlas_foundation.portfolio_master "
                    f"set params = params || '{RULES}'::jsonb where {STOCK_BOOKS}"
                )
            ).rowcount
            print(f"applied: rules on {n} stock crossover book(s)")
            n = conn.execute(
                sa.text(
                    "update atlas_foundation.portfolio_master "
                    "set params = params || '{\"notify\": true}'::jsonb where name = :n"
                ),
                {"n": NOTIFY_BOOK},
            ).rowcount
            print(f"applied: telegram on {n} book ({NOTIFY_BOOK})")

    with engine.connect() as conn:
        print("\nAFTER:")
        show(conn)
    print(
        "\nNext: rebuild the stored curves so they match the live rule —\n"
        "  PYTHONPATH=.:scripts/foundation .venv/bin/python "
        "scripts/foundation/portfolio_run.py backtest --all --years 8"
    )


if __name__ == "__main__":
    sys.exit(main())
