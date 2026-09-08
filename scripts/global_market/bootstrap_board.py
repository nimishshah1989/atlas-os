#!/usr/bin/env python3
"""One command that puts the Global board's database credentials in place, end to end.

    python scripts/global_market/bootstrap_board.py            # do it
    python scripts/global_market/bootstrap_board.py --dry-run  # say what it would do

Everything here was a hand-run SQL paste and a hand-edited file, which is how a password ends
up in a chat log and a URL ends up on the wrong port. It does four things, all idempotent:

1. Mints a fresh password for the board's role and applies the role's grants. The role reads
   all of ``atlas_global`` and writes only the admin tables, and is REVOKEd from
   ``atlas_foundation`` — ADR-0006 enforced at the database, not on trust.
2. VERIFIES the credential by connecting AS that role through the transaction pooler and
   counting the scored universe. A password written to a file but never exercised is a deploy
   that fails at 3am on a page nobody is watching.
3. Writes ``frontend-global/.env.local`` at mode 600, PRESERVING any Supabase auth keys
   already in it, and never overwriting a ``GLOBAL_REVALIDATE_SECRET`` that already exists
   (the orchestrator holds the matching copy; changing one side silently breaks publishing).
4. Prints what is still missing and can only come from a browser.

THE PORT IS THE POINT. The board must reach Postgres on the TRANSACTION pooler (6543), never
the session pooler (5432): India's board holds 14 of the cluster's 15 session slots, and one
global process taking the last one stops the LIVE India board. The board's own ``db.ts``
refuses to start on 5432; this script builds the right URL so that refusal never has to fire.

The password is generated here, used here, written to a 600 file, and never printed — not to
the console, not to a log, not into the repo. Nobody has to see it for it to work.
"""

from __future__ import annotations

import argparse
import re
import secrets
import string
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import _gdb
import psycopg2

M = _gdb.M
REPO = Path(__file__).resolve().parents[2]
ENV_LOCAL = REPO / "frontend-global" / ".env.local"
FM_EMAIL = "nimish.shah1989@gmail.com"
TRANSACTION_POOLER_PORT = 6543

# Alphanumeric only, deliberately. A libpq URL carries the password percent-encoded and a
# .env file does not quote it, so a shell-special or a '@' turns a working credential into an
# unparseable one somewhere downstream. 40 characters of base62 is ~238 bits; the entropy is
# not the constraint, the number of places this string gets copied through is.
_ALPHABET = string.ascii_letters + string.digits

GRANTS = f"""
GRANT USAGE ON SCHEMA {M} TO atlas_global_app;
GRANT SELECT ON ALL TABLES IN SCHEMA {M} TO atlas_global_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA {M} GRANT SELECT ON TABLES TO atlas_global_app;
GRANT INSERT, UPDATE ON {M}.atlas_thresholds, {M}.atlas_thresholds_audit,
  {M}.etf_classification_override, {M}.app_user TO atlas_global_app;
REVOKE ALL ON SCHEMA atlas_foundation FROM atlas_global_app;
"""

VERIFY_SQL = f"""
SELECT count(*) FROM {M}.universe_snapshot
WHERE date = (SELECT max(date) FROM {M}.universe_snapshot) AND in_universe
"""


def board_url(admin_url: str, password: str) -> str:
    """The board's transaction-pooler URL, derived from the admin one rather than typed.

    Supabase's pooler takes the role name with the project ref appended
    (``postgres.<ref>`` → ``atlas_global_app.<ref>``), and typing that by hand is how a
    deploy spends an afternoon on ``password authentication failed``. The ref is read off the
    admin URL that is already working on this box, so it cannot disagree with reality.
    """
    parts = urlsplit(admin_url)
    if not parts.netloc or not parts.username or not parts.hostname:
        raise SystemExit(
            "ATLAS_DB_URL has no usable authority section — cannot derive the board URL"
        )
    ref = parts.username.split(".", 1)[1] if "." in parts.username else ""
    user = f"atlas_global_app.{ref}" if ref else "atlas_global_app"
    db = (parts.path or "/postgres").lstrip("/") or "postgres"
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{parts.hostname}:{TRANSACTION_POOLER_PORT}/{db}?sslmode=require"
    )


