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
import json
import re
import subprocess
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


def missing_support(ema_cross_src: str) -> list[str]:
    """Which of the keywords RULES writes are NOT accepted by this EmaCross source.

    Params are only half a switch-on; the code that has to honour them is the other
    half. On 2026-07-31 the params went live while `main` was still the docs-only spec
    commit, and the DB started asking a box for `EmaCross(exit=..., entry_confirm=...)`
    it could not construct — a TypeError on all four books at the next mark, silent
    because portfolio_mark is a step and the failure alert had just been removed.
    """
    sig_start = ema_cross_src.find("def __init__(")
    if sig_start == -1:
        return sorted(json.loads(RULES))  # no constructor found — assume nothing works
    sig = ema_cross_src[sig_start : ema_cross_src.find(")", sig_start)]
    return sorted(k for k in json.loads(RULES) if k not in sig)


def main_branch_source() -> str | None:
    """EmaCross as it exists on origin/main — the box tracks main, so this is the code
    that will actually meet these params tonight. None if git cannot answer."""
    try:
        # S603: every argument is a literal constant and shell=False — there is no
        # input here to be untrusted. Same reasoning the repo already applies to
        # tests/** ("subprocess the project's own binary, no untrusted input").
        r = subprocess.run(
            ["git", "show", "origin/main:atlas/portfolio/strategies/ema_cross.py"],
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=30,
            check=False,
        )
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def assert_code_is_deployed(force: bool) -> None:
    """Refuse to write params that the deployed code cannot honour."""
    # S603: literal argv, constant cwd, shell=False. No untrusted input.
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=REPO, timeout=60, check=False)
    src = main_branch_source()
    if src is None:
        print("  ! could not read origin/main — skipping the code check")
        return
    missing = missing_support(src)
    if not missing:
        print("  ok: origin/main carries the code these params need")
        return
    msg = (
        f"REFUSING: origin/main's EmaCross does not accept {missing}.\n"
        "The box tracks main, so applying these params would make the next nightly mark\n"
        "fail with a TypeError on every stock crossover book — silently, because\n"
        "portfolio_mark is a step, not a gate.\n"
        "Merge the crossover v2 code to main and let the box deploy it FIRST."
    )
    if not force:
        raise SystemExit(msg)
    print(f"  ! --force: proceeding anyway\n{msg}")


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
    ap.add_argument(
        "--force",
        action="store_true",
        help="apply even if origin/main lacks the code (you will break the nightly mark)",
    )
    a = ap.parse_args()

    if not (a.dry_run or a.rollback):
        # params are only half a switch-on; the deployed code is the other half
        assert_code_is_deployed(a.force)

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
