"""Give every tradeable ETF a sector.

318 active ETFs carried a NULL `instrument_master.sector`, and `de_etf_master` covers
only 43 of them — so a model portfolio holding index/commodity ETFs rendered a large
slice of its weight as "Unmapped" on the sector pie.

An ETF's underlying exposure is encoded in its name ("ICICI PRUDENTIAL NIFTY AUTO ETF"),
so the sector is derivable. Vocabulary is 21 + 5 (FM, 2026-07-30): an ETF tracking a
sector index gets one of the 21 canonical `atlas_sector_master` names, so it shares a pie
slice with stocks in that sector; the ~75% with no equity sector at all get one of exactly
five asset-class labels — Gold, Silver, Debt, Broad Index, International.

Those five are deliberately NOT added to atlas_sector_master: the canonical-21 gate is
scoped to `asset_class='stock'` (see assign_sectors.py), so ETF labels never widen the
stock sector vocabulary. backfill() enforces that nothing else can appear.

Run: python3 -c "import etf_sector; etf_sector.backfill()"
"""

from __future__ import annotations

import re

import _db

# Ordered most-specific first: the FIRST pattern that matches wins. Order is the whole
# design — "NIFTY 1D RATE LIQUID" holds both a cash and an index token, and cash must
# win; "NIFTY 200 MOMENTUM 30" holds a cap and a factor token, and the factor must win.
_RULES: list[tuple[str, str]] = [
    # Commodities: the asset itself is the exposure.
    # Unanchored on purpose: vendor rows bury the metal mid-token ("AONESILVER").
    (r"GOLD", "Gold"),
    (r"SILVER", "Silver"),
    # Cash and debt must beat any index token in the same name.
    (r"LIQUID|\b1D RATE\b|OVERNIGHT|\bCASH\b", "Debt"),
    (r"\bG-?SEC\b|GILT|\bBOND\b|TREASURY|\bSDL\b|\bCORP DEBT\b|BHARATBOND", "Debt"),
    # Overseas trackers.
    (r"HANG ?SENG|NASDAQ|NYSE|FANG|\bS&P 500\b|\bUS \b|GLOBAL|WORLD|EMERGING", "International"),
    # Sectoral, onto the canonical 21.
    # Financial Services BEFORE Banking: "FINANCIAL SERVICES EX-BANK" contains "BANK".
    (r"FIN(ANCIAL)? ?SERV|\bBFSI\b|FINSERV", "Financial Services"),
    (r"\bBANK|\bBNK", "Banking"),
    (r"CAPITAL ?MARKET|INSURANCE", "Capital Markets"),
    (r"\bIT\b|\bTECH\b|TECHNOLOG", "IT"),
    (r"HEALTHCARE|\bHEALTH\b|\bHC\b", "Healthcare"),
    (r"PHARMA", "Pharma"),
    (r"\bMETAL", "Metal"),
    (r"REALTY|REAL ESTATE", "Realty"),
    (r"\bAUTO|AUTOMOTIVE|\bEV &", "Automobile"),
    (r"CHEMICAL", "Chemicals"),
    (r"\bOIL\b|\bGAS\b|PETRO", "Oil & Gas"),
    (r"ENERGY|\bPOWER\b", "Energy"),
    (r"DEFENCE|DEFENSE", "Defence"),
    (r"CONSUMPTION|\bFMCG\b|CONSUMER", "FMCG"),
    (r"INTERNET|\bDIGITAL\b", "Digital"),
    (r"INFRA", "Infrastructure"),
    (r"\bMEDIA\b", "Media"),
    (r"LOGISTIC", "Logistics"),
    (r"TOURISM|HOTEL", "Tourism"),
    # Diversified-equity baskets: a CPSE/MNC/manufacturing/commodity-equity basket and
    # a factor tilt all span many sectors, so none of the 21 describes them. They share
    # the Broad Index bucket rather than being forced onto their largest constituent.
    # \bVALUE (no trailing boundary) — "VALUEAXIS" is a vendor-mangled value fund.
    (
        r"MANUFACTURING|\bCPSE\b|\bPSE\b|BHARAT ?22|\bMNC\b|COMMODIT"
        r"|MOMENTUM|QUALITY|\bVALUE|\bQLITY\b|LOW ?VOL|LOWVOL|\bALPHA\b|EQUAL ?WEIGHT|\bALPL",
        "Broad Index",
    ),
]

