#!/usr/bin/env python3
# allow-large: TABLE_SPECS catalog (36 entries x ~10 lines each) is a single
# cohesive data structure — splitting would relocate, not reduce.
"""Atlas backend health check — populates atlas.atlas_data_health.

Runs LAST in the nightly chain at 03:30 IST (22:00 UTC). For every critical
table in the v6 backend, computes:
  - last_data_date     : MAX(date_column) in the table
  - expected_data_date : per-table target (today for IN, today-1 for global)
  - row_count          : total rows (or filtered to most-recent date for daily tables)
  - null_rate_critical : NULL rate on the column(s) that matter for the table
  - size_bytes         : pg_total_relation_size
  - status             : GREEN / YELLOW / RED

Writes ONE row per (check_date, schema, table) — idempotent UPSERT.

No Slack / email alerts per user direction (2026-05-27): RED rows ARE the
alert. Check status with:

  SELECT table_name, status, freshness_days_lag, notes
  FROM atlas.atlas_data_health
  WHERE check_date = CURRENT_DATE AND status != 'GREEN'
  ORDER BY status DESC, freshness_days_lag DESC;

Run on EC2:
  ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \\
    'cd ~/atlas-os && .venv/bin/python scripts/atlas_health_check.py'
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import structlog  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

log = structlog.get_logger()

ENV_PATH = Path("/home/ubuntu/atlas-compute/.env")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


@dataclass(frozen=True)
class TableSpec:
    """Specification for one health-check row."""

    schema: str
    table: str
    category: str  # 'raw' | 'calculated' | 'mv'
    source: str
    date_column: str | None  # None = use snapshot_date or no date column
    critical_columns: tuple[str, ...] = ()  # columns whose null-rate is tracked
    expected_lag_days: int = 0  # 0 = should be current; 1 = global (T-1)
    min_rows: int = 1
    null_threshold_yellow: float = 0.05
    null_threshold_red: float = 0.30
    notes_hint: str = ""


TABLE_SPECS: tuple[TableSpec, ...] = (
    # ============================================================
    # RAW INGEST TABLES
    # ============================================================
    TableSpec(
        schema="public",
        table="de_equity_ohlcv",
        category="raw",
        source="NSE bhavcopy (via JIP)",
        date_column="date",
        critical_columns=("close", "volume"),
        expected_lag_days=0,
        min_rows=500_000,
    ),
    TableSpec(
        schema="public",
        table="de_etf_ohlcv",
        category="raw",
        source="NSE bhavcopy",
        date_column="date",
        critical_columns=("close", "volume"),
        expected_lag_days=0,
        min_rows=100_000,
    ),
    TableSpec(
        schema="public",
        table="de_index_prices",
        category="raw",
        source="NSE bhavcopy",
        date_column="date",
        critical_columns=("close",),
        expected_lag_days=0,
        min_rows=50_000,
    ),
    TableSpec(
        schema="public",
        table="de_mf_nav_daily",
        category="raw",
        source="AMFI + Morningstar (mfapi.in)",
        date_column="nav_date",
        critical_columns=("nav",),
        expected_lag_days=1,
        min_rows=1_000_000,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_macro_daily",
        category="raw",
        source="JIP + yfinance",
        date_column="date",
        critical_columns=("usdinr", "dxy", "vix_9d"),
        expected_lag_days=1,
        min_rows=1000,
        null_threshold_yellow=0.20,
        null_threshold_red=0.50,
        notes_hint="FII/DII often lag — tracked separately",
    ),
    # ============================================================
    # CALCULATED TABLES (atlas pipeline output)
    # ============================================================
    TableSpec(
        schema="atlas",
        table="atlas_stock_metrics_daily",
        category="calculated",
        source="compute (M4)",
        date_column="date",
        critical_columns=("ret_3m", "rs_3m_nifty500"),
        expected_lag_days=1,
        min_rows=1_000_000,
        null_threshold_yellow=0.05,
        null_threshold_red=0.20,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_stock_states_daily",
        category="calculated",
        source="compute (M4)",
        date_column="date",
        critical_columns=("rs_state",),
        expected_lag_days=1,
        min_rows=1_000_000,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_sector_metrics_daily",
        category="calculated",
        source="compute (M3)",
        date_column="date",
        critical_columns=("bottomup_ret_3m", "bottomup_rs_3m_nifty500"),
        expected_lag_days=1,
        min_rows=50_000,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_sector_states_daily",
        category="calculated",
        source="compute (M3)",
        date_column="date",
        critical_columns=("sector_state",),
        expected_lag_days=1,
        min_rows=50_000,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_index_metrics_daily",
        category="calculated",
        source="compute (M3)",
        date_column="date",
        critical_columns=("ret_3m",),
        expected_lag_days=1,
        min_rows=10_000,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_etf_metrics_daily",
        category="calculated",
        source="compute (ETF pipeline)",
        date_column="date",
        critical_columns=("ret_3m", "rs_3m_benchmark"),
        expected_lag_days=1,
        min_rows=10_000,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_etf_states_daily",
        category="calculated",
        source="compute (ETF pipeline)",
        date_column="date",
        critical_columns=("rs_state",),
        expected_lag_days=1,
        min_rows=10_000,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_etf_decisions_daily",
        category="calculated",
        source="compute (ETF pipeline)",
        date_column="date",
        critical_columns=("is_investable",),
        expected_lag_days=1,
        min_rows=10_000,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_etf_scorecard",
        category="calculated",
        source="compute (ETF pipeline) + AMFI",
        date_column="snapshot_date",
        critical_columns=("composite_score", "premium_bps"),
        expected_lag_days=1,
        min_rows=30,
        null_threshold_yellow=0.10,
        null_threshold_red=0.50,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_stock_conviction_daily",
        category="calculated",
        source="compute (Atlas intelligence)",
        date_column="date",
        critical_columns=("conviction_score", "tier"),
        expected_lag_days=1,
        min_rows=5_000,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_scorecard_daily",
        category="calculated",
        source="compute (Atlas intelligence)",
        date_column="date",
        critical_columns=("family_trend", "rs_residual_6m"),
        expected_lag_days=1,
        min_rows=500,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_signal_calls",
        category="calculated",
        source="compute (Atlas intelligence)",
        date_column="date",
        critical_columns=("action", "confidence_unconditional"),
        expected_lag_days=1,
        min_rows=100,
    ),
    TableSpec(
        schema="atlas",
        table="atlas_etf_signal_calls",
        category="calculated",
        source="manual backfill (no nightly writer)",
        date_column=None,  # design-as-config: rows persist until exit; no daily cadence
        critical_columns=("action",),
        expected_lag_days=0,
        min_rows=1,
        notes_hint="Open ETF signals — no nightly writer; rows persist until exit",
    ),
    TableSpec(
        schema="atlas",
        table="atlas_cts_signals_daily",
        category="calculated",
        source="compute (SP09 CTS)",
        date_column="date",
        critical_columns=("stage",),
        expected_lag_days=1,
        min_rows=10_000,
    ),
    # ============================================================
    # MATERIALIZED VIEWS — 14 canonical v6 MVs
    # ============================================================
    TableSpec(
        schema="atlas",
        table="mv_current_market_regime",
        category="mv",
        source="mv",
        date_column=None,
        min_rows=1,
    ),
    TableSpec(
        schema="atlas",
        table="mv_market_regime_landing",
        category="mv",
        source="mv",
        date_column=None,
        min_rows=1,
    ),
    TableSpec(
        schema="atlas",
        table="mv_india_pulse",
        category="mv",
        source="mv",
        date_column="as_of_date",
        expected_lag_days=1,
        min_rows=2000,
    ),
    TableSpec(
        schema="atlas",
        table="mv_markets_rs_grid",
        category="mv",
        source="mv",
        date_column=None,
        min_rows=5,  # 9 benchmark rows by design — threshold below that
    ),
    TableSpec(
        schema="atlas",
        table="mv_markets_rs_detail_charts",
        category="mv",
        source="mv",
        date_column="as_of_date",
        expected_lag_days=1,
        min_rows=10_000,
    ),
    TableSpec(
        schema="atlas",
        table="mv_sector_cards",
        category="mv",
        source="mv",
        date_column="as_of_date",
        expected_lag_days=1,
        min_rows=40_000,
    ),
    TableSpec(
        schema="atlas",
        table="mv_sector_breadth",
        category="mv",
        source="mv",
        date_column="as_of_date",
        expected_lag_days=1,
        min_rows=40_000,
    ),
    TableSpec(
        schema="atlas",
        table="mv_sector_rrg",
        category="mv",
        source="mv",
        date_column="as_of_date",
        expected_lag_days=1,
        min_rows=20,
    ),
    TableSpec(
        schema="atlas",
        table="mv_sector_deepdive",
        category="mv",
        source="mv",
        date_column=None,
        min_rows=20,
    ),
    TableSpec(
        schema="atlas",
        table="mv_stock_list_v6",
        category="mv",
        source="mv",
        date_column=None,
        min_rows=500,
    ),
    TableSpec(
        schema="atlas",
        table="mv_stock_landscape",
        category="mv",
        source="mv",
        date_column="as_of_date",
        expected_lag_days=1,
        min_rows=500,
    ),
    TableSpec(
        schema="atlas",
        table="mv_stock_deepdive",
        category="mv",
        source="mv",
        date_column=None,
        min_rows=500,
    ),
    TableSpec(
        schema="atlas",
        table="mv_fund_list_v6",
        category="mv",
        source="mv",
        date_column=None,
        min_rows=100,
    ),
    TableSpec(
        schema="atlas",
        table="mv_fund_deepdive",
        category="mv",
        source="mv",
        date_column=None,
        min_rows=100,
    ),
    TableSpec(
        schema="atlas",
        table="mv_etf_list_v6",
        category="mv",
        source="mv",
        date_column="as_of_date",
        expected_lag_days=1,
        min_rows=30,
    ),
    TableSpec(
        schema="atlas",
        table="mv_etf_deepdive",
        category="mv",
        source="mv",
        date_column="as_of_date",
        expected_lag_days=1,
        min_rows=30,
    ),
    TableSpec(
        schema="atlas",
        table="mv_calls_performance",
        category="mv",
        source="mv",
        date_column=None,
        min_rows=1,
    ),
)


def check_table(conn, spec: TableSpec, check_date: date) -> dict:
    """Run all checks for one table; return a dict ready for UPSERT."""
    qualified = f"{spec.schema}.{spec.table}"

    # Row count
    try:
        row_count = (
            conn.execute(text(f"SELECT COUNT(*) FROM {qualified}")).scalar() or 0  # qualified built from TableSpec literals
        )
    except Exception as exc:
        return _row(
            spec,
            check_date,
            status="RED",
            row_count=0,
            notes=f"COUNT(*) failed: {exc.__class__.__name__}: {str(exc)[:200]}",
        )

    # Size on disk
    try:
        size_bytes = (
            conn.execute(
                text("SELECT pg_total_relation_size(:q::regclass)"),
                {"q": qualified},
            ).scalar()
            or 0
        )
    except Exception:
        size_bytes = None

    # Last data date
    last_date: date | None = None
    if spec.date_column:
        try:
            last_date = conn.execute(
                text(f"SELECT MAX({spec.date_column}) FROM {qualified}")
            ).scalar()
        except Exception as exc:
            return _row(
                spec,
                check_date,
                status="RED",
                row_count=row_count,
                size_bytes=size_bytes,
                notes=f"MAX({spec.date_column}) failed: {str(exc)[:200]}",
            )

    freshness_lag = (check_date - last_date).days if (spec.date_column and last_date) else None

    # Null rate on critical columns (computed against most-recent date if a
    # date column is defined, otherwise the whole table).
    null_rate: float | None = None
    if spec.critical_columns:
        if spec.date_column and last_date:
            scope = f"WHERE {spec.date_column} = '{last_date.isoformat()}'"
        else:
            scope = ""
        try:
            null_count_exprs = ", ".join(
                f"COUNT(*) FILTER (WHERE {c} IS NULL) AS n_{i}"
                for i, c in enumerate(spec.critical_columns)
            )
            row = (
                conn.execute(
                    text(
                        f"SELECT COUNT(*) AS total, {null_count_exprs} "
                        f"FROM {qualified} {scope}"
                    )
                )
                .mappings()
                .fetchone()
            )
            if row and row["total"]:
                total = row["total"]
                worst_nulls = max(row[f"n_{i}"] for i in range(len(spec.critical_columns)))
                null_rate = worst_nulls / total if total else None
        except Exception as exc:
            return _row(
                spec,
                check_date,
                status="RED",
                row_count=row_count,
                size_bytes=size_bytes,
                last_date=last_date,
                freshness_lag=freshness_lag,
                notes=f"null-rate check failed: {str(exc)[:200]}",
            )

    # Status decision
    status = "GREEN"
    notes_parts: list[str] = []

    if row_count < spec.min_rows:
        status = "RED"
        notes_parts.append(f"row_count {row_count} < min {spec.min_rows}")

    if spec.date_column and last_date:
        if freshness_lag is None:
            pass
        elif freshness_lag > spec.expected_lag_days + 2:
            status = "RED"
            notes_parts.append(
                f"freshness_lag {freshness_lag}d > expected {spec.expected_lag_days}d"
            )
        elif freshness_lag > spec.expected_lag_days:
            if status != "RED":
                status = "YELLOW"
            notes_parts.append(
                f"freshness_lag {freshness_lag}d > expected {spec.expected_lag_days}d"
            )
    elif spec.date_column and last_date is None:
        status = "RED"
        notes_parts.append("no rows in table")

    if null_rate is not None:
        if null_rate >= spec.null_threshold_red:
            status = "RED"
            notes_parts.append(f"null_rate {null_rate:.1%} >= red threshold")
        elif null_rate >= spec.null_threshold_yellow:
            if status != "RED":
                status = "YELLOW"
            notes_parts.append(f"null_rate {null_rate:.1%} >= yellow threshold")

    if spec.notes_hint and not notes_parts:
        notes_parts.append(spec.notes_hint)

    return _row(
        spec,
        check_date,
        status=status,
        row_count=row_count,
        size_bytes=size_bytes,
        last_date=last_date,
        freshness_lag=freshness_lag,
        null_rate=null_rate,
        notes="; ".join(notes_parts) or None,
    )


def _row(
    spec: TableSpec,
    check_date: date,
    *,
    status: str,
    row_count: int = 0,
    size_bytes: int | None = None,
    last_date: date | None = None,
    freshness_lag: int | None = None,
    null_rate: float | None = None,
    notes: str | None = None,
) -> dict:
    expected = check_date - timedelta(days=spec.expected_lag_days)
    return {
        "check_date": check_date.isoformat(),
        "schema_name": spec.schema,
        "table_name": spec.table,
        "category": spec.category,
        "source": spec.source,
        "last_data_date": last_date.isoformat() if last_date else None,
        "expected_data_date": expected.isoformat(),
        "freshness_days_lag": freshness_lag,
        "row_count": row_count,
        "null_rate_critical": round(null_rate, 4) if null_rate is not None else None,
        "size_bytes": size_bytes,
        "status": status,
        "notes": notes,
    }


_UPSERT_SQL = """
INSERT INTO atlas.atlas_data_health
  (check_date, schema_name, table_name, category, source,
   last_data_date, expected_data_date, freshness_days_lag,
   row_count, null_rate_critical, size_bytes, status, notes)
