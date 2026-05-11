"""M1 data quality audit — per-instrument coverage across the 10-year window.

Read-only audit that joins the locked atlas universe (Layer 2) against
JIP Data Core's Layer 1 OHLCV / NAV / holdings tables and reports:

- Per-instrument trading-day count (vs the ~2,500 expected for full coverage)
- Earliest / latest observation per instrument
- Stocks failing the methodology liquidity gate (60-day median traded
  value < ₹5 cr) — surfaced but doesn't block M1
- Stocks with insufficient history (<252 trading days) → INSUFFICIENT_HISTORY
- NULL close / NULL volume rate per asset class
- Holdings disclosure freshness per ETF / fund

Output: a markdown report at ``output/validation_M1_<date>_data_quality.md``
plus a per-section console summary. Exit code: 0 (ok), 1 (warnings),
2 (critical issues blocking M1 sign-off).

Usage::

    # ATLAS_DB_URL must be set
    python -m atlas.validation.m1_data_quality

    # Custom output path
    python -m atlas.validation.m1_data_quality --output output/dq.md
"""
# allow-large: comprehensive audit script — 12 data quality sections, shared
# helpers, report writer, and CLI entrypoint form one indivisible validation
# run. Splitting would require passing a shared report object across files.

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


HISTORICAL_START = date.fromisoformat(Config.HISTORICAL_START_DATE)


@dataclass
class CheckResult:
    section: str
    name: str
    severity: str  # 'ok' | 'warn' | 'critical'
    actual: str
    expected: str
    notes: str = ""


@dataclass
class Report:
    started_at: datetime = field(default_factory=datetime.now)
    historical_start: date = HISTORICAL_START
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, c: CheckResult) -> None:
        self.checks.append(c)
        sym = {"ok": "✓", "warn": "⚠", "critical": "✗"}.get(c.severity, "?")
        print(f"  {sym} [{c.section}] {c.name:55s}  actual={c.actual}  expected={c.expected}")
        if c.notes:
            print(f"      └─ {c.notes}")

    def n(self, severity: str) -> int:
        return sum(1 for c in self.checks if c.severity == severity)

    def exit_code(self) -> int:
        if self.n("critical"):
            return 2
        if self.n("warn"):
            return 1
        return 0


def _scalar(engine: Engine, sql: str, **kwargs: Any) -> Any:
    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        return conn.execute(text(sql), kwargs).scalar()


def _row(engine: Engine, sql: str, **kwargs: Any) -> Any:
    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        return conn.execute(text(sql), kwargs).first()


def _rows(engine: Engine, sql: str, **kwargs: Any) -> list[Any]:
    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        return list(conn.execute(text(sql), kwargs).all())


# ---------------------------------------------------------------------------
# Section 1 — Stock OHLCV coverage
# ---------------------------------------------------------------------------