# The closed exception set: exposures that are NOT an equity sector, so none of the
# canonical 21 can describe them truthfully. Calling a gold ETF "Metal" would imply
# equity beta it does not have, and calling a Nifty 50 ETF by its largest constituent
# sector would misstate a diversified holding — in a document that allocates capital,
# an honest asset-class label beats a forced sector. Every SECTORAL ETF still lands on
# one of the 21 (enforced in backfill()).
# FM decision 2026-07-30: exactly five, so the vocabulary stays small enough to read.
_NON_SECTORAL = {"Gold", "Silver", "Debt", "Broad Index", "International"}

# Anything that tracks a market-cap or broad-market index. Also the final fallback:
# an unrecognised ETF is far likelier to be a broad tracker than a sector bet, and a
# wrong-but-honest bucket beats a NULL that renders as "Unmapped".
_DEFAULT = "Broad Index"


# Fund-house names that collide with a sector pattern and must be removed before
# matching: "BAJAJ FINSERV NIFTY BANK ETF" tracks Nifty Bank, but the AMC's own name
# would otherwise classify it as Financial Services.
_AMC_NOISE = re.compile(r"BAJAJ ?FINSERV|BANK OF INDIA|CANARA ROBECO|UNION MUTUAL")


def etf_sector(symbol: str, name: str | None) -> str:
    """Classify one ETF. Matches on symbol + name because some vendor rows carry a
    mangled name ("AXISAMC-GOLDAXIS") where the exposure only shows in the symbol."""
    text = _AMC_NOISE.sub(" ", f"{symbol or ''} {name or ''}".upper())
    for pattern, sector in _RULES:
        if re.search(pattern, text):
            return sector
    return _DEFAULT


def backfill(dry_run: bool = False) -> dict:
    """Write a sector for every active ETF, derived from its name."""
    # de_etf_master.sector is deliberately NOT consulted. It covers only 42 of 318 and
    # supplies synonyms for names we already have canonically ("Banking & Financial" for
    # Banking, "Consumption" for FMCG) plus the useless "Sectoral" — which is exactly the
    # inconsistency this backfill exists to remove. Comparing all 42 against the derived
    # label (2026-07-30) showed 21 disagreements, 19 of which the derivation won; the two
    # it lost (FANG+ → International, "FINANCIAL SERVICES EX-BANK" → Financial Services)
    # became rules, so nothing is lost by deriving every row from one vocabulary.
    rows = _db.read_df(
        """
        SELECT i.instrument_id::text AS id, i.symbol, i.name
        FROM atlas_foundation.instrument_master i
        WHERE i.asset_class = 'etf' AND i.is_active
        ORDER BY i.symbol
        """
    )
    print(f"  active ETFs: {len(rows)}")

    assignments = [
        (str(iid), etf_sector(str(sym), None if nm is None else str(nm)))
        for iid, sym, nm in zip(rows["id"], rows["symbol"], rows["name"], strict=True)
    ]
    unresolved = [a for a in assignments if not a[1]]
    if unresolved:
        raise RuntimeError(f"classifier returned empty for {len(unresolved)} ETFs — fix the rules")

    # Consistency gate: every SECTORAL label must be one of the canonical 21, so an ETF
    # and a stock in the same sector share a pie slice. The asset-class labels below are
    # the closed, reviewed exception set — see _NON_SECTORAL.
    canonical = set(
        _db.read_df("SELECT sector_name FROM atlas_foundation.atlas_sector_master")["sector_name"]
    )
    stray = {s for _, s in assignments if s not in canonical and s not in _NON_SECTORAL}
    if stray:
        raise RuntimeError(
            f"labels that are neither canonical nor a reviewed exception: {sorted(stray)}"
        )

    if dry_run:
        from collections import Counter

        dist = Counter(s for _, s in assignments)
        print("  DRY RUN — no write. distribution:")
        for sector, n in dist.most_common():
            print(f"    {n:>4}  {sector}")
        return {"written": 0, "dry_run": True, "would_write": len(assignments)}

    with _db.engine().begin() as conn:
        from sqlalchemy import text

        for iid, sector in assignments:
            conn.execute(
                text(
                    "UPDATE atlas_foundation.instrument_master "
                    "SET sector = :s, updated_at = now() WHERE instrument_id = :i"
                ),
                {"s": sector, "i": iid},
            )
        after_null = conn.execute(
            text(
                "SELECT count(*) FROM atlas_foundation.instrument_master "
                "WHERE asset_class = 'etf' AND is_active AND (sector IS NULL OR sector = '')"
            )
        ).scalar()

    print(f"  wrote {len(assignments)} ETF sectors; still NULL after = {after_null}")
    if after_null:
        raise RuntimeError(f"{after_null} active ETFs still have no sector")
    return {"written": len(assignments), "after_null": after_null}


if __name__ == "__main__":
    import sys

    backfill(dry_run="--dry-run" in sys.argv)
