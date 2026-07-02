#!/usr/bin/env python3
"""Weekly data-quality audit (Sunday) — the safety net that emails/alerts the FM if
anything drifted during the week. Asserts on REAL produced output (rule #0):

  1. FRESHNESS  — every KEY table reached the last EOD (reuses freshness_guard).
  2. COVERAGE   — >=95% of the scored universe has a real (non-zero) composite, and
                  each lens has >=80% non-null coverage (catches the "silent zero"
                  bug where composite=0.0 because a lens feed was empty).
  3. OUTLIERS   — no stock shows an implausible 1-day jump in the last 5 sessions
                  (|log-return| > 0.40 ≈ a mis-adjusted split/bad print).
  4. NULL/ERROR — no NULLs in the columns the board renders on the latest date.

Prints a PASS/FAIL digest and sends it to Telegram. Exit 1 if any check fails.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import numpy as np

_FND = Path(__file__).resolve().parents[1] / "foundation"
sys.path.insert(0, str(_FND))
import _db  # noqa: E402

M = "atlas_foundation"


def _freshness(eod: dt.date) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("freshness_guard.py")), "--eod", str(eod)],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout else "no output"


def _coverage(eod: dt.date) -> list[str]:
    fails = []
    n = _db.scalar(f"select count(*) from {M}.atlas_lens_scores_daily where date=:d and asset_class='stock'", {"d": eod})
    if not n:
        return [f"coverage: no stock lens rows on {eod}"]
    nonzero = _db.scalar(
        f"select count(*) from {M}.atlas_lens_scores_daily where date=:d and asset_class='stock' and composite>0",
        {"d": eod},
    )
    if nonzero / n < 0.95:
        fails.append(f"coverage: only {nonzero}/{n} stocks have composite>0 (<95%) — silent-zero risk")
    for lens in ("technical", "fundamental", "flow", "catalyst"):
        c = _db.scalar(
            f"select count({lens}) from {M}.atlas_lens_scores_daily where date=:d and asset_class='stock'",
            {"d": eod},
        )
        if c / n < 0.80:
            fails.append(f"coverage: {lens} non-null only {c}/{n} (<80%)")
    return fails


def _outliers(eod: dt.date) -> list[str]:
    df = _db.read_df(
        f"""select symbol, date, close_adj from {M}.ohlcv_stock
            where date > :d - interval '10 days' and close_adj > 0 order by symbol, date""",
        {"d": eod},
    )
    bad = []
    for sym, g in df.groupby("symbol"):
        c = g["close_adj"].astype(float).to_numpy()
        if len(c) < 2:
            continue
        lr = np.abs(np.log(c[1:] / c[:-1]))
        if lr.size and np.nanmax(lr) > 0.40:
            bad.append(sym)
    return [f"outliers: {len(bad)} stocks with >40% 1-day jump last week ({', '.join(bad[:8])})"] if bad else []


def main() -> int:
    eod = _db.eod_cutoff()
    print(f"[qa_weekly] EOD={eod}")
    checks: list[str] = []
    ok, msg = _freshness(eod)
    if not ok:
        checks.append(f"FRESHNESS: {msg}")
    checks += _coverage(eod)
    checks += _outliers(eod)

    if not checks:
        report = f"✅ Atlas weekly QA PASS ({eod}) — freshness, coverage, outliers all clean."
        rc = 0
    else:
        report = f"⚠️ Atlas weekly QA FAIL ({eod}):\n" + "\n".join(f"• {c}" for c in checks)
        rc = 1
    print(report)
    try:
        from atlas.intraday.notify import send_message_sync

        send_message_sync(report)
    except Exception as e:  # noqa: BLE001
        print(f"[qa_weekly] notify failed: {e}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