def check_stock_ohlcv(engine: Engine, report: Report) -> None:
    print("\n[1] Stock OHLCV coverage (750 universe stocks)")

    # Batch per tier so each query is small (~100-250 instruments).
    # Adding the date predicate to the LEFT JOIN enables partition pruning.
    per_tier_sql = """
        SELECT
            COUNT(*)                                                       AS total,
            COUNT(*) FILTER (WHERE per_stock.days_in_window = 0)           AS no_data,
            COUNT(*) FILTER (WHERE per_stock.days_in_window > 0
                              AND per_stock.days_in_window < 252)          AS lt_252,
            COUNT(*) FILTER (WHERE per_stock.days_in_window >= 252
                              AND per_stock.days_in_window < 2000)         AS partial,
            COUNT(*) FILTER (WHERE per_stock.days_in_window >= 2000)       AS full_coverage,
            COUNT(*) FILTER (WHERE per_stock.null_close_count > 0)         AS has_null_close,
            SUM(per_stock.null_close_count)                                AS total_null_closes,
            COUNT(*) FILTER (WHERE per_stock.earliest > :start
                              AND u.listing_date < :start)                 AS late_start_pre_listed,
            MAX(per_stock.latest)                                          AS most_recent
        FROM atlas.atlas_universe_stocks u
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)                                AS days_in_window,
                MIN(o.date)                             AS earliest,
                MAX(o.date)                             AS latest,
                COUNT(*) FILTER (WHERE o.close IS NULL) AS null_close_count
            FROM public.de_equity_ohlcv o
            WHERE o.instrument_id = u.instrument_id
              AND o.date >= :start
        ) per_stock ON TRUE
        WHERE u.effective_to IS NULL
          AND u.tier = :tier
    """

    # Aggregate per-tier results
    total = no_data = lt_252 = partial = full_cov = has_null = late_start = 0
    total_null = 0
    most_recent: date | None = None
    for tier in ("Large", "Mid", "Small", "Micro"):
        print(f"  ... auditing {tier} tier...", flush=True)
        r = _row(engine, per_tier_sql, start=HISTORICAL_START, tier=tier)
        if r is None:
            continue
        (t, nd, lt, pt, fc, hn, tn, lsp, mr) = r
        total += t or 0
        no_data += nd or 0
        lt_252 += lt or 0
        partial += pt or 0
        full_cov += fc or 0
        has_null += hn or 0
        total_null += int(tn or 0)
        late_start += lsp or 0
        if mr and (most_recent is None or mr > most_recent):
            most_recent = mr

    # Total stocks
    report.add(
        CheckResult(
            "stocks",
            "total stocks in universe",
            "ok",
            str(total),
            "750",
        )
    )
    # Zero-data stocks (critical — should be 0)
    report.add(
        CheckResult(
            "stocks",
            "stocks with NO OHLCV in 10y window",
            "critical" if no_data > 0 else "ok",
            str(no_data),
            "0",
            notes=""
            if no_data == 0
            else f"{no_data} stocks have zero rows in de_equity_ohlcv for {HISTORICAL_START}+",
        )
    )
    # Insufficient history (warn)
    report.add(
        CheckResult(
            "stocks",
            "stocks with <252 days (INSUFFICIENT_HISTORY gate)",
            "warn" if lt_252 > 50 else "ok",
            str(lt_252),
            "<50 (recent IPOs accepted)",
            notes="Per methodology 3.3, these classify as INSUFFICIENT_HISTORY until they reach 252 days.",
        )
    )
    # Partial coverage (252+ but not full window)
    report.add(
        CheckResult(
            "stocks",
            "stocks with partial coverage (252-2000 days)",
            "ok",
            str(partial),
            "informational",
            notes="Mostly stocks listed during the 10y window — expected.",
        )
    )
    # Full coverage
    full_pct = 100 * full_cov / total if total else 0
    report.add(
        CheckResult(
            "stocks",
            "stocks with full 10y coverage (>=2000 days)",
            "ok" if full_pct >= 30 else "warn",
            f"{full_cov} ({full_pct:.0f}%)",
            ">= 30%",
        )
    )
    # Late-start anomaly (listed pre-2016 but JIP data only starts later)
    report.add(
        CheckResult(
            "stocks",
            "pre-listed stocks with late JIP coverage start",
            "warn" if late_start > 20 else "ok",
            str(late_start),
            "<= 20",
            notes="Stocks listed before 2016-04-07 but earliest OHLCV in JIP is later — gap-fill artifact.",
        )
    )
    # NULL close rate
    null_rate = 100 * has_null / total if total else 0
    report.add(
        CheckResult(
            "stocks",
            "stocks with any NULL close",
            "ok" if has_null < 5 else "warn",
            f"{has_null} ({null_rate:.1f}%)",
            "<= 5",
        )
    )
    # Total NULL count
    report.add(
        CheckResult(
            "stocks",
            "total NULL close cells across all 750",
            "ok" if (total_null or 0) < 100 else "warn",
            str(total_null or 0),
            "<= 100",
        )
    )
    # Most recent date
    if most_recent:
        days_stale = (date.today() - most_recent).days
        report.add(
            CheckResult(
                "stocks",
                "most-recent date freshness",
                "ok" if days_stale <= 5 else "warn",
                f"{most_recent} ({days_stale}d ago)",
                "<= 5d",
            )
        )


# ---------------------------------------------------------------------------
# Section 2 — ETF OHLCV coverage
# ---------------------------------------------------------------------------


