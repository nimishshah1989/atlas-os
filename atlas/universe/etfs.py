"""Atlas ETF universe builder.

Per methodology Section 3.1: domestic Indian ETFs covering Broad and Sectoral
themes. Theme classification per methodology 8.2:

- **Broad** — tracks Nifty 50/100/500/Next 50 / Midcap 150 / Sensex
- **Sectoral** — tracks a single NSE sector (Bank, IT, Pharma, etc.)
- **Thematic** — everything else (factor, smart-beta, gold, liquid, debt)

Universe strategy: CURATED_ETF_REGISTRY defines the canonical Broad + Sectoral
ETFs we always want tracked, regardless of JIP traded-value ranking. These are
merged with auto-detected high-liquidity ETFs from de_etf_master that are not
already in the curated list.  This guarantees sector coverage: for every NSE
sector index that has a tradable ETF, at least one entry exists in the universe.

Domestic filter: ``country='IN' AND exchange='NSE'`` — excludes US-listed India
ETFs (INDA, INDY, SMIN) and all foreign ETFs.

Note (verified 2026-05-06 against Supabase):
- ``de_etf_master.name`` is the ETF name column (not ``etf_name``)
- No ``fund_house`` column on JIP — kept NULL on atlas side
- No ``isin`` column on JIP — kept NULL
- ``category`` and ``asset_class`` are populated and useful for classification
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.config import Config
from atlas.db import get_engine

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Curated registry — the canonical Broad + Sectoral ETF universe
#
# Rules:
#   - ``linked_sector`` MUST match atlas_sector_master.sector_name exactly
#     (which comes from de_instrument.sector in JIP).
#   - ``linked_index`` is the short benchmark code (informational + used by
#     the ETF compute pipeline for sectoral benchmark resolution).
#   - ETFs in this list that are missing from de_etf_ohlcv need BHAV backfill
#     via scripts/etf_sector_backfill.py before compute runs.
#   - Add new entries here; do NOT add them only to the backfill script.
#
# Sectors currently without a liquid NSE ETF (no entry possible):
#   FMCG, Media, Capital Goods, Chemicals, Telecom, Infrastructure
# ---------------------------------------------------------------------------

CURATED_ETF_REGISTRY: tuple[dict, ...] = (
    # ── Broad — tracks major NSE indices ────────────────────────────────────
    {
        "ticker": "NIFTYBEES",
        "etf_name": "Nippon India ETF Nifty 50 BeES",
        "theme": "Broad",
        "linked_sector": None,
        "linked_index": "NIFTY50",
    },
    {
        "ticker": "JUNIORBEES",
        "etf_name": "Nippon India ETF Nifty Next 50 BeES",
        "theme": "Broad",
        "linked_sector": None,
        "linked_index": "NIFTYNXT50",
    },
    {
        "ticker": "SETFNIF50",
        "etf_name": "SBI ETF Nifty 50",
        "theme": "Broad",
        "linked_sector": None,
        "linked_index": "NIFTY50",
    },
    {
        "ticker": "SETFNN50",
        "etf_name": "SBI ETF Nifty Next 50",
        "theme": "Broad",
        "linked_sector": None,
        "linked_index": "NIFTYNXT50",
    },
    {
        "ticker": "LICNETFN50",
        "etf_name": "LIC MF Nifty 50 ETF",
        "theme": "Broad",
        "linked_sector": None,
        "linked_index": "NIFTY50",
    },
    {
        "ticker": "MID150BEES",
        "etf_name": "Nippon India ETF Nifty Midcap 150",
        "theme": "Broad",
        "linked_sector": None,
        "linked_index": "NIFTYMID150",
    },
    # ── Sectoral — Banking ──────────────────────────────────────────────────
    {
        "ticker": "BANKBEES",
        "etf_name": "Nippon India ETF Nifty Bank BeES",
        "theme": "Sectoral",
        "linked_sector": "Banking",
        "linked_index": "NIFTYBANK",
    },
    {
        "ticker": "PSUBNKBEES",
        "etf_name": "Nippon India ETF Nifty PSU Bank BeES",
        "theme": "Sectoral",
        "linked_sector": "Banking",
        "linked_index": "NIFTYPSUBANK",
    },
    # ── Sectoral — IT ───────────────────────────────────────────────────────
    {
        "ticker": "ITBEES",
        "etf_name": "Nippon India ETF Nifty IT BeES",
        "theme": "Sectoral",
        "linked_sector": "IT",
        "linked_index": "NIFTYIT",
    },
    {
        "ticker": "SBIETFIT",
        "etf_name": "SBI ETF Nifty IT",
        "theme": "Sectoral",
        "linked_sector": "IT",
        "linked_index": "NIFTYIT",
    },
    # ── Sectoral — Pharma ───────────────────────────────────────────────────
    {
        "ticker": "PHARMABEES",
        "etf_name": "Nippon India ETF Nifty Pharma",
        "theme": "Sectoral",
        "linked_sector": "Pharma",
        "linked_index": "NIFTYPHARMA",
    },
    # ── Sectoral — Healthcare ───────────────────────────────────────────────
    {
        "ticker": "HEALTHIETF",
        "etf_name": "Nippon India ETF Nifty Healthcare",
        "theme": "Sectoral",
        "linked_sector": "Healthcare",
        "linked_index": "NIFTYHEALTHCARE",
    },
    # ── Sectoral — Automobile ───────────────────────────────────────────────
    {
        "ticker": "AUTOBEES",
        "etf_name": "Nippon India ETF Nifty Auto",
        "theme": "Sectoral",
        "linked_sector": "Automobile",
        "linked_index": "NIFTYAUTO",
    },
    # ── Sectoral — Metal ────────────────────────────────────────────────────
    {
        "ticker": "METALIETF",
        "etf_name": "Nippon India ETF Nifty Metal",
        "theme": "Sectoral",
        "linked_sector": "Metal",
        "linked_index": "NIFTYMETAL",
    },
    # ── Sectoral — Energy ───────────────────────────────────────────────────
    {
        "ticker": "MOENERGY",
        "etf_name": "Motilal Oswal Nifty Energy ETF",
        "theme": "Sectoral",
        "linked_sector": "Energy",
        "linked_index": "NIFTYENERGY",
    },
    # ── Sectoral — Realty ───────────────────────────────────────────────────
    {
        "ticker": "MOREALTY",
        "etf_name": "Motilal Oswal Nifty Realty ETF",
        "theme": "Sectoral",
        "linked_sector": "Realty",
        "linked_index": "NIFTYREALTY",
    },
    # ── Sectoral — Financial Services ───────────────────────────────────────
    {
        "ticker": "FINIETF",
        "etf_name": "Nippon India ETF Nifty Fin Services",
        "theme": "Sectoral",
        "linked_sector": "Financial Services",
        "linked_index": "NIFTYFINSERVICE",
    },
    {
        "ticker": "SETFNIFBK",
        "etf_name": "SBI ETF Nifty Financial Services",
        "theme": "Sectoral",
        "linked_sector": "Financial Services",
        "linked_index": "NIFTYFINSERVICE",
    },
    # ── Sectoral — Consumer Durables ────────────────────────────────────────
    {
        "ticker": "CONSDURBEES",
        "etf_name": "Nippon India ETF Nifty Consumer Durables BeES",
        "theme": "Sectoral",
        "linked_sector": "Consumer Durables",
        "linked_index": "NIFTYCONSDURBL",
    },
    # ── Sectoral — Oil & Gas ────────────────────────────────────────────────
    {
        "ticker": "OILIETF",
        "etf_name": "Nippon India ETF Nifty Oil & Gas",
        "theme": "Sectoral",
        "linked_sector": "Oil & Gas",
        "linked_index": "NIFTYOILGAS",
    },
)

_CURATED_TICKERS: frozenset[str] = frozenset(e["ticker"] for e in CURATED_ETF_REGISTRY)

# Sectors that have at least one curated ETF — used for coverage logging.
_CURATED_SECTORS: frozenset[str] = frozenset(
    e["linked_sector"] for e in CURATED_ETF_REGISTRY if e["linked_sector"]
)


# ---------------------------------------------------------------------------
# Auto-detection helpers (used for supplementary non-curated ETFs)
# ---------------------------------------------------------------------------

_AUTO_DETECT_QUERY = """
    WITH recent_volume AS (
        SELECT
            o.ticker,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (o.close * o.volume))
                AS median_traded_value_60d
        FROM public.de_etf_ohlcv o
        WHERE o.date >= (CURRENT_DATE - INTERVAL '90 days')
          AND o.close IS NOT NULL AND o.volume IS NOT NULL
        GROUP BY o.ticker
        HAVING COUNT(*) >= 30
    )
    SELECT
        m.ticker,
        m.name             AS etf_name,
        m.asset_class,
        m.category,
        m.benchmark,
        m.inception_date,
        rv.median_traded_value_60d
    FROM public.de_etf_master m
    JOIN recent_volume rv ON rv.ticker = m.ticker
    WHERE m.is_active = TRUE
      AND m.country = 'IN'
      AND m.exchange = 'NSE'
      AND m.ticker != ALL(:exclude_tickers)
    ORDER BY rv.median_traded_value_60d DESC
    LIMIT 40
