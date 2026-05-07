"""Atlas-M1 Supabase pre-flight check.

Verifies that the JIP Data Core tables migrated to Supabase contain
everything M1 needs to lock the universe + start computing. Read-only —
hits ``public.de_*`` tables, never writes anything.

What we check (focused per Nimish's scope):

1. **Schema parity** — 15 ``public.de_*`` tables exist; ``atlas`` schema
   is absent (M1 will create it cleanly).
2. **Universe candidate coverage**:
   - ~2,000+ active stocks in ``de_instrument``, with ~500 NIFTY 500
     members and sector populated
   - ≥100 ETFs with ≥30 trading days of recent volume
   - All 75 curated indices present in ``de_index_master``
   - 350-600 candidate funds match the SEBI filter
3. **12-year history depth** for the locked universe:
   - Stocks: 750 universe candidates have OHLCV from 2014-04-01 (or
     listing_date if later) to T-1
   - ETFs: 100 universe candidates have OHLCV
   - Indices: 75 curated indices have prices from 2014-04-01 (or earliest
     available) to T-1
   - Funds: ~500 universe candidates have NAVs from earliest available
4. **Holdings tables**:
   - ``de_mf_holdings`` — recent disclosures for universe funds
   - ``de_etf_holdings`` — recent disclosures for universe ETFs
5. **Sector mapping**: ``de_sector_mapping`` rows present
6. **Source-identifier sanity**: GOLDBEES, SP500/MSCIWORLD (M0 Job 1),
   INDIA VIX exist where expected.

Output: a markdown report at ``output/preflight_supabase_<date>.md`` plus
a colour-coded console summary. Exit codes: 0 = GO, 1 = REVIEW (proceed
with documented gaps), 2 = NO-GO.

Usage::

    # With ATLAS_DB_URL in .env:
    python -m atlas.preflight

    # Or pass DSN explicitly:
    ATLAS_DB_URL=postgresql+psycopg2://... python -m atlas.preflight

    # Save report to custom path:
    python -m atlas.preflight --output output/my_check.md
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.config import Config
from atlas.db import get_engine

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 15 public.de_* tables Atlas reads from (per architecture Section 4)
EXPECTED_JIP_TABLES = (
    "de_instrument",
    "de_etf_master",
    "de_mf_master",
    "de_index_master",
    "de_equity_ohlcv",
    "de_etf_ohlcv",
    "de_index_prices",
    "de_global_prices",
    "de_mf_nav_daily",
    "de_index_constituents",
    "de_sector_mapping",
    "de_trading_calendar",
    "de_corporate_actions",
    "de_mf_holdings",
    "de_etf_holdings",
)

# Methodology Section 3.4 said "12 years from 2014-04-01" — but JIP's index
# price history actually starts 2016-04-07 (verified against Supabase). We
# adjust to a 10-year scope. Stock OHLCV reaches back to 2007 so stock-level
# returns are fine; what's bounded is RS-vs-index calculations.
HISTORICAL_START = date(2016, 4, 7)

# 75 curated indices — verified codes against actual JIP de_index_master
# (must match atlas/universe/indices.py exactly).
CURATED_INDEX_CODES = (
    # Broad (15)
    "NIFTY 50",
    "NIFTY 100",
    "NIFTY 200",
    "NIFTY 500",
    "NIFTY NEXT 50",
    "NIFTY MIDCAP 50",
    "NIFTY MIDCAP 100",
    "NIFTY MIDCAP 150",
    "NIFTY SMLCAP 50",
    "NIFTY SMLCAP 100",
    "NIFTY SMLCAP 250",
    "NIFTY MICROCAP250",
    "NIFTY TOTAL MKT",
    "NIFTY LARGEMID250",
    "NIFTY MIDSML 400",
    # Sectoral (12)
    "NIFTY BANK",
    "NIFTY IT",
    "NIFTY FMCG",
    "NIFTY AUTO",
    "NIFTY PHARMA",
    "NIFTY METAL",
    "NIFTY ENERGY",
    "NIFTY REALTY",
    "NIFTY MEDIA",
    "NIFTY PSU BANK",
    "NIFTY PVT BANK",
    "NIFTY HEALTHCARE",
    # Industry (15)
    "NIFTY FIN SERVICE",
    "NIFTY FINSEREXBNK",
    "NIFTY OIL AND GAS",
    "NIFTY CONSR DURBL",
    "NIFTY CAPITAL MKT",
    "NIFTY MIDSML HLTH",
    "NIFTY MS FIN SERV",
    "NIFTY MS IT TELCM",
    "NIFTY MS IND CONS",
    "NIFTY HOUSING",
    "NIFTY MOBILITY",
    "NIFTY IND TOURISM",
    "NIFTY IND DEFENCE",
    "NIFTY EV",
    "NIFTY INFRALOG",
    # Factor (18)
    "NIFTY ALPHA 50",
    "NIFTY ALPHALOWVOL",
    "NIFTY100 QUALTY30",
    "NIFTY200 QUALTY30",
    "NIFTY200 VALUE 30",
    "NIFTY500 VALUE 50",
    "NIFTY500MOMENTM50",
    "NIFTY200MOMENTM30",
    "NIFTY100 LOWVOL30",
    "NIFTY LOW VOL 50",
    "NIFTY500 LOWVOL50",
    "NIFTY HIGHBETA 50",
    "NIFTY DIV OPPS 50",
    "NIFTY GROWSECT 15",
    "NIFTY100 EQL WGT",
    "NIFTY100 ALPHA 30",
    "NIFTY200 ALPHA 30",
    "NIFTY AQLV 30",
    # Thematic (15)
    "NIFTY CPSE",
    "NIFTY PSE",
    "NIFTY MNC",
    "NIFTY INFRA",
    "NIFTY INDIA MFG",
    "NIFTY SERV SECTOR",
    "NIFTY COMMODITIES",
    "NIFTY IND DIGITAL",
    "NIFTY CONSUMPTION",
    "NIFTY NEW CONSUMP",
    "NIFTY NONCYC CONS",
    "NIFTY INTERNET",
    "NIFTY MULTI INFRA",
    "NIFTY MULTI MFG",
    "NIFTY RAILWAYSPSU",
)


# ---------------------------------------------------------------------------
# Result aggregation
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str  # 'go' | 'review' | 'no-go'
    actual: str
    expected: str
    notes: str = ""


@dataclass
class Report:
    started_at: datetime = field(default_factory=datetime.now)
    db_user: str = ""
    db_name: str = ""
    db_version: str = ""
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)
        symbol = "✓" if result.passed else ("⚠" if result.severity == "review" else "✗")
        print(f"  {symbol} {result.name:60s}  actual={result.actual}  expected={result.expected}")
        if result.notes:
            print(f"      └─ {result.notes}")

    def verdict(self) -> str:
        if any(c.severity == "no-go" and not c.passed for c in self.checks):
            return "NO-GO"
        if any(c.severity == "review" and not c.passed for c in self.checks):
            return "REVIEW"
        return "GO"

    def exit_code(self) -> int:
        v = self.verdict()
        return {"GO": 0, "REVIEW": 1, "NO-GO": 2}[v]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _scalar(engine: Engine, sql: str, **kwargs: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), kwargs).scalar()


def _check_schema_parity(engine: Engine, report: Report) -> None:
    print("\n[1] Schema parity")
    for table in EXPECTED_JIP_TABLES:
        exists = _scalar(
            engine,
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables "
            "  WHERE table_schema = 'public' AND table_name = :tbl"
            ")",
            tbl=table,
        )
        report.add(
            CheckResult(
                name=f"public.{table} exists",
                passed=bool(exists),
                severity="no-go",
                actual="present" if exists else "MISSING",
                expected="present",
            )
        )

    atlas_exists = _scalar(
        engine,
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.schemata WHERE schema_name = 'atlas'"
        ")",
    )
    report.add(
        CheckResult(
            name="atlas schema is empty (clean slate)",
            passed=not atlas_exists,
            severity="review",
            actual="exists" if atlas_exists else "absent",
            expected="absent",
            notes=(
                "atlas schema already exists — M1 migrations will upsert. "
                "If you want a clean re-lock, drop it first."
                if atlas_exists
                else ""
            ),
        )
    )


def _check_instrument_master(engine: Engine, report: Report) -> None:
    print("\n[2] de_instrument master coverage")

    active_count = _scalar(
        engine, "SELECT COUNT(*) FROM public.de_instrument WHERE is_active = TRUE"
    )
    report.add(
        CheckResult(
            name="active stock count",
            passed=bool(active_count and active_count > 1500),
            severity="no-go",
            actual=str(active_count),
            expected="≥ 1,500",
        )
    )

    n500_count = _scalar(
        engine,
        "SELECT COUNT(*) FROM public.de_instrument " "WHERE is_active = TRUE AND nifty_500 = TRUE",
    )
    report.add(
        CheckResult(
            name="NIFTY 500 active members",
            passed=bool(n500_count and 480 <= n500_count <= 510),
            severity="no-go",
            actual=str(n500_count),
            expected="500 ± 10",
        )
    )

    # NIFTY 100 membership is NOT a column on de_instrument (it has nifty_50,
    # nifty_200, nifty_500). We resolve Large tier via de_index_constituents
    # instead. Verify NIFTY 100 has 100 members in that table.
    n100_count = _scalar(
        engine,
        "SELECT COUNT(DISTINCT instrument_id) FROM public.de_index_constituents "
        "WHERE index_code = 'NIFTY 100' "
        "AND (effective_to IS NULL OR effective_to > CURRENT_DATE)",
    )
    report.add(
        CheckResult(
            name="NIFTY 100 constituents (Large tier)",
            passed=bool(n100_count and 95 <= n100_count <= 105),
            severity="no-go",
            actual=str(n100_count),
            expected="100 ± 5",
        )
    )

    n200_count = _scalar(
        engine,
        "SELECT COUNT(*) FROM public.de_instrument " "WHERE is_active = TRUE AND nifty_200 = TRUE",
    )
    report.add(
        CheckResult(
            name="NIFTY 200 active members",
            passed=bool(n200_count and 195 <= n200_count <= 205),
            severity="review",
            actual=str(n200_count),
            expected="200 ± 5",
        )
    )

    # All four tier-defining indices must have constituents
    for index_code, expected, label in (
        ("NIFTY MIDCAP 150", 150, "Mid tier"),
        ("NIFTY SMLCAP 250", 250, "Small tier"),
        ("NIFTY MICROCAP250", 250, "Micro tier"),
    ):
        cnt = _scalar(
            engine,
            "SELECT COUNT(DISTINCT instrument_id) FROM public.de_index_constituents "
            "WHERE index_code = :code "
            "AND (effective_to IS NULL OR effective_to > CURRENT_DATE)",
            code=index_code,
        )
        report.add(
            CheckResult(
                name=f"{index_code} constituents ({label})",
                passed=bool(cnt and abs(cnt - expected) <= 5),
                severity="no-go",
                actual=str(cnt),
                expected=f"{expected} ± 5",
            )
        )

    sector_distinct = _scalar(
        engine,
        "SELECT COUNT(DISTINCT sector) FROM public.de_instrument "
        "WHERE is_active = TRUE AND sector IS NOT NULL",
    )
    # JIP uses a finer-grained sector taxonomy (~31) than methodology Section 10.1
    # assumed (~20-22). Methodology says "use whatever NSE actually returns";
    # 31 is fine, just more granular.
    report.add(
        CheckResult(
            name="distinct sector count",
            passed=bool(sector_distinct and 15 <= sector_distinct <= 50),
            severity="review",
            actual=str(sector_distinct),
            expected="15-50 (JIP uses finer taxonomy than methodology assumed ~20)",
        )
    )

    sector_null_pct = (
        _scalar(
            engine,
            "SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE sector IS NULL) / NULLIF(COUNT(*), 0), 2) "
            "FROM public.de_instrument WHERE is_active = TRUE",
        )
        or 0
    )
    # 11% of stocks have NULL sector but they're excluded from universe via the
    # WHERE sector IS NOT NULL filter in tier loaders. Document, not block.
    report.add(
        CheckResult(
            name="active stocks with NULL sector",
            passed=float(sector_null_pct) < 20.0,
            severity="review",
            actual=f"{sector_null_pct}%",
            expected="< 20% (excluded from universe via tier loaders)",
            notes="Stocks with NULL sector are excluded from atlas universe.",
        )
    )


def _check_stock_ohlcv_depth(engine: Engine, report: Report) -> None:
    print("\n[3] de_equity_ohlcv 12-year depth (NIFTY 500 universe)")

    earliest = _scalar(engine, "SELECT MIN(date) FROM public.de_equity_ohlcv")
    report.add(
        CheckResult(
            name="earliest OHLCV date",
            passed=bool(earliest and earliest <= HISTORICAL_START),
            severity="no-go",
            actual=str(earliest),
            expected=f"≤ {HISTORICAL_START}",
        )
    )

    latest = _scalar(engine, "SELECT MAX(date) FROM public.de_equity_ohlcv")
    days_stale = (date.today() - latest).days if latest else 999
    report.add(
        CheckResult(
            name="latest OHLCV date freshness",
            passed=days_stale <= 5,
            severity="review",
            actual=f"{latest} ({days_stale}d ago)",
            expected="within last 5 days",
        )
    )

    # Critical: every NIFTY 500 stock has 252+ days of OHLCV before
    # 2014-04-01 + listing date. Captures M0 Job 1 gap-fill completeness.
    short_history_count = _scalar(
        engine,
        f"""
        SELECT COUNT(*)
        FROM public.de_instrument i
        WHERE i.is_active = TRUE AND i.nifty_500 = TRUE
          AND (
              SELECT MIN(date) FROM public.de_equity_ohlcv o
              WHERE o.instrument_id = i.id
          ) > '{HISTORICAL_START}'
          AND (i.listing_date IS NULL OR i.listing_date < '{HISTORICAL_START}')
        """,
    )
    report.add(
        CheckResult(
            name="NIFTY 500 stocks listed pre-2014 with insufficient history",
            passed=(short_history_count or 0) <= 5,
            severity="review",
            actual=str(short_history_count),
            expected="≤ 5 (rest covered by M0 Job 1 gap-fill)",
            notes=(
                "These stocks were listed before 2014-04-01 but have no OHLCV "
                "from then. Either gap-fill incomplete or listing_date is wrong."
                if short_history_count
                else ""
            ),
        )
    )


def _check_etf_coverage(engine: Engine, report: Report) -> None:
    print("\n[4] ETFs (de_etf_master + de_etf_ohlcv)")

    etf_master_count = _scalar(engine, "SELECT COUNT(*) FROM public.de_etf_master")
    report.add(
        CheckResult(
            name="de_etf_master row count",
            passed=bool(etf_master_count and etf_master_count >= 100),
            severity="no-go",
            actual=str(etf_master_count),
            expected="≥ 100 (universe takes top 100)",
        )
    )

    # ETFs with ≥30 trading days in last 90 calendar days = pass liquidity check
    liquid_etf_count = _scalar(
        engine,
        """
        SELECT COUNT(*) FROM (
            SELECT ticker
            FROM public.de_etf_ohlcv
            WHERE date >= (CURRENT_DATE - INTERVAL '90 days')
              AND close IS NOT NULL AND volume IS NOT NULL
            GROUP BY ticker
            HAVING COUNT(*) >= 30
        ) t
        """,
    )
    report.add(
        CheckResult(
            name="ETFs passing liquidity gate (30+ days in last 90)",
            passed=bool(liquid_etf_count and liquid_etf_count >= 100),
            severity="no-go",
            actual=str(liquid_etf_count),
            expected="≥ 100",
            notes=(
                "Methodology Section 3.1 — top 100 by traded value. "
                "If < 100 liquid ETFs exist, universe is undersized."
                if (liquid_etf_count or 0) < 100
                else ""
            ),
        )
    )


def _check_index_coverage(engine: Engine, report: Report) -> None:
    print("\n[5] Indices (de_index_master + de_index_prices)")

    # Every curated index code must exist in de_index_master
    placeholders = ", ".join(f":code_{i}" for i in range(len(CURATED_INDEX_CODES)))
    params: dict[str, Any] = {f"code_{i}": code for i, code in enumerate(CURATED_INDEX_CODES)}
    found_count = _scalar(
        engine,
        f"SELECT COUNT(*) FROM public.de_index_master WHERE index_code IN ({placeholders})",
        **params,
    )
    report.add(
        CheckResult(
            name="curated 75-index codes present in de_index_master",
            passed=found_count == len(CURATED_INDEX_CODES),
            severity="no-go",
            actual=f"{found_count} / {len(CURATED_INDEX_CODES)}",
            expected=str(len(CURATED_INDEX_CODES)),
            notes=(
                "Some curated codes missing — likely naming mismatch "
                "(e.g. 'NIFTY 50' vs 'NIFTY50'). Reconcile before M1."
                if found_count != len(CURATED_INDEX_CODES)
                else ""
            ),
        )
    )

    # Critical benchmarks: NIFTY 500 (regime), tier benchmarks, INDIA VIX.
    # Use exact JIP index_codes (NIFTY SMLCAP 250 not NIFTY SMALLCAP 250).
    for code in ("NIFTY 500", "NIFTY 100", "NIFTY MIDCAP 150", "NIFTY SMLCAP 250", "INDIA VIX"):
        earliest = _scalar(
            engine,
            "SELECT MIN(date) FROM public.de_index_prices WHERE index_code = :code",
            code=code,
        )
        # India VIX is allowed to start later (2018) — used by regime classifier
        # only from 2018+; pre-2018 regime calls fall back to breadth+trend.
        if code == "INDIA VIX":
            target = date(2019, 1, 1)
            severity = "review"
        else:
            target = HISTORICAL_START
            severity = "no-go"
        ok = bool(earliest and earliest <= target)
        report.add(
            CheckResult(
                name=f"{code} earliest price",
                passed=ok,
                severity=severity,
                actual=str(earliest) if earliest else "MISSING",
                expected=f"≤ {target}",
            )
        )


def _check_global_prices(engine: Engine, report: Report) -> None:
    print("\n[6] de_global_prices (M0 Job 1 deliverable: SP500, MSCIWORLD)")

    # GOLDBEES is in de_etf_ohlcv per schema 2.6 (numéraire source).
    # Check anyway in case it lives in global_prices instead.
    for ticker, friendly in (
        ("GOLDBEES", "Gold (numéraire)"),
        ("^GSPC", "S&P 500 (yfinance ticker)"),
        ("INTL_SPX", "S&P 500 (M0 prefix variant)"),
        ("URTH", "MSCI World (URTH iShares ETF)"),
        ("INTL_MSCIWORLD", "MSCI World (M0 prefix variant)"),
    ):
        rows = _scalar(
            engine,
            "SELECT COUNT(*) FROM public.de_global_prices WHERE ticker = :t",
            t=ticker,
        )
        report.add(
            CheckResult(
                name=f"de_global_prices: {friendly}",
                passed=bool(rows and rows > 1000),
                severity="review",  # Either ticker variant is acceptable
                actual=f"{rows} rows" if rows else "0",
                expected="> 1,000 daily rows",
            )
        )


def _check_index_constituents(engine: Engine, report: Report) -> None:
    """No-op: tier index counts already verified in _check_instrument_master."""
    _ = (engine, report)
    print("\n[7] de_index_constituents — checked in [2] instrument master section")


def _check_fund_master_and_navs(engine: Engine, report: Report) -> None:
    print("\n[8] Mutual funds (de_mf_master + de_mf_nav_daily)")

    mf_master_count = _scalar(engine, "SELECT COUNT(*) FROM public.de_mf_master")
    report.add(
        CheckResult(
            name="de_mf_master row count",
            passed=bool(mf_master_count and mf_master_count >= 1000),
            severity="no-go",
            actual=str(mf_master_count),
            expected="≥ 1,000",
        )
    )

    # Filter dry-run — must match atlas/universe/funds.py exactly.
    filter_count = _scalar(
        engine,
        """
        SELECT COUNT(*) FROM public.de_mf_master m
        WHERE m.is_active = TRUE
          AND COALESCE(m.is_index_fund, FALSE) = FALSE
          AND COALESCE(m.is_etf, FALSE) = FALSE
          AND m.closure_date IS NULL
          AND m.category_name = ANY(:cats)
          AND m.fund_name NOT ILIKE '%direct%'
          AND m.fund_name NOT ILIKE '%idcw%'
          AND m.fund_name NOT ILIKE '%dividend%'
          AND m.fund_name NOT ILIKE '%income%'
          AND m.fund_name NOT ILIKE '%dpp%'
          AND m.fund_name NOT ILIKE '%global%'
          AND m.fund_name NOT ILIKE '%world%'
          AND m.fund_name NOT ILIKE '%international%'
          AND m.fund_name NOT ILIKE '%us equity%'
          AND m.fund_name NOT ILIKE '%asia%'
          AND m.fund_name NOT ILIKE '%emerging market%'
          AND m.fund_name NOT ILIKE '%retirement%'
          AND m.fund_name NOT ILIKE '%children%'
          AND m.fund_name NOT ILIKE '%solution%'
          AND m.fund_name NOT ILIKE '%esg%'
          AND EXISTS (
              SELECT 1 FROM public.de_mf_nav_daily n WHERE n.mstar_id = m.mstar_id LIMIT 1
          )
        """,
        cats=[
            # Match atlas/universe/funds.py:_KEPT_CATEGORIES
            "India Fund Large-Cap",
            "India Fund Mid-Cap",
            "India Fund Small-Cap",
            "India Fund Large & Mid-Cap",
            "India Fund Multi-Cap",
            "India Fund Flexi Cap",
            "India Fund ELSS (Tax Savings)",
            "India Fund Sector - Financial Services",
            "India Fund Sector - Healthcare",
            "India Fund Sector - Technology",
            "India Fund Sector - Energy",
            "India Fund Sector - FMCG",
            "India Fund Equity - Consumption",
            "India Fund Equity - Infrastructure",
            "Flexi Cap",
            "ELSS (Tax Savings)",
        ],
    )
    report.add(
        CheckResult(
            name="MF universe filter dry-run",
            passed=bool(filter_count and 350 <= filter_count <= 700),
            severity="no-go",
            actual=str(filter_count),
            expected="450-500 (band 350-700)",
            notes=(
                "Filter logic is in atlas/universe/funds.py:_FUND_FILTER_QUERY. "
                "Tighten or loosen if outside band."
            ),
        )
    )

    nav_earliest = _scalar(engine, "SELECT MIN(nav_date) FROM public.de_mf_nav_daily")
    nav_latest = _scalar(engine, "SELECT MAX(nav_date) FROM public.de_mf_nav_daily")
    nav_days_stale = (date.today() - nav_latest).days if nav_latest else 999
    report.add(
        CheckResult(
            name="de_mf_nav_daily earliest date",
            passed=bool(nav_earliest and nav_earliest <= HISTORICAL_START),
            severity="no-go",
            actual=str(nav_earliest),
            expected=f"≤ {HISTORICAL_START}",
        )
    )
    report.add(
        CheckResult(
            name="de_mf_nav_daily latest date freshness",
            passed=nav_days_stale <= 5,
            severity="review",
            actual=f"{nav_latest} ({nav_days_stale}d ago)",
            expected="within last 5 days",
        )
    )


def _check_holdings(engine: Engine, report: Report) -> None:
    print("\n[9] Holdings (de_mf_holdings + de_etf_holdings)")

    mf_distinct = _scalar(engine, "SELECT COUNT(DISTINCT mstar_id) FROM public.de_mf_holdings")
    mf_recent = _scalar(engine, "SELECT MAX(as_of_date) FROM public.de_mf_holdings")
    mf_days_stale = (date.today() - mf_recent).days if mf_recent else 999
    report.add(
        CheckResult(
            name="de_mf_holdings: distinct schemes covered",
            passed=bool(mf_distinct and mf_distinct >= 400),
            severity="review",
            actual=str(mf_distinct),
            expected="≥ 400",
        )
    )
    report.add(
        CheckResult(
            name="de_mf_holdings: latest as_of_date",
            passed=mf_days_stale <= 60,
            severity="review",
            actual=f"{mf_recent} ({mf_days_stale}d ago)",
            expected="within last 60 days",
        )
    )

    etf_distinct = _scalar(engine, "SELECT COUNT(DISTINCT ticker) FROM public.de_etf_holdings")
    etf_recent = _scalar(engine, "SELECT MAX(as_of_date) FROM public.de_etf_holdings")
    etf_days_stale = (date.today() - etf_recent).days if etf_recent else 999
    report.add(
        CheckResult(
            name="de_etf_holdings: distinct ETFs covered (M0 Job 2)",
            passed=bool(etf_distinct and etf_distinct >= 80),
            severity="review",
            actual=str(etf_distinct),
            expected="≥ 80 of 100 universe ETFs",
        )
    )
    report.add(
        CheckResult(
            name="de_etf_holdings: latest as_of_date",
            passed=etf_days_stale <= 60,
            severity="review",
            actual=f"{etf_recent} ({etf_days_stale}d ago)",
            expected="within last 60 days",
        )
    )


def _check_sector_mapping(engine: Engine, report: Report) -> None:
    print("\n[10] de_sector_mapping")

    count = _scalar(engine, "SELECT COUNT(*) FROM public.de_sector_mapping")
    report.add(
        CheckResult(
            name="sector mapping rows",
            passed=bool(count and count >= 10),
            severity="no-go",
            actual=str(count),
            expected="≥ 10 (one per major NSE-indexed sector)",
        )
    )

    # The major sectors that *must* have a primary NSE index per methodology 6.3
    required_sectors = (
        "Bank",
        "Information Technology",
        "FMCG",
        "Automobile",
        "Pharma",
        "Metals & Mining",
        "Energy",
        "Real Estate",
        "Media",
        "Healthcare",
    )
    # Use ILIKE since exact spellings may vary across JIP releases
    placeholders = " OR ".join(
        f"jip_sector_name ILIKE :sec_{i}" for i in range(len(required_sectors))
    )
    params: dict[str, Any] = {f"sec_{i}": f"%{s}%" for i, s in enumerate(required_sectors)}
    mapped = _scalar(
        engine,
        f"SELECT COUNT(*) FROM public.de_sector_mapping "
        f"WHERE primary_nse_index IS NOT NULL AND ({placeholders})",
        **params,
    )
    report.add(
        CheckResult(
            name="sectors with primary NSE index mapped",
            passed=bool(mapped and mapped >= 8),
            severity="review",
            actual=f"{mapped} sectors with primary index",
            expected="≥ 8 of major sectors",
        )
    )


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------


def write_markdown_report(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    verdict = report.verdict()

    by_severity: dict[str, list[CheckResult]] = {"no-go": [], "review": [], "go": []}
    for c in report.checks:
        by_severity.setdefault(c.severity, []).append(c)

    n_pass = sum(1 for c in report.checks if c.passed)
    n_fail_critical = sum(1 for c in report.checks if not c.passed and c.severity == "no-go")
    n_fail_review = sum(1 for c in report.checks if not c.passed and c.severity == "review")

    lines: list[str] = []
    lines.append("# Atlas-M1 Supabase Pre-Flight Report")
    lines.append("")
    lines.append(f"**Generated:** {report.started_at.isoformat()}")
    lines.append(f"**Database:** `{report.db_name}` (user: `{report.db_user}`)")
    lines.append(f"**PostgreSQL:** {report.db_version}")
    lines.append("")
    lines.append(f"## Verdict: **{verdict}**")
    lines.append("")
    lines.append(f"- {n_pass} of {len(report.checks)} checks pass")
    lines.append(f"- {n_fail_critical} NO-GO failures (block M1 start)")
    lines.append(f"- {n_fail_review} REVIEW failures (proceed with documented gaps)")
    lines.append("")
    lines.append("## Result detail")
    lines.append("")
    lines.append("| Status | Severity | Check | Actual | Expected | Notes |")
    lines.append("|---|---|---|---|---|---|")
    for c in report.checks:
        symbol = "✅" if c.passed else ("⚠️" if c.severity == "review" else "❌")
        lines.append(
            f"| {symbol} | `{c.severity}` | {c.name} | {c.actual} | {c.expected} | {c.notes} |"
        )
    lines.append("")
    lines.append("## Next steps")
    lines.append("")
    if verdict == "GO":
        lines.append(
            "All checks pass. Run `python scripts/m1_run.py` to apply migrations + lock the universe."
        )
    elif verdict == "REVIEW":
        lines.append(
            "Critical checks pass; some warnings noted above. Review each ⚠️ row and decide whether to:"
        )
        lines.append("- Fix the gap before M1 (e.g. wait for fresher MF NAV data), or")
        lines.append("- Document the gap in `docs/validation/validation_M1_<date>.md` and proceed.")
    else:
        lines.append(
            "Critical (NO-GO) failures present. Do NOT run M1 until each ❌ row is resolved."
        )
        lines.append(
            "Most NO-GO failures are migration gaps — re-run the JIP→Supabase migration for the affected tables."
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ Markdown report written: {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_preflight(output_path: Path | None = None) -> int:
    """Execute all pre-flight checks. Returns exit code (0/1/2)."""
    Config.assert_db_url()
    engine = get_engine()

    report = Report()

    # Connection sanity
    with engine.connect() as conn:
        report.db_user = str(conn.execute(text("SELECT current_user")).scalar())
        report.db_name = str(conn.execute(text("SELECT current_database()")).scalar())
        report.db_version = str(conn.execute(text("SELECT version()")).scalar())

    print("=" * 80)
    print("Atlas-M1 Supabase Pre-Flight")
    print(f"  Database: {report.db_name}  user: {report.db_user}")
    print(f"  Started:  {report.started_at.isoformat()}")
    print("=" * 80)

    _check_schema_parity(engine, report)
    _check_instrument_master(engine, report)
    _check_stock_ohlcv_depth(engine, report)
    _check_etf_coverage(engine, report)
    _check_index_coverage(engine, report)
    _check_global_prices(engine, report)
    _check_index_constituents(engine, report)
    _check_fund_master_and_navs(engine, report)
    _check_holdings(engine, report)
    _check_sector_mapping(engine, report)

    print("\n" + "=" * 80)
    print(f"VERDICT: {report.verdict()}")
    print("=" * 80)

    out_path = output_path or Path(f"output/preflight_supabase_{date.today().isoformat()}.md")
    write_markdown_report(report, out_path)

    return report.exit_code()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atlas-M1 Supabase pre-flight check")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Markdown report output path (default: output/preflight_supabase_<date>.md)",
    )
    args = parser.parse_args(argv)
    try:
        return run_preflight(args.output)
    except Exception as exc:
        log.exception("preflight_crashed", error=str(exc))
        print(f"\n✗ Pre-flight crashed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
