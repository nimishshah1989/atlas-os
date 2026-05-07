"""Atlas ETF universe builder.

Per methodology Section 3.1: top 100 ETFs by 60-day median traded value
(close × volume) on NSE. Theme classification per methodology 8.2:

- **Broad** — tracks Nifty 50/100/500/Next 50 / Sensex
- **Sectoral** — tracks a single NSE sector (Bank, IT, Pharma, etc.)
- **Thematic** — everything else (factor, smart-beta, gold, international)

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


_TOP_100_BY_TRADED_VALUE_QUERY = """
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
    ORDER BY rv.median_traded_value_60d DESC
    LIMIT 100
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
    "SENSEX",
    "BSE 100",
    "BSE100",
    "TOTAL MARKET",
    "TOTAL MKT",
)

# Substring → atlas_sector_master.sector_name. Sector names verified against
# actual JIP de_sector_mapping (loaded into atlas_sector_master) — e.g.
# JIP uses "Banking" not "Bank", "Automobile" not "Auto". Order matters:
# longer/more specific tokens first.
_SECTORAL_KEYWORDS: tuple[tuple[str, str], ...] = (
    # PSU/Private Bank ETFs map to the parent "Banking" sector since JIP
    # doesn't sub-classify (no PSU Bank or Private Bank rows in master).
    ("PSU BANK", "Banking"),
    ("PRIVATE BANK", "Banking"),
    ("PVT BANK", "Banking"),
    ("BANK", "Banking"),
    ("HEALTHCARE", "Healthcare"),
    ("PHARMA", "Pharma"),
    ("FMCG", "FMCG"),
    ("AUTO", "Automobile"),
    ("METAL", "Metal"),
    ("ENERGY", "Energy"),
    ("REALTY", "Realty"),
    ("MEDIA", "Media"),
    ("CONSUMER DURABLES", "Consumer Durables"),
    ("CONSR DURBL", "Consumer Durables"),
    ("OIL & GAS", "Oil & Gas"),
    ("OIL AND GAS", "Oil & Gas"),
    ("IT", "IT"),  # last because IT is short / can collide
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
            # Word-boundary check for IT to avoid matching "INFRASTRUCTURE", "ITC", etc.
            tokens = haystack.replace("/", " ").replace("-", " ").split()
            if "IT" in tokens:
                return ("Sectoral", sector_name)
            continue
        if kw in haystack:
            return ("Sectoral", sector_name)

    return ("Thematic", None)


def build_etf_universe(engine: Engine | None = None) -> list[dict[str, object]]:
    """Return top-100 ETF universe rows. Asserts count == 100."""
    eng = engine or get_engine()
    with eng.connect() as conn:
        raw = conn.execute(text(_TOP_100_BY_TRADED_VALUE_QUERY)).mappings().all()

    rows: list[dict[str, object]] = []
    for r in raw:
        theme, linked_sector = _classify_theme(r.get("etf_name"), r.get("category"))
        rows.append(
            {
                "ticker": r["ticker"],
                "isin": None,  # JIP de_etf_master has no isin column
                "fund_house": None,  # JIP de_etf_master has no fund_house column
                "etf_name": r["etf_name"],
                "theme": theme,
                "linked_sector": linked_sector,
                "linked_index": None,
                "asset_class": r.get("asset_class"),
                "inception_date": r.get("inception_date"),
            }
        )

    if len(rows) != 100:
        raise AssertionError(
            f"Expected 100 ETFs, got {len(rows)}. "
            "Check de_etf_ohlcv volume coverage and de_etf_master row count."
        )

    theme_counts: dict[str, int] = {}
    for r in rows:
        theme = str(r["theme"])
        theme_counts[theme] = theme_counts.get(theme, 0) + 1
    log.info("etf_universe_built", total=len(rows), themes=theme_counts)
    return rows


def populate_universe_etfs(engine: Engine | None = None) -> int:
    """Insert the 100-ETF universe into ``atlas_universe_etfs``."""
    eng = engine or get_engine()
    rows = build_etf_universe(eng)

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
            etf_name = EXCLUDED.etf_name,
            theme = EXCLUDED.theme,
            linked_sector = EXCLUDED.linked_sector,
            asset_class = EXCLUDED.asset_class,
            updated_at = NOW()
    """)

    with eng.begin() as conn:
        for r in rows:
            conn.execute(insert_sql, {**r, "effective_from": Config.UNIVERSE_LOCK_DATE})

    log.info("universe_etfs_populated", count=len(rows))
    return len(rows)