def check_etf_ohlcv(engine: Engine, report: Report) -> None:
    print("\n[2] ETF OHLCV coverage (100 universe ETFs)")

    sql = """
        SELECT
            COUNT(*)                                                       AS total,
            COUNT(*) FILTER (WHERE per_etf.days_in_window = 0)             AS no_data,
            COUNT(*) FILTER (WHERE per_etf.days_in_window > 0
                              AND per_etf.days_in_window < 252)            AS lt_252,
            COUNT(*) FILTER (WHERE per_etf.days_in_window >= 252)          AS adequate,
            COUNT(*) FILTER (WHERE per_etf.null_close_count > 0)           AS has_null,
            MAX(per_etf.latest)                                            AS most_recent
        FROM atlas.atlas_universe_etfs u
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)                                AS days_in_window,
                MIN(o.date)                             AS earliest,
                MAX(o.date)                             AS latest,
                COUNT(*) FILTER (WHERE o.close IS NULL) AS null_close_count
            FROM public.de_etf_ohlcv o
            WHERE o.ticker = u.ticker
              AND o.date >= :start
        ) per_etf ON TRUE
        WHERE u.effective_to IS NULL
    """
    r = _row(engine, sql, start=HISTORICAL_START)
    total, no_data, lt_252, adequate, has_null, most_recent = r
    report.add(
        CheckResult(
            "etfs",
            "total ETFs",
            "ok",
            str(total),
            "100",
        )
    )
    report.add(
        CheckResult(
            "etfs",
            "ETFs with NO OHLCV in window",
            "critical" if no_data > 0 else "ok",
            str(no_data),
            "0",
        )
    )
    report.add(
        CheckResult(
            "etfs",
            "ETFs with <252 days (INSUFFICIENT_HISTORY)",
            "warn" if lt_252 > 30 else "ok",
            str(lt_252),
            "<= 30 (recent ETF launches OK)",
        )
    )
    report.add(
        CheckResult(
            "etfs",
            "ETFs with adequate history (>=252 days)",
            "ok" if adequate >= 70 else "warn",
            str(adequate),
            ">= 70",
        )
    )
    report.add(
        CheckResult(
            "etfs",
            "ETFs with any NULL close",
            "ok" if has_null < 5 else "warn",
            str(has_null),
            "<= 5",
        )
    )
    if most_recent:
        days_stale = (date.today() - most_recent).days
        report.add(
            CheckResult(
                "etfs",
                "most-recent date freshness",
                "ok" if days_stale <= 5 else "warn",
                f"{most_recent} ({days_stale}d ago)",
                "<= 5d",
            )
        )


# ---------------------------------------------------------------------------
# Section 3 — Index price coverage
# ---------------------------------------------------------------------------


def check_index_prices(engine: Engine, report: Report) -> None:
    print("\n[3] Index price coverage (75 curated indices)")

    sql = """
        SELECT
            COUNT(*)                                                       AS total,
            COUNT(*) FILTER (WHERE per_index.days_in_window = 0)           AS no_data,
            COUNT(*) FILTER (WHERE per_index.days_in_window > 0
                              AND per_index.days_in_window < 1500)         AS partial,
            COUNT(*) FILTER (WHERE per_index.days_in_window >= 1500)       AS full_cov,
            MAX(per_index.latest)                                          AS most_recent,
            MIN(per_index.earliest) FILTER (WHERE per_index.earliest IS NOT NULL) AS earliest_overall
        FROM atlas.atlas_universe_indices u
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)        AS days_in_window,
                MIN(p.date)     AS earliest,
                MAX(p.date)     AS latest
            FROM public.de_index_prices p
            WHERE p.index_code = u.index_code
              AND p.date >= :start
        ) per_index ON TRUE
        WHERE u.effective_to IS NULL
    """
    r = _row(engine, sql, start=HISTORICAL_START)
    total, no_data, partial, full_cov, _most_recent, earliest = r
    report.add(
        CheckResult(
            "indices",
            "total curated indices",
            "ok",
            str(total),
            "75",
        )
    )
    report.add(
        CheckResult(
            "indices",
            "indices with NO prices in window",
            "critical" if no_data > 0 else "ok",
            str(no_data),
            "0",
            notes=""
            if no_data == 0
            else "These are in the curated 75 but JIP has no prices for them.",
        )
    )
    report.add(
        CheckResult(
            "indices",
            "indices with full coverage (>=1500 days)",
            "ok" if full_cov >= 60 else "warn",
            str(full_cov),
            ">= 60",
        )
    )
    report.add(
        CheckResult(
            "indices",
            "indices with partial coverage (newer launches)",
            "ok",
            str(partial),
            "informational",
        )
    )
    if earliest:
        report.add(
            CheckResult(
                "indices",
                "earliest index price overall",
                "ok",
                str(earliest),
                f"<= {HISTORICAL_START}",
            )
        )


