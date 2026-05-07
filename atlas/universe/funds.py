"""Atlas mutual fund universe builder.

Per methodology Section 3.1 + ``prds/00_INFRA_DECISIONS.md`` Section 4:
~450-500 equity, regular-plan, growth-option schemes across 8 SEBI categories.

Reality check (verified 2026-05-06 against Supabase JIP schema):
- ``de_mf_master`` columns: ``mstar_id``, ``fund_name`` (NOT scheme_name),
  ``amc_name`` (NOT amc), ``category_name``, ``broad_category``,
  ``is_index_fund`` (BOOL), ``is_etf`` (BOOL), ``is_active`` (BOOL),
  ``closure_date``, ``primary_benchmark``, ``inception_date``.
- Categories use a ``"India Fund <Name>"`` prefix — e.g.
  ``India Fund Large-Cap`` rather than ``Large Cap Fund``.
- Boolean flags (``is_index_fund``, ``is_etf``, ``is_active``) replace the
  earlier name-pattern hacks for filtering out index funds / ETFs.

Filter approach:
1. Boolean: ``is_active = TRUE AND is_index_fund = FALSE AND is_etf = FALSE``
2. Category: one of the 8 SEBI v0 categories (see ``_KEPT_CATEGORIES``)
3. Plan: ``fund_name NOT ILIKE '%direct%'`` (Regular plan only)
4. Option: ``fund_name NOT ILIKE '%idcw%'`` and similar (Growth option only)
5. Scope exclusions: international, solution-oriented, ESG out per v0 scope
6. NAV existence: must have at least one row in ``de_mf_nav_daily``
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.config import Config
from atlas.db import get_engine

log = structlog.get_logger()


# Eight SEBI equity categories — using JIP's "India Fund <Name>" prefix.
# Variants with and without the prefix are both accepted (some schemes lack it).
_KEPT_CATEGORIES = (
    # JIP-prefixed variants (the common case)
    "India Fund Large-Cap",
    "India Fund Mid-Cap",
    "India Fund Small-Cap",
    "India Fund Large & Mid-Cap",
    "India Fund Multi-Cap",
    "India Fund Flexi Cap",
    "India Fund ELSS (Tax Savings)",
    # Sectoral / Thematic equity flavours (per methodology 12.1)
    "India Fund Sector - Financial Services",
    "India Fund Sector - Healthcare",
    "India Fund Sector - Technology",
    "India Fund Sector - Energy",
    "India Fund Sector - FMCG",
    "India Fund Equity - Consumption",
    "India Fund Equity - Infrastructure",
    # Bare variants (some rows omit the prefix)
    "Flexi Cap",
    "ELSS (Tax Savings)",
)


_FUND_FILTER_QUERY = """
    SELECT
        m.mstar_id,
        m.fund_name,
        m.amc_name,
        COALESCE(m.broad_category, 'Equity')                AS broad_category,
        m.category_name,
        m.inception_date
    FROM public.de_mf_master m
    WHERE m.is_active = TRUE
      AND COALESCE(m.is_index_fund, FALSE) = FALSE
      AND COALESCE(m.is_etf, FALSE) = FALSE
      AND m.closure_date IS NULL
      AND m.category_name = ANY(:categories)
      -- Regular plan (not Direct)
      AND m.fund_name NOT ILIKE '%direct%'
      -- Growth option (not IDCW / Dividend payout / Income)
      AND m.fund_name NOT ILIKE '%idcw%'
      AND m.fund_name NOT ILIKE '%dividend%'
      AND m.fund_name NOT ILIKE '%income%'
      AND m.fund_name NOT ILIKE '%dpp%'
      -- International funds (out of v0 scope)
      AND m.fund_name NOT ILIKE '%global%'
      AND m.fund_name NOT ILIKE '%world%'
      AND m.fund_name NOT ILIKE '%international%'
      AND m.fund_name NOT ILIKE '%us equity%'
      AND m.fund_name NOT ILIKE '%asia%'
      AND m.fund_name NOT ILIKE '%emerging market%'
      -- Solution-oriented + ESG (out of v0 scope)
      AND m.fund_name NOT ILIKE '%retirement%'
      AND m.fund_name NOT ILIKE '%children%'
      AND m.fund_name NOT ILIKE '%solution%'
      AND m.fund_name NOT ILIKE '%esg%'
      -- Must have at least one NAV row
      AND EXISTS (
          SELECT 1 FROM public.de_mf_nav_daily n
          WHERE n.mstar_id = m.mstar_id
          LIMIT 1
      )
    ORDER BY m.amc_name, m.fund_name
