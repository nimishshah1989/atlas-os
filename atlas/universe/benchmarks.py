"""Atlas benchmark master + fund-category benchmark map seeders.

Seeds the two reference tables that drive RS classification:

- ``atlas_benchmark_master`` (9 rows: 5 user benchmarks + 4 tier benchmarks)
- ``atlas_fund_category_benchmark_map`` (8 rows mapping category → benchmark)

Per ``docs/02_DATABASE_SCHEMA.md`` Sections 2.6 + 2.7 and methodology 12.1.

v0 note on MICROCAP_CUSTOM: methodology §6.2 specifies an Atlas-constructed
equal-weighted index of the 250 micro names. For v0 we point at JIP's
``NIFTY MICROCAP250`` directly — close enough as a tier benchmark for
within-tier RS ranking, and it sidesteps the chicken-and-egg of computing
the custom EW index inside M2 itself. v1 swap-in is tracked in
``prds/00_INFRA_DECISIONS.md``.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()


# 9 benchmarks per schema 2.6
_BENCHMARKS: tuple[dict[str, str], ...] = (
    # User benchmarks (selectable in UI)
    {
        "benchmark_code": "NIFTY50",
        "benchmark_name": "Nifty 50",
        "benchmark_type": "user",
        "source_table": "de_index_prices",
        "source_identifier": "NIFTY 50",
        "description": "Nifty 50 — large-cap NSE benchmark",
    },
    {
        "benchmark_code": "NIFTY500",
        "benchmark_name": "Nifty 500",
        "benchmark_type": "user",
        "source_table": "de_index_prices",
        "source_identifier": "NIFTY 500",
        "description": "Nifty 500 — broad-market reference and methodology default",
    },
    {
        "benchmark_code": "MSCIWORLD",
        "benchmark_name": "MSCI World",
        "benchmark_type": "user",
        "source_table": "de_global_prices",
        "source_identifier": "URTH",
        "description": "MSCI World (URTH iShares ETF proxy)",
    },
    {
        "benchmark_code": "SP500",
        "benchmark_name": "S&P 500",
        "benchmark_type": "user",
        "source_table": "de_global_prices",
        "source_identifier": "^GSPC",
        "description": "S&P 500 — sourced from Stooq per M0 Job 1",
    },
    {
        "benchmark_code": "GOLD",
        "benchmark_name": "Gold (GOLDBEES proxy)",
        "benchmark_type": "user/numeraire",
        "source_table": "de_etf_ohlcv",
        "source_identifier": "GOLDBEES",
        "description": "GOLDBEES NAV; serves as both user benchmark and gold numéraire",
    },
    # Tier benchmarks (drive within-tier RS)
    {
        "benchmark_code": "NIFTY100",
        "benchmark_name": "Nifty 100",
        "benchmark_type": "tier",
        "source_table": "de_index_prices",
        "source_identifier": "NIFTY 100",
        "description": "Tier benchmark for Large stocks",
    },
    {
        "benchmark_code": "NIFTY200",
        "benchmark_name": "Nifty 200",
        "benchmark_type": "tier",
        "source_table": "de_index_prices",
        "source_identifier": "NIFTY 200",
        "description": "Category benchmark for Large & Mid Cap funds",
    },
    {
        "benchmark_code": "MIDCAP150",
        "benchmark_name": "Nifty Midcap 150",
        "benchmark_type": "tier",
        "source_table": "de_index_prices",
        "source_identifier": "NIFTY MIDCAP 150",
        "description": "Tier benchmark for Mid stocks",
    },
    {
        "benchmark_code": "SMALLCAP250",
        "benchmark_name": "Nifty Smallcap 250",
        "benchmark_type": "tier",
        "source_table": "de_index_prices",
        "source_identifier": "NIFTY SMLCAP 250",
        "description": "Tier benchmark for Small stocks",
    },
    {
        "benchmark_code": "MICROCAP_CUSTOM",
        "benchmark_name": "Nifty Microcap 250 (v0 proxy)",
        "benchmark_type": "tier",
        "source_table": "de_index_prices",
        "source_identifier": "NIFTY MICROCAP250",
        "description": (
            "Tier benchmark for Micro stocks. v0: uses JIP's NIFTY MICROCAP250 "
            "directly. v1 will swap to an Atlas-constructed equal-weighted "
            "index of the 250 micro names (per methodology §6.2)."
        ),
    },
)


# Per methodology 12.1
_FUND_CATEGORY_MAP: tuple[tuple[str, str, str | None], ...] = (
    ("Large Cap Fund", "NIFTY100", None),
    ("Large & Mid Cap Fund", "NIFTY200", None),
    ("Mid Cap Fund", "MIDCAP150", None),
    ("Small Cap Fund", "SMALLCAP250", None),
    ("Multi Cap Fund", "NIFTY500", None),
    ("Flexi Cap Fund", "NIFTY500", None),
    ("ELSS", "NIFTY500", None),
    ("Sectoral / Thematic Fund", "NIFTY500", "Per-fund mapping deferred to v1"),
)


def populate_benchmark_master(engine: Engine | None = None) -> int:
    eng = engine or get_engine()
    insert_sql = text("""
        INSERT INTO atlas.atlas_benchmark_master
            (benchmark_code, benchmark_name, benchmark_type,
             source_table, source_identifier, description, is_active)
        VALUES
            (:benchmark_code, :benchmark_name, :benchmark_type,
             :source_table, :source_identifier, :description, TRUE)
        ON CONFLICT (benchmark_code) DO UPDATE SET
            benchmark_name = EXCLUDED.benchmark_name,
            benchmark_type = EXCLUDED.benchmark_type,
            source_table = EXCLUDED.source_table,
            source_identifier = EXCLUDED.source_identifier,
            description = EXCLUDED.description,
            updated_at = NOW()
    """)
    with eng.begin() as conn:
        for r in _BENCHMARKS:
            conn.execute(insert_sql, r)
    log.info("benchmark_master_populated", count=len(_BENCHMARKS))
    return len(_BENCHMARKS)


def populate_fund_category_benchmark_map(engine: Engine | None = None) -> int:
    eng = engine or get_engine()
    insert_sql = text("""
        INSERT INTO atlas.atlas_fund_category_benchmark_map
            (category_name, benchmark_code, notes)
        VALUES (:category_name, :benchmark_code, :notes)
        ON CONFLICT (category_name) DO UPDATE SET
            benchmark_code = EXCLUDED.benchmark_code,
            notes = EXCLUDED.notes
    """)
    rows = [
        {"category_name": cat, "benchmark_code": code, "notes": notes}
        for cat, code, notes in _FUND_CATEGORY_MAP
    ]
    with eng.begin() as conn:
        for r in rows:
            conn.execute(insert_sql, r)
    log.info("fund_category_benchmark_map_populated", count=len(rows))
    return len(rows)
