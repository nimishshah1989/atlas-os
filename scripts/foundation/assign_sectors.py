#!/usr/bin/env python3
"""Guard the sector mapping of the active scored universe (A2).

Durable, idempotent, chain-runnable. Runs AFTER build_universe.py (which writes/refreshes
instrument rows but never touches `sector`) and is safe to re-run.

SOURCE OF TRUTH: `atlas_foundation.instrument_master.sector` IS the sector classification
now. The former raw fallback (`public.de_instrument.sector`) was dropped in the single-schema
consolidation, and no other per-stock sector source survived — every remaining sector-bearing
table (mv_stock_landscape, sector_lens_daily) is DERIVED from instrument_master, so filling
from it would be circular. There is therefore nothing to COALESCE from.

What this script does (RULE #0 — never fabricate a sector):
  • APPLY the FM-curated map below, and ONLY to rows whose sector is NULL/'' — an existing
    classification is never overwritten, so this is idempotent and safe to re-run.
  • REPORT the count + symbols of any active stock still with no sector (loud, so an NSE
    reconstitution that adds an un-sectored name is caught rather than silently scored blank).
  • GUARD that the distinct actionable-sector count stays ≤ 21 (the FM-locked canonical fold).
A still-unmapped name is surfaced here and is NON-FATAL, but note that
`validate_lenses.py --check B` GATES on it: an unmapped active stock blocks the nightly
deploy outright. Those two stances disagree, and on 2026-09-07 the disagreement froze the
board — eight names entered the index unmapped and the deploy stopped for days while this
script reported them politely each week. Curating a new name promptly is therefore not
housekeeping; it is what keeps the board publishing.
"""

from __future__ import annotations

import _db

_ACTIVE_STOCK = "FROM atlas_foundation.instrument_master WHERE asset_class='stock' AND is_active"


# ── the FM-curated fold ────────────────────────────────────────────────────────────────────
# symbol → (sector, why). Values MUST come from the 21-value FM-locked fold; the guard below
# refuses anything that would widen it.
#
# RULE #0 asks for the FM's explicit prior approval before a judgement like this is encoded.
# It was given on 2026-09-08: "you take the right judgement call on the sector". These eight
# entered the NIFTY 500 unmapped — five of them Vedanta demerger entities — and had frozen
# every nightly deploy through `validate_lenses --check B`. Each rationale is recorded so the
# FM can overrule a call by editing one line rather than re-deriving the reasoning.
CURATED: dict[str, tuple[str, str]] = {
    # Unambiguous — the company name states the sector.
    "VAML": ("Metal", "Vedanta Aluminium Metal — aluminium smelting"),
    "VISL": ("Metal", "Vedanta Iron and Steel"),
    "VOGL": ("Oil & Gas", "Vedanta Oil and Gas — upstream hydrocarbons"),
    "CORDELIA": ("Tourism", "Waterways Leisure Tourism — cruise operator"),
    # Judgement calls, each with the alternative that was rejected and why.
    "VEDPOWER": (
        "Energy",
        "Vedanta Power — generation. The fold carries Energy AND Oil & Gas as separate "
        "values, so Energy is the power/utilities bucket and Oil & Gas the hydrocarbons "
        "one. Infrastructure was rejected: it holds asset developers, not generators.",
    ),
    "TURTLEMINT": (
        "Financial Services",
        "Turtlemint Fintech Solutions — insurance distribution. Banking is banks and "
        "Capital Markets is brokers/exchanges/AMCs, so neither fits; Digital was rejected "
        "because the revenue is insurance commission, not a technology product.",
    ),
    "VOEPL": (
        "Consumer Durables",
        "Virtuoso Optoelectronics — contract manufacturer of finished consumer appliances. "
        "Capital Goods was rejected: the output is consumer product, not plant.",
    ),
    # The weakest of the eight, and flagged as such rather than dressed up.
    "KNACK": (
        "Chemicals",
        "Knack Packaging — polymer (polypropylene) converting into flexible packaging. "
        "LEAST CONFIDENT of the eight: packaging has no home in the 21-value fold, and "
        "Indian broker taxonomies split it between plastics/Chemicals and Capital Goods. "
        "Chemicals is chosen because the economics track polymer input costs. Revisit if "
        "the fold ever gains a Materials or Packaging value.",
    ),
}


def _unmapped_symbols() -> list[str]:
    df = _db.read_df(
        f"SELECT symbol {_ACTIVE_STOCK} AND (sector IS NULL OR sector='') ORDER BY symbol"
    )
    return list(df["symbol"])


def _known_sectors() -> set[str]:
    """The sector values the active universe already uses — the only legal targets."""
    df = _db.read_df(
        f"SELECT DISTINCT sector {_ACTIVE_STOCK} AND sector IS NOT NULL AND sector<>''"
    )
    return set(df["sector"])


def _distinct() -> int:
    return int(
        _db.scalar(
            f"SELECT count(DISTINCT sector) {_ACTIVE_STOCK} AND sector IS NOT NULL AND sector<>''"
        )
        or 0
    )


def _apply_curated() -> list[str]:
    """Fill ONLY empty sectors from CURATED. Returns the symbols actually written.

    The `sector IS NULL OR sector=''` predicate is what makes this idempotent and what makes
    it safe to leave in the weekly cron: a later FM re-classification through any other route
    is never clobbered by this map."""
    # A typo here — "Metals" for "Metal" — would mint a 22nd sector and trip the fold guard
    # AFTER the write. Refuse it BEFORE, against the values the table actually holds, so the
    # allowlist is real data rather than a second hardcoded copy of the fold that can drift.
    known = _known_sectors()
    unknown = sorted({sec for sec, _ in CURATED.values()} - known)
    if unknown:
        raise SystemExit(
            f"GUARD TRIPPED: CURATED names sector(s) absent from instrument_master: {unknown}. "
            f"Either the spelling is wrong or the FM fold has genuinely gained a value; "
            f"neither is something this script may decide."
        )

    written: list[str] = []
    for symbol, (sector, _why) in CURATED.items():
        before = _db.scalar(
            f"SELECT count(*) {_ACTIVE_STOCK} AND symbol=:s AND (sector IS NULL OR sector='')",
            {"s": symbol},
        )
        if not before:
            continue
        _db.exec_sql(
            "UPDATE atlas_foundation.instrument_master SET sector=:sec "
            "WHERE asset_class='stock' AND is_active AND symbol=:s "
            "AND (sector IS NULL OR sector='')",
            {"sec": sector, "s": symbol},
        )
        written.append(f"{symbol}->{sector}")
    return written


def run() -> dict:
    written = _apply_curated()
    if written:
        print(f"  curated sectors applied ({len(written)}): {', '.join(written)}")
    unmapped = _unmapped_symbols()
    distinct = _distinct()
    res = {"applied": len(written), "unmapped": len(unmapped), "distinct_sectors": distinct}
    print(res)
    if unmapped:
        print(
            f"  ⚠️  {len(unmapped)} active stock(s) have NO sector — curate in instrument_master "
            f"(FM fold map): {', '.join(unmapped)}"
        )
    if distinct > 21:
        raise SystemExit(f"GUARD TRIPPED: distinct sectors {distinct} > 21 — aborting")
    return res


if __name__ == "__main__":
    run()