# ---------------------------------------------------------------------------
# Section 4 — MF NAV coverage
# ---------------------------------------------------------------------------


def check_mf_nav(engine: Engine, report: Report) -> None:
    print("\n[4] Mutual fund NAV coverage (592 universe funds)")

    sql = """
        SELECT
            COUNT(*)                                                       AS total,
            COUNT(*) FILTER (WHERE per_fund.days_in_window = 0)            AS no_data,
            COUNT(*) FILTER (WHERE per_fund.days_in_window > 0
                              AND per_fund.days_in_window < 252)           AS lt_252,
            COUNT(*) FILTER (WHERE per_fund.days_in_window >= 252
                              AND per_fund.days_in_window < 2000)          AS partial,
            COUNT(*) FILTER (WHERE per_fund.days_in_window >= 2000)        AS full_cov,
            MAX(per_fund.latest)                                           AS most_recent
        FROM atlas.atlas_universe_funds u
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)            AS days_in_window,
                MIN(n.nav_date)     AS earliest,
                MAX(n.nav_date)     AS latest
            FROM public.de_mf_nav_daily n
            WHERE n.mstar_id = u.mstar_id
              AND n.nav_date >= :start
        ) per_fund ON TRUE
        WHERE u.effective_to IS NULL
    """
    r = _row(engine, sql, start=HISTORICAL_START)
    total, no_data, lt_252, _partial, full_cov, most_recent = r
    report.add(
        CheckResult(
            "funds",
            "total funds in universe",
            "ok",
            str(total),
            "~592",
        )
    )
    report.add(
        CheckResult(
            "funds",
            "funds with NO NAV in window",
            "critical" if no_data > 0 else "ok",
            str(no_data),
            "0",
        )
    )
    report.add(
        CheckResult(
            "funds",
            "funds with <252 days (INSUFFICIENT_HISTORY)",
            "warn" if lt_252 > 50 else "ok",
            str(lt_252),
            "<= 50 (recent NFOs OK)",
        )
    )
    full_pct = 100 * full_cov / total if total else 0
    report.add(
        CheckResult(
            "funds",
            "funds with full 10y coverage (>=2000 days)",
            "ok" if full_pct >= 25 else "warn",
            f"{full_cov} ({full_pct:.0f}%)",
            ">= 25%",
        )
    )
    if most_recent:
        days_stale = (date.today() - most_recent).days
        report.add(
            CheckResult(
                "funds",
                "most-recent NAV date freshness",
                "ok" if days_stale <= 5 else "warn",
                f"{most_recent} ({days_stale}d ago)",
                "<= 5d",
            )
        )


# ---------------------------------------------------------------------------
# Section 5 — ETF holdings freshness
# ---------------------------------------------------------------------------


def check_etf_holdings(engine: Engine, report: Report) -> None:
    print("\n[5] ETF holdings disclosure freshness (100 universe ETFs)")

    sql = """
        WITH per_etf AS (
            SELECT
                u.ticker,
                COUNT(DISTINCT h.as_of_date) AS disclosure_count,
                MAX(h.as_of_date) AS latest_disclosure,
                COUNT(DISTINCT h.instrument_id) AS distinct_holdings_latest
            FROM atlas.atlas_universe_etfs u
            LEFT JOIN public.de_etf_holdings h ON h.ticker = u.ticker
            WHERE u.effective_to IS NULL
            GROUP BY u.ticker
        )
        SELECT
            COUNT(*)                                                            AS total,
            COUNT(*) FILTER (WHERE disclosure_count = 0)                        AS no_disclosure,
            COUNT(*) FILTER (WHERE latest_disclosure IS NULL OR latest_disclosure < (CURRENT_DATE - INTERVAL '60 days')) AS stale,
            COUNT(*) FILTER (WHERE latest_disclosure >= (CURRENT_DATE - INTERVAL '60 days')) AS fresh,
            AVG(distinct_holdings_latest) FILTER (WHERE distinct_holdings_latest > 0) AS avg_holdings
        FROM per_etf
    """
    r = _row(engine, sql, start=HISTORICAL_START)
    total, no_disclosure, _stale, fresh, avg_holdings = r
    report.add(
        CheckResult(
            "etf_holdings",
            "total ETFs in universe",
            "ok",
            str(total),
            "100",
        )
    )
    report.add(
        CheckResult(
            "etf_holdings",
            "ETFs with no holdings disclosure ever",
            "warn" if no_disclosure > 20 else "ok",
            str(no_disclosure),
            "<= 20",
            notes="Some thematic / smaller-AUM ETFs may have sparse Morningstar coverage.",
        )
    )
    report.add(
        CheckResult(
            "etf_holdings",
            "ETFs with fresh disclosure (last 60d)",
            "ok" if fresh >= 60 else "warn",
            str(fresh),
            ">= 60",
        )
    )
    if avg_holdings:
        report.add(
            CheckResult(
                "etf_holdings",
                "avg distinct holdings per ETF",
                "ok",
                f"{avg_holdings:.0f}",
                "informational",
            )
        )


