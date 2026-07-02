#!/usr/bin/env python3
"""Assign sector to active stocks in atlas_foundation.instrument_master (A2).

Durable, idempotent, chain-runnable. Runs AFTER build_universe.py (which writes
instrument rows but no sector) and is safe to re-run.

STAGE A2 — SAFE PART (FM-pre-approved COALESCE fallback, remediation plan A2):
  Fill sector for unmapped active stocks from `public.de_instrument.sector`, but
  ONLY where that raw sector is already one of the existing actionable sectors in
  instrument_master. The actionable set is self-defining (distinct current sectors),
  so this can NEVER introduce a new distinct sector — "≤21 canonical" stays green.
  Curated overrides on already-mapped rows are left untouched.

HELD FOR FM SIGN-OFF (methodology — NOT applied here; see backlog
docs/v4/2026-06-25-master-execution-backlog.md "BLOCKER surfaced 2026-06-25" and
memory v4-d13-taxonomy-mismatch):
  • the real 31→≤21 NSE thin-tail fold (Services/Diversified/Telecom/MNC/Power/…)
  • a source for the 111 active stocks with no de_instrument row (industry / index /
    extend-universe / gate-exclude).
These keep the remaining ~126 unmapped until the fold map is approved.
"""

from __future__ import annotations

import _db

_ACTIONABLE = """
  SELECT DISTINCT sector FROM atlas_foundation.instrument_master
  WHERE asset_class='stock' AND is_active AND sector IS NOT NULL AND sector <> ''
"""

# Safe COALESCE: de_instrument.sector fallback, restricted to the existing actionable
# set so distinct-sector count cannot grow.
_FILL_SAFE = f"""
  UPDATE atlas_foundation.instrument_master im
     SET sector = di.sector, updated_at = now()
    FROM public.de_instrument di
   WHERE di.symbol = im.symbol
     AND im.asset_class = 'stock' AND im.is_active
     AND (im.sector IS NULL OR im.sector = '')
     AND di.sector IN ({_ACTIONABLE})
"""


def _unmapped() -> int:
    return int(
        _db.scalar(
            "SELECT count(*) FROM atlas_foundation.instrument_master "
            "WHERE asset_class='stock' AND is_active AND (sector IS NULL OR sector='')"
        )
        or 0
    )


def _distinct() -> int:
    return int(
        _db.scalar(
            "SELECT count(DISTINCT sector) FROM atlas_foundation.instrument_master "
            "WHERE asset_class='stock' AND is_active AND sector IS NOT NULL AND sector<>''"
        )
        or 0
    )


def run() -> dict:
    before_unmapped, before_distinct = _unmapped(), _distinct()
    _db.exec_sql(_FILL_SAFE)
    after_unmapped, after_distinct = _unmapped(), _distinct()
    res = {
        "unmapped_before": before_unmapped,
        "unmapped_after": after_unmapped,
        "mapped": before_unmapped - after_unmapped,
        "distinct_before": before_distinct,
        "distinct_after": after_distinct,
    }
    print(res)
    if after_distinct > 21:
        raise SystemExit(f"GUARD TRIPPED: distinct sectors {after_distinct} > 21 — aborting")
    return res


if __name__ == "__main__":
    run()
