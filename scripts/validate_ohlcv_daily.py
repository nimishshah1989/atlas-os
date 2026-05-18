#!/usr/bin/env python3
"""Daily OHLCV validation for JIP de_equity_ohlcv.

Promotes rows from ``data_status='raw'`` to ``'validated'`` after sanity checks:
  - open/high/low/close all > 0
  - high >= low, high >= open, high >= close, low <= open, low <= close
  - volume >= 0

Rows failing checks stay as ``'raw'`` — we do NOT mark them ``'invalid'``;
downstream Atlas compute already accepts ``data_status IN ('raw','validated')``,
so the validator's job is only to mark known-good rows. The original JIP
script lived at ``/home/ubuntu/validate_ohlcv_daily.py`` and got deleted
between 2026-05-14 and 2026-05-15 — restored here in the repo so disaster
recovery from git is possible.

The JIP cron at ``0 14 * * 1-5 /home/ubuntu/jip-data-engine/scripts/cron/validate_ohlcv.sh``
calls the EC2-side copy; keep this file in sync if either is edited.

Usage::

    python3 scripts/validate_ohlcv_daily.py
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text


def _load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                env[k.strip()] = v
    return env


def main() -> int:
    env = _load_env(Path("/home/ubuntu/atlas-os/.env"))
    db_url = env.get("ATLAS_DB_URL", "")
    if not db_url:
        print("ATLAS_DB_URL not set", file=sys.stderr)
        return 1

    engine = create_engine(db_url, pool_pre_ping=True)
    today = datetime.now(UTC).date()
    window_start = today - timedelta(days=10)

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE public.de_equity_ohlcv
                SET data_status = 'validated', updated_at = NOW()
                WHERE date BETWEEN :ws AND :we
                  AND data_status = 'raw'
                  AND open  > 0
                  AND high  > 0
                  AND low   > 0
                  AND close > 0
                  AND high  >= low
                  AND high  >= open
                  AND high  >= close
                  AND low   <= open
                  AND low   <= close
                  AND volume >= 0
            """),
            {"ws": window_start, "we": today},
        )
        n_validated = result.rowcount

    with engine.connect() as conn:
        through_date: date | None = conn.execute(
            text("SELECT MAX(date) FROM public.de_equity_ohlcv WHERE data_status = 'validated'")
        ).scalar()

    print(f"validate_ohlcv rows_validated={n_validated} through_date={through_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