"""

_BROAD_KEYWORDS = (
    "NIFTY 50",
    "NIFTY50",
    "NIFTY 100",
    "NIFTY100",
    "NIFTY 500",
    "NIFTY500",
    "NIFTY NEXT 50",
    "NIFTYNEXT50",
    "NIFTY MID",
    "NIFTYMID",
    "MIDCAP",
    "MID CAP",
    "SENSEX",
    "BSE 100",
    "BSE100",
    "TOTAL MARKET",
    "TOTAL MKT",
)

# Substring → atlas_sector_master.sector_name.
# Sector names verified against JIP de_instrument.sector.
# Order matters: longer/more specific tokens must appear before shorter ones.
_SECTORAL_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("PSU BANK", "Banking"),
    ("PRIVATE BANK", "Banking"),
    ("PVT BANK", "Banking"),
    ("FINANCIAL SERVICES", "Financial Services"),
    ("FIN SERVICES", "Financial Services"),
    ("FIN SVCS", "Financial Services"),
    ("BANK", "Banking"),
    ("HEALTHCARE", "Healthcare"),
    ("PHARMA", "Pharma"),
    ("FMCG", "FMCG"),
    ("OIL & GAS", "Oil & Gas"),
    ("OIL AND GAS", "Oil & Gas"),
    ("OIL GAS", "Oil & Gas"),
    ("AUTO", "Automobile"),
    ("METAL", "Metal"),
    ("ENERGY", "Energy"),
    ("REALTY", "Realty"),
    ("MEDIA", "Media"),
    ("CONSUMER DURABLES", "Consumer Durables"),
    ("CONSR DURBL", "Consumer Durables"),
    ("CONSDURBL", "Consumer Durables"),
    ("INFRA", "Infrastructure"),
    ("IT", "IT"),  # last: short token, word-boundary check applied
)


def _classify_theme(etf_name: str | None, category: str | None) -> tuple[str, str | None]:
    """Return ``(theme, linked_sector)``. ``linked_sector`` only set for Sectoral."""
    name = (etf_name or "").upper()
    cat = (category or "").upper()
    haystack = f"{name} {cat}"

    for kw in _BROAD_KEYWORDS:
        if kw in haystack:
            return ("Broad", None)

    for kw, sector_name in _SECTORAL_KEYWORDS:
        if kw == "IT":
            tokens = haystack.replace("/", " ").replace("-", " ").split()
            if "IT" in tokens:
                return ("Sectoral", sector_name)
            continue
        if kw in haystack:
            return ("Sectoral", sector_name)

    return ("Thematic", None)


def build_etf_universe(engine: Engine | None = None) -> list[dict[str, object]]:
    """Return domestic Indian ETF universe rows.

    Primary source: CURATED_ETF_REGISTRY — always included.
    Secondary source: auto-detected ETFs from de_etf_master with sufficient
    OHLCV (≥30 trading days in last 90 calendar days), excluding curated tickers.

    Curated ETFs that are not yet in de_etf_ohlcv (awaiting BHAV backfill) are
    still included with asset_class/inception_date as None — they will be
    populated once the backfill runs and the universe is re-locked.
    """
    eng = engine or get_engine()

    # ── 1. Load OHLCV presence for curated tickers ───────────────────────────
    curated_tickers = list(_CURATED_TICKERS)
    with eng.connect() as conn:
        ohlcv_rows = conn.execute(
            text(
                "SELECT DISTINCT ticker FROM public.de_etf_ohlcv "
                "WHERE ticker = ANY(:tickers) "
                "  AND date >= CURRENT_DATE - INTERVAL '90 days'"
            ),
            {"tickers": curated_tickers},
        ).all()
    tickers_with_ohlcv: frozenset[str] = frozenset(r[0] for r in ohlcv_rows)

    # Optionally pull asset_class / inception_date from de_etf_master for
    # curated tickers that do have a master row.
    with eng.connect() as conn:
        master_rows = (
            conn.execute(
                text(
                    "SELECT ticker, asset_class, inception_date "
                    "FROM public.de_etf_master "
                    "WHERE ticker = ANY(:tickers) AND is_active = TRUE"
                ),
                {"tickers": curated_tickers},
            )
            .mappings()
            .all()
        )
    master_meta: dict[str, dict] = {r["ticker"]: dict(r) for r in master_rows}

    rows: list[dict[str, object]] = []

    # ── 2. Curated entries (always included) ─────────────────────────────────
    missing_ohlcv: list[str] = []
    for entry in CURATED_ETF_REGISTRY:
        ticker = entry["ticker"]
        meta = master_meta.get(ticker, {})
        if ticker not in tickers_with_ohlcv:
            missing_ohlcv.append(ticker)
        rows.append(
            {
                "ticker": ticker,
                "isin": None,
                "fund_house": None,
                "etf_name": entry["etf_name"],
                "theme": entry["theme"],
                "linked_sector": entry["linked_sector"],
                "linked_index": entry["linked_index"],
                "asset_class": meta.get("asset_class"),
                "inception_date": meta.get("inception_date"),
            }
        )

    if missing_ohlcv:
        log.warning(
            "curated_etfs_missing_ohlcv",
            count=len(missing_ohlcv),
            tickers=missing_ohlcv,
            action="run scripts/etf_sector_backfill.py to seed OHLCV",
        )

    # ── 3. Auto-detected supplementary ETFs ──────────────────────────────────
    with eng.connect() as conn:
        auto_raw = (
            conn.execute(
                text(_AUTO_DETECT_QUERY),
                {"exclude_tickers": curated_tickers},
            )
            .mappings()
            .all()
        )

    for r in auto_raw:
        theme, linked_sector = _classify_theme(r.get("etf_name"), r.get("category"))
        if theme == "Thematic":
            continue  # skip thematic in auto-detect supplement
        rows.append(
            {
                "ticker": r["ticker"],
                "isin": None,
                "fund_house": None,
                "etf_name": r["etf_name"],
                "theme": theme,
                "linked_sector": linked_sector,
                "linked_index": None,
                "asset_class": r.get("asset_class"),
                "inception_date": r.get("inception_date"),
            }
        )

    theme_counts: dict[str, int] = {}
    sector_set: set[str] = set()
    for row in rows:
        theme_counts[str(row["theme"])] = theme_counts.get(str(row["theme"]), 0) + 1
        if row["linked_sector"]:
            sector_set.add(str(row["linked_sector"]))

    missing_sectors = _CURATED_SECTORS - sector_set
    if missing_sectors:
        log.warning("etf_universe_sector_gaps", missing=sorted(missing_sectors))

    log.info(
        "etf_universe_built",
        total=len(rows),
        themes=theme_counts,
        sectors_covered=len(sector_set),
        sectors_missing=sorted(missing_sectors),
    )
    return rows


def populate_universe_etfs(engine: Engine | None = None) -> int:
    """Insert the domestic Indian ETF universe into ``atlas_universe_etfs``.

    Also soft-deletes any previously active rows for tickers no longer in the
    domestic universe.
    """
    eng = engine or get_engine()
    rows = build_etf_universe(eng)
    active_tickers = [r["ticker"] for r in rows]

    retire_sql = text("""
        UPDATE atlas.atlas_universe_etfs
        SET effective_to = CURRENT_DATE, updated_at = NOW()
        WHERE effective_to IS NULL
          AND ticker != ALL(:keep_tickers)
          AND ticker IN (SELECT ticker FROM public.de_etf_master)
    """)

    insert_sql = text("""
        INSERT INTO atlas.atlas_universe_etfs
            (ticker, isin, fund_house, etf_name, theme, linked_sector,
             linked_index, asset_class, inception_date,
             effective_from, effective_to)
        VALUES
            (:ticker, :isin, :fund_house, :etf_name, :theme, :linked_sector,
             :linked_index, :asset_class, :inception_date,
             :effective_from, NULL)
        ON CONFLICT (ticker, effective_from) DO UPDATE SET
            etf_name      = EXCLUDED.etf_name,
            theme         = EXCLUDED.theme,
            linked_sector = EXCLUDED.linked_sector,
            linked_index  = EXCLUDED.linked_index,
            asset_class   = EXCLUDED.asset_class,
            updated_at    = NOW()
    """)

    with eng.begin() as conn:
        retired = conn.execute(retire_sql, {"keep_tickers": active_tickers})
        log.info("universe_etfs_retired", count=retired.rowcount)
        for r in rows:
            conn.execute(insert_sql, {**r, "effective_from": Config.UNIVERSE_LOCK_DATE})

    log.info("universe_etfs_populated", count=len(rows), tickers=active_tickers)
    return len(rows)