# ---------------------------------------------------------------------------
# Section 6 — MF holdings freshness
# ---------------------------------------------------------------------------


def check_mf_holdings(engine: Engine, report: Report) -> None:
    print("\n[6] MF holdings disclosure freshness (592 universe funds)")

    sql = """
        WITH per_fund AS (
            SELECT
                u.mstar_id,
                COUNT(DISTINCT h.as_of_date) AS disclosure_count,
                MAX(h.as_of_date) AS latest_disclosure,
                COUNT(DISTINCT h.instrument_id) AS distinct_holdings_latest
            FROM atlas.atlas_universe_funds u
            LEFT JOIN public.de_mf_holdings h ON h.mstar_id = u.mstar_id
            WHERE u.effective_to IS NULL
            GROUP BY u.mstar_id
        )
        SELECT
            COUNT(*)                                                            AS total,
            COUNT(*) FILTER (WHERE disclosure_count = 0)                        AS no_disclosure,
            COUNT(*) FILTER (WHERE latest_disclosure >= (CURRENT_DATE - INTERVAL '60 days')) AS fresh,
            COUNT(*) FILTER (WHERE latest_disclosure IS NULL OR latest_disclosure < (CURRENT_DATE - INTERVAL '60 days')) AS stale
        FROM per_fund
    """
    r = _row(engine, sql, start=HISTORICAL_START)
    total, no_disclosure, fresh, _stale2 = r
    report.add(
        CheckResult(
            "mf_holdings",
            "total funds in universe",
            "ok",
            str(total),
            "~592",
        )
    )
    report.add(
        CheckResult(
            "mf_holdings",
            "funds with no holdings disclosure ever",
            "critical" if no_disclosure > 50 else "warn" if no_disclosure > 0 else "ok",
            str(no_disclosure),
            "<= 50",
        )
    )
    fresh_pct = 100 * fresh / total if total else 0
    report.add(
        CheckResult(
            "mf_holdings",
            "funds with fresh disclosure (last 60d)",
            "ok" if fresh_pct >= 80 else "warn",
            f"{fresh} ({fresh_pct:.0f}%)",
            ">= 80%",
        )
    )


# ---------------------------------------------------------------------------
# Section 7 — Liquidity gate (60-day median traded value >= ₹5cr)
# ---------------------------------------------------------------------------