"""


# Map JIP category_name → atlas benchmark_code (per methodology 12.1).
# Uses startswith / "in" checks because the JIP names have varied formatting.
def _category_to_benchmark_code(category_name: str) -> str:
    """Return benchmark_code for a fund category. Falls back to NIFTY 500."""
    cat = category_name.lower()

    if "large & mid" in cat:
        return "NIFTY200"
    if "large-cap" in cat or "large cap" in cat:
        return "NIFTY100"
    if "mid-cap" in cat or "mid cap" in cat:
        return "MIDCAP150"
    if "small-cap" in cat or "small cap" in cat:
        return "SMALLCAP250"
    if "multi-cap" in cat or "multi cap" in cat:
        return "NIFTY500"
    if "flexi" in cat:
        return "NIFTY500"
    if "elss" in cat:
        return "NIFTY500"
    if "sector" in cat or "equity -" in cat:
        return "NIFTY500"  # Per-fund refinement deferred to v1
    return "NIFTY500"


def build_fund_universe(engine: Engine | None = None) -> list[dict[str, object]]:
    """Return the filtered MF universe rows. Asserts count is in [350, 700]."""
    eng = engine or get_engine()
    with eng.connect() as conn:
        raw = (
            conn.execute(
                text(_FUND_FILTER_QUERY),
                {"categories": list(_KEPT_CATEGORIES)},
            )
            .mappings()
            .all()
        )

    rows: list[dict[str, object]] = []
    for r in raw:
        category = str(r["category_name"])
        rows.append(
            {
                "mstar_id": r["mstar_id"],
                "scheme_name": r["fund_name"],  # atlas schema uses scheme_name
                "amc": r["amc_name"],  # atlas schema uses amc
                "broad_category": r["broad_category"],
                "category_name": category,
                "plan_type": "Regular",
                "option_type": "Growth",
                "benchmark_code": _category_to_benchmark_code(category),
                "inception_date": r.get("inception_date"),
            }
        )

    n = len(rows)
    if not (350 <= n <= 700):
        raise AssertionError(
            f"Fund universe count {n} outside expected band [350, 700]. "
            "Inspect _FUND_FILTER_QUERY (likely too tight or too loose); "
            "tune via tests."
        )

    cat_counts: dict[str, int] = {}
    for r in rows:
        c = str(r["category_name"])
        cat_counts[c] = cat_counts.get(c, 0) + 1
    log.info("fund_universe_built", total=n, categories=cat_counts)
    return rows


def populate_universe_funds(engine: Engine | None = None) -> int:
    eng = engine or get_engine()
    rows = build_fund_universe(eng)

    insert_sql = text("""
        INSERT INTO atlas.atlas_universe_funds
            (mstar_id, scheme_name, amc, broad_category, category_name,
             plan_type, option_type, benchmark_code, inception_date,
             effective_from, effective_to)
        VALUES
            (:mstar_id, :scheme_name, :amc, :broad_category, :category_name,
             :plan_type, :option_type, :benchmark_code, :inception_date,
             :effective_from, NULL)
        ON CONFLICT (mstar_id, effective_from) DO UPDATE SET
            scheme_name = EXCLUDED.scheme_name,
            amc = EXCLUDED.amc,
            category_name = EXCLUDED.category_name,
            benchmark_code = EXCLUDED.benchmark_code,
            updated_at = NOW()
    """)

    with eng.begin() as conn:
        for r in rows:
            conn.execute(insert_sql, {**r, "effective_from": Config.UNIVERSE_LOCK_DATE})

    log.info("universe_funds_populated", count=len(rows))
    return len(rows)