VALUES
  (:check_date, :schema_name, :table_name, :category, :source,
   :last_data_date, :expected_data_date, :freshness_days_lag,
   :row_count, :null_rate_critical, :size_bytes, :status, :notes)
ON CONFLICT (check_date, schema_name, table_name) DO UPDATE SET
  category           = EXCLUDED.category,
  source             = EXCLUDED.source,
  last_data_date     = EXCLUDED.last_data_date,
  expected_data_date = EXCLUDED.expected_data_date,
  freshness_days_lag = EXCLUDED.freshness_days_lag,
  row_count          = EXCLUDED.row_count,
  null_rate_critical = EXCLUDED.null_rate_critical,
  size_bytes         = EXCLUDED.size_bytes,
  status             = EXCLUDED.status,
  notes              = EXCLUDED.notes,
  checked_at         = now();
"""


def main() -> int:
    env = load_env()
    db_url = env.get("ATLAS_DB_URL")
    if not db_url:
        print("ERROR: ATLAS_DB_URL missing from .env", file=sys.stderr)
        return 1

    engine = create_engine(db_url, pool_pre_ping=True, pool_size=2)
    check_date = date.today()
    rows: list[dict] = []

    log.info("health_check_start", n_tables=len(TABLE_SPECS), check_date=str(check_date))

    # AUTOCOMMIT: each SELECT runs in its own implicit transaction so a single
    # failure (e.g. pg_total_relation_size on a partitioned parent) does not
    # poison subsequent checks in the loop.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for spec in TABLE_SPECS:
            row = check_table(conn, spec, check_date)
            rows.append(row)
            print(
                f"{row['status']:7s} {row['schema_name']}.{row['table_name']}  "
                f"last={row['last_data_date'] or '—':10s}  "
                f"lag={row['freshness_days_lag']}  "
                f"rows={row['row_count']:>12,}  "
                f"null={row['null_rate_critical']}  "
                f"{row['notes'] or ''}"
            )

    with engine.begin() as conn:
        for row in rows:
            conn.execute(text(_UPSERT_SQL), row)

    n_green = sum(1 for r in rows if r["status"] == "GREEN")
    n_yellow = sum(1 for r in rows if r["status"] == "YELLOW")
    n_red = sum(1 for r in rows if r["status"] == "RED")
    summary_line = (
        f"Summary  GREEN={n_green}  YELLOW={n_yellow}  RED={n_red}  (check_date={check_date})"
    )
    print(f"\n{summary_line}")

    # Human-readable status file — primary morning-check surface. No Slack/email
    # per user direction. `cat ~/atlas_status.txt` over ssh = full picture.
    try:
        with open("/home/ubuntu/atlas_status.txt", "w") as f:
            f.write(f"Atlas backend status — {check_date}\n")
            f.write(f"{summary_line}\n\n")
            if n_red:
                f.write("REDS (action required):\n")
                for r in rows:
                    if r["status"] == "RED":
                        f.write(
                            f"  {r['schema_name']}.{r['table_name']:<40s} "
                            f"last={r['last_data_date'] or '—'} "
                            f"notes: {r['notes'] or ''}\n"
                        )
                f.write("\n")
            if n_yellow:
                f.write("YELLOWS (acceptable but watch):\n")
                for r in rows:
                    if r["status"] == "YELLOW":
                        f.write(
                            f"  {r['schema_name']}.{r['table_name']:<40s} "
                            f"last={r['last_data_date'] or '—'} "
                            f"notes: {r['notes'] or ''}\n"
                        )
                f.write("\n")
            f.write("All tracked tables:\n")
            for r in sorted(rows, key=lambda x: (x["category"], x["table_name"])):
                f.write(
                    f"  [{r['status']:<6s}] {r['schema_name']}.{r['table_name']:<40s} "
                    f"last={r['last_data_date'] or '—':<10s} "
                    f"rows={r['row_count']:>12,}  ({r['category']})\n"
                )
    except Exception as exc:
        log.warning("status_file_write_failed", error=str(exc))

    return 0 if n_red == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