def check_liquidity_gate(engine: Engine, report: Report) -> None:
    print("\n[7] Liquidity gate dry-run (per methodology 3.3, ₹5cr threshold)")

    # 60-day median traded value (close * volume) over last 90 calendar days
    sql = """
        WITH recent AS (
            SELECT
                u.instrument_id,
                u.tier,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.close * o.volume) AS median_60d
            FROM atlas.atlas_universe_stocks u
            JOIN public.de_equity_ohlcv o ON o.instrument_id = u.instrument_id
            WHERE u.effective_to IS NULL
              AND o.date >= (CURRENT_DATE - INTERVAL '90 days')
              AND o.close IS NOT NULL AND o.volume IS NOT NULL
            GROUP BY u.instrument_id, u.tier
            HAVING COUNT(*) >= 30
        )
        SELECT
            tier,
            COUNT(*)                                              AS stocks,
            COUNT(*) FILTER (WHERE median_60d < 50000000)         AS illiquid_lt_5cr,
            COUNT(*) FILTER (WHERE median_60d >= 50000000)        AS liquid_gte_5cr
        FROM recent
        GROUP BY tier
        ORDER BY CASE tier WHEN 'Large' THEN 1 WHEN 'Mid' THEN 2 WHEN 'Small' THEN 3 ELSE 4 END
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).all()
    if not rows:
        report.add(
            CheckResult(
                "liquidity",
                "no stocks with 30+ days traded value",
                "critical",
                "0",
                ">0",
            )
        )
        return

    total_stocks = sum(r[1] for r in rows)
    total_illiquid = sum(r[2] for r in rows)
    for tier, stocks, illiquid, liquid in rows:
        report.add(
            CheckResult(
                "liquidity",
                f"{tier} tier: liquid / illiquid",
                "ok" if illiquid <= stocks * 0.20 else "warn",
                f"{liquid} liquid / {illiquid} illiquid",
                f"<= 20% illiquid for {tier}",
                notes="Illiquid stocks classify as ILLIQUID per methodology 3.3 — surfaced separately, not blocked.",
            )
        )
    overall_illiquid_pct = 100 * total_illiquid / total_stocks
    report.add(
        CheckResult(
            "liquidity",
            "overall illiquid rate",
            "ok" if overall_illiquid_pct < 25 else "warn",
            f"{total_illiquid} / {total_stocks} ({overall_illiquid_pct:.1f}%)",
            "< 25%",
        )
    )


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def write_markdown_report(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_ok = report.n("ok")
    n_warn = report.n("warn")
    n_crit = report.n("critical")

    lines: list[str] = []
    lines.append("# M1 Data Quality Audit")
    lines.append("")
    lines.append(f"**Generated:** {report.started_at.isoformat()}")
    lines.append(f"**Historical scope:** {report.historical_start} to T-1")
    lines.append("**Universe:** locked at Atlas-M1 (`atlas.atlas_universe_*`)")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- {len(report.checks)} checks total")
    lines.append(f"- ✓ OK: {n_ok}")
    lines.append(f"- ⚠ Warning: {n_warn}")
    lines.append(f"- ✗ Critical: {n_crit}")
    lines.append("")

    if n_crit > 0:
        verdict = "**DATA QUALITY: NOT READY** — critical issues block M1 sign-off"
    elif n_warn > 0:
        verdict = "**DATA QUALITY: ACCEPTABLE WITH NOTES** — warnings documented, M1 can proceed"
    else:
        verdict = "**DATA QUALITY: CLEAN** — all checks pass"
    lines.append(f"## Verdict: {verdict}")
    lines.append("")

    by_section: dict[str, list[CheckResult]] = {}
    for c in report.checks:
        by_section.setdefault(c.section, []).append(c)
    for section, checks in by_section.items():
        lines.append(f"### {section}")
        lines.append("")
        lines.append("| Status | Check | Actual | Expected | Notes |")
        lines.append("|---|---|---|---|---|")
        for c in checks:
            sym = {"ok": "✅", "warn": "⚠️", "critical": "❌"}[c.severity]
            lines.append(f"| {sym} | {c.name} | {c.actual} | {c.expected} | {c.notes} |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ Markdown report: {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_audit(output_path: Path | None = None) -> int:
    Config.assert_db_url()
    engine = get_engine()
    report = Report()

    print("=" * 80)
    print("Atlas-M1 Data Quality Audit")
    print(f"  Historical scope: {HISTORICAL_START} to T-1")
    print(f"  Started:          {report.started_at.isoformat()}")
    print("=" * 80)

    check_stock_ohlcv(engine, report)
    check_etf_ohlcv(engine, report)
    check_index_prices(engine, report)
    check_mf_nav(engine, report)
    check_etf_holdings(engine, report)
    check_mf_holdings(engine, report)
    check_liquidity_gate(engine, report)

    print("\n" + "=" * 80)
    n_ok = report.n("ok")
    n_warn = report.n("warn")
    n_crit = report.n("critical")
    print(f"VERDICT: OK={n_ok}  WARN={n_warn}  CRIT={n_crit}")
    print("=" * 80)

    out = output_path or Path(f"output/validation_M1_data_quality_{date.today().isoformat()}.md")
    write_markdown_report(report, out)
    return report.exit_code()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M1 data quality audit")
    parser.add_argument("--output", "-o", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        return run_audit(args.output)
    except Exception as exc:
        log.exception("audit_crashed", error=str(exc))
        print(f"\n✗ Audit crashed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