def apply_role(admin_url: str, password: str) -> None:
    """Mint the password and (re-)apply the grants. Idempotent: ALTER, not CREATE."""
    with psycopg2.connect(admin_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'atlas_global_app'")
        if cur.fetchone() is None:
            cur.execute("CREATE ROLE atlas_global_app LOGIN PASSWORD %s", (password,))
            print("  role atlas_global_app CREATED")
        else:
            cur.execute("ALTER ROLE atlas_global_app WITH LOGIN PASSWORD %s", (password,))
            print("  role atlas_global_app already existed — password reset")
        cur.execute(GRANTS)
        cur.execute(
            f"INSERT INTO {M}.app_user (email, role, display_name) VALUES (%s, 'fm', %s) "
            "ON CONFLICT (email) DO NOTHING",
            (FM_EMAIL, "Nimish"),
        )
        print(f"  grants applied; {FM_EMAIL} present in app_user as fm")


def verify(url: str) -> int:
    """Connect AS the board's role, through the pooler it will really use."""
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute(VERIFY_SQL)
        row = cur.fetchone()
        return int(row[0]) if row else 0


def verify_cannot_read_india(url: str) -> None:
    """The read that must FAIL. A grant is only proved by what it refuses.

    Its OWN connection, deliberately. The failing statement aborts its transaction, and
    sharing one with the count above would make a passing check depend on rollback ordering.

    ANY database refusal counts. Without USAGE on the schema Postgres raises
    InsufficientPrivilege, but a role that cannot see the schema at all can surface
    UndefinedTable instead, and here they mean the same thing. Only a statement that SUCCEEDS
    is a failure — catching one specific error class would have turned the other into a
    traceback on the one run that matters.
    """
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM atlas_foundation.instrument_master")
    except psycopg2.Error:
        return  # refused, which is the whole point
    finally:
        conn.rollback()
        conn.close()
    raise SystemExit(
        "REFUSING: atlas_global_app CAN read atlas_foundation. ADR-0006 is one schema per "
        "market with zero cross-references, and the REVOKE did not take. Do not deploy: the "
        "board would carry a live credential into the India market's data."
    )


def existing(path: Path) -> dict[str, str]:
    """What .env.local already holds, so auth keys and the publish secret survive a re-run."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
        if m and m.group(2):
            out[m.group(1)] = m.group(2)
    return out


def write_env(path: Path, url: str, keep: dict[str, str]) -> tuple[str, list[str]]:
    """Write .env.local at 600. Returns the publish secret and what is still missing."""
    secret = keep.get("GLOBAL_REVALIDATE_SECRET") or secrets.token_hex(32)
    supa_url = keep.get("NEXT_PUBLIC_SUPABASE_URL", "")
    supa_key = keep.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    path.write_text(
        "# frontend-global/.env.local — written by scripts/global_market/bootstrap_board.py.\n"
        "# Never committed. ATLAS_GLOBAL_BASE_PATH stays EMPTY: this board is served at the\n"
        "# root of its own host (docs/global/deploy-subdomain.md), not under a sub-path.\n"
        "ATLAS_GLOBAL_BASE_PATH=\n"
        f"ATLAS_GLOBAL_DB_URL={url}\n"
        f"GLOBAL_REVALIDATE_SECRET={secret}\n"
        f"NEXT_PUBLIC_SUPABASE_URL={supa_url}\n"
        f"NEXT_PUBLIC_SUPABASE_ANON_KEY={supa_key}\n"
    )
    path.chmod(0o600)
    missing = [
        k
        for k, v in (
            ("NEXT_PUBLIC_SUPABASE_URL", supa_url),
            ("NEXT_PUBLIC_SUPABASE_ANON_KEY", supa_key),
        )
        if not v
    ]
    return secret, missing


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="say what would happen; change nothing")
    args = ap.parse_args()

    admin = _gdb.psycopg2_url()
    print(f"[bootstrap] admin connection → {urlsplit(admin).hostname}, schema {M}")
    if args.dry_run:
        print("  would: reset atlas_global_app's password, apply grants, verify through the")
        print(f"  transaction pooler (:{TRANSACTION_POOLER_PORT}), and write {ENV_LOCAL}")
        return

    password = "".join(secrets.choice(_ALPHABET) for _ in range(40))
    apply_role(admin, password)
    url = board_url(admin, password)
    n = verify(url)
    print(
        f"  verified AS atlas_global_app through the transaction pooler "
        f"— {n:,d} instruments in universe"
    )
    verify_cannot_read_india(url)
    print("  verified it CANNOT read atlas_foundation (ADR-0006)")

    keep = existing(ENV_LOCAL)
    _, missing = write_env(ENV_LOCAL, url, keep)
    print(f"  wrote {ENV_LOCAL} (mode 600)")

    print("\n[bootstrap] DONE. The database half is finished and proven.")
    if missing:
        print("\n  STILL NEEDED — only a browser can give you these:")
        print("    Supabase → Project Settings → API. Paste both into")
        print(f"    {ENV_LOCAL}:")
        for k in missing:
            print(f"      {k}=")
        print("\n  Without them /health renders on real data and the board redirects to /login.")
    print("\n  Then:  ATLAS_GLOBAL_PORT=<free port>  bash scripts/ops/atlas_global_deploy.sh")
    print(
        "  Pick the port from `ss -ltnp` — NOT 3002 (India's rollback target) or 3004 (India live)."
    )


if __name__ == "__main__":
    main()
