"""SP07: read-only atlas queries that back the tool registry.

Every function here is read-only: opens a connection with
``engine.connect()`` (never ``engine.begin()``) and returns plain Python
dicts/lists. SQL identifiers (column names, table names) are either bind
parameters or whitelisted constants — no user input is ever interpolated.

These functions are exposed to LLM tool callers via
``atlas.agents.tools.registry``. They are NOT public API; callers should
use the registry, not import these directly.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

# Whitelist for query_distribution_stats — only these (table, column) pairs
# are allowed. The SQL identifier substitution below is safe only because
# both halves come from this constant.
_DISTRIBUTION_WHITELIST: frozenset[tuple[str, str]] = frozenset(
    [
        ("atlas_stock_metrics_daily", "rs_pctile_3m"),
        ("atlas_stock_metrics_daily", "ema_ratio_50_200"),
        ("atlas_sector_metrics_daily", "rs_pctile_cross_sector"),
        ("atlas_sector_metrics_daily", "rs_velocity"),
        ("atlas_market_regime_daily", "pct_above_ema_50"),
        ("atlas_market_regime_daily", "ad_ratio"),
    ]
)

_VALID_SEVERITIES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3"})

_VALID_CONVICTION_TIERS: frozenset[str] = frozenset(
    {
        "tier_1_megacap",
        "tier_2_largecap",
        "tier_3_uppermid",
        "tier_4_lowermid",
        "tier_5_smallcap",
    }
)

_VALID_CONFIDENCE_LABELS: frozenset[str] = frozenset({"industry_grade", "baseline"})


def query_current_regime(engine: Engine) -> dict[str, Any]:
    """Return the latest row of ``mv_current_market_regime`` as a dict."""
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT date, regime_state, deployment_multiplier, "
                    "dislocation_active, india_vix, pct_above_ema_50, "
                    "pct_above_ema_200, pct_in_strong_states, ad_ratio, "
                    "net_new_highs, mcclellan_oscillator "
                    "FROM atlas.mv_current_market_regime LIMIT 1"
                )
            )
            .mappings()
            .fetchone()
        )
    if row is None:
        return {"available": False, "reason": "mv_current_market_regime is empty"}
    return {"available": True, **{k: _to_jsonable(v) for k, v in row.items()}}


def query_regime_history(engine: Engine, *, n_days: int = 5) -> list[dict[str, Any]]:
    """Return the last ``n_days`` regime daily rows, most recent first."""
    n = max(1, min(int(n_days), 30))
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT date, regime_state, deployment_multiplier, "
                    "dislocation_active "
                    "FROM atlas.atlas_market_regime_daily "
                    "ORDER BY date DESC LIMIT :lim"
                ),
                {"lim": n},
            )
            .mappings()
            .fetchall()
        )
    return [{k: _to_jsonable(v) for k, v in r.items()} for r in rows]


def query_sector_rotation_quadrants(engine: Engine) -> dict[str, Any]:
    """Return all sectors grouped by RRG quadrant plus an ``as_of`` date."""
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT sector_name, rrg_quadrant, rs_level, rs_velocity, "
                    "rs_pctile_cross_sector, sector_state, date "
                    "FROM atlas.mv_sector_rotation_state "
                    "ORDER BY rs_pctile_cross_sector DESC NULLS LAST"
                )
            )
            .mappings()
            .fetchall()
        )
    if not rows:
        return {"available": False, "reason": "mv_sector_rotation_state is empty"}

    quadrants: dict[str, list[dict[str, Any]]] = {
        "Leading": [],
        "Improving": [],
        "Weakening": [],
        "Lagging": [],
        "Unknown": [],
    }
    as_of: date | None = None
    for r in rows:
        q = str(r.get("rrg_quadrant") or "Unknown")
        quadrants.setdefault(q, []).append(
            {
                "sector": str(r["sector_name"]),
                "rs_level": _to_jsonable(r.get("rs_level")),
                "rs_velocity": _to_jsonable(r.get("rs_velocity")),
                "rs_pctile_cross_sector": _to_jsonable(r.get("rs_pctile_cross_sector")),
                "sector_state": str(r.get("sector_state") or ""),
            }
        )
        if as_of is None and r.get("date") is not None:
            as_of = r["date"]
    return {
        "available": True,
        "as_of": as_of.isoformat() if as_of else None,
        "n_sectors": len(rows),
        "quadrants": quadrants,
    }


def query_top_rs_stocks(
    engine: Engine, *, n: int = 10, sector: str | None = None
) -> list[dict[str, Any]]:
    """Return top-``n`` RS leader stocks, optionally filtered by sector."""
    lim = max(1, min(int(n), 50))
    with engine.connect() as conn:
        if sector:
            rows = (
                conn.execute(
                    text(
                        "SELECT symbol, company_name, sector, tier, rs_state, "
                        "rs_pctile_3m, momentum_state, state_since_date "
                        "FROM atlas.mv_rs_leaders_daily "
                        "WHERE LOWER(sector) LIKE :sector "
                        "ORDER BY rs_pctile_3m DESC NULLS LAST LIMIT :lim"
                    ),
                    {"sector": f"%{sector.lower()}%", "lim": lim},
                )
                .mappings()
                .fetchall()
            )
        else:
            rows = (
                conn.execute(
                    text(
                        "SELECT symbol, company_name, sector, tier, rs_state, "
                        "rs_pctile_3m, momentum_state, state_since_date "
                        "FROM atlas.mv_rs_leaders_daily "
                        "ORDER BY rs_pctile_3m DESC NULLS LAST LIMIT :lim"
                    ),
                    {"lim": lim},
                )
                .mappings()
                .fetchall()
            )
    return [{k: _to_jsonable(v) for k, v in r.items()} for r in rows]


def query_breakout_candidates(engine: Engine, *, n: int = 10) -> list[dict[str, Any]]:
    """Return today's breakout candidates (transitions INTO Leader/Strong)."""
    lim = max(1, min(int(n), 50))
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT symbol, company_name, sector, new_rs_state, "
                    "prior_rs_state, rs_pctile_3m, state_since_date "
                    "FROM atlas.mv_breakout_candidates "
                    "ORDER BY rs_pctile_3m DESC NULLS LAST LIMIT :lim"
                ),
                {"lim": lim},
            )
            .mappings()
            .fetchall()
        )
    return [{k: _to_jsonable(v) for k, v in r.items()} for r in rows]


def query_deterioration_watch(engine: Engine, *, n: int = 10) -> list[dict[str, Any]]:
    """Return today's deterioration watch (transitions OUT of Leader/Strong)."""
    lim = max(1, min(int(n), 50))
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT symbol, company_name, sector, prior_rs_state, "
                    "new_rs_state, rs_pctile_3m, state_since_date "
                    "FROM atlas.mv_deterioration_watch "
                    "ORDER BY rs_pctile_3m DESC NULLS LAST LIMIT :lim"
                ),
                {"lim": lim},
            )
            .mappings()
            .fetchall()
        )
    return [{k: _to_jsonable(v) for k, v in r.items()} for r in rows]


def query_recent_findings(
    engine: Engine, *, severity: str | None = None, n: int = 20
) -> list[dict[str, Any]]:
    """Return recent ``atlas_validator_findings`` rows, optionally filtered."""
    lim = max(1, min(int(n), 100))
    sev = severity.upper() if severity else None
    if sev is not None and sev not in _VALID_SEVERITIES:
        raise ValueError(f"severity must be one of {sorted(_VALID_SEVERITIES)} or None")
    with engine.connect() as conn:
        if sev:
            rows = (
                conn.execute(
                    text(
                        "SELECT finding_class, severity, surface, identifier, "
                        "expected_value, actual_value, first_seen, last_seen, "
                        "resolved_at "
                        "FROM atlas.atlas_validator_findings "
                        "WHERE severity = :sev "
                        "ORDER BY last_seen DESC LIMIT :lim"
                    ),
                    {"sev": sev, "lim": lim},
                )
                .mappings()
                .fetchall()
            )
        else:
            rows = (
                conn.execute(
                    text(
                        "SELECT finding_class, severity, surface, identifier, "
                        "expected_value, actual_value, first_seen, last_seen, "
                        "resolved_at "
                        "FROM atlas.atlas_validator_findings "
                        "ORDER BY last_seen DESC LIMIT :lim"
                    ),
                    {"lim": lim},
                )
                .mappings()
                .fetchall()
            )
    return [{k: _to_jsonable(v) for k, v in r.items()} for r in rows]


def query_finding_summary(engine: Engine, *, n_days: int = 7) -> dict[str, Any]:
    """Aggregate finding counts by severity/class over the last ``n_days``."""
    n = max(1, min(int(n_days), 90))
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT severity, finding_class, COUNT(*) AS n, "
                    "COUNT(*) FILTER (WHERE resolved_at IS NULL) AS unresolved "
                    "FROM atlas.atlas_validator_findings "
                    "WHERE last_seen >= NOW() - (:n || ' days')::interval "
                    "GROUP BY severity, finding_class "
                    "ORDER BY severity, finding_class"
                ),
                {"n": n},
            )
            .mappings()
            .fetchall()
        )
    return {
        "window_days": n,
        "by_severity_class": [{k: _to_jsonable(v) for k, v in r.items()} for r in rows],
    }


def query_distribution_stats(engine: Engine, *, metric_column: str, table: str) -> dict[str, Any]:
    """Return basic distribution stats for a whitelisted (table, column)."""
    if (table, metric_column) not in _DISTRIBUTION_WHITELIST:
        raise ValueError(
            f"(table, column) pair not in whitelist: "
            f"got ({table!r}, {metric_column!r}); "
            f"valid pairs: {sorted(_DISTRIBUTION_WHITELIST)}"
        )
    # SQL identifier substitution is safe: both halves were validated
    # against _DISTRIBUTION_WHITELIST above. Bind parameters cannot carry
    # SQL identifiers, so f-string interpolation is the only path; the
    # whitelist guard is the load-bearing safety check.
    col = metric_column
    select = (
        f"SELECT COUNT(*) AS n_rows, AVG({col})::float AS mean, "
        f"PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {col}) AS median, "
        f"PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY {col}) AS p95, "
        f"MIN({col}) AS min, MAX({col}) AS max, MAX(date) AS as_of"
    )
    from_where = (
        f"FROM atlas.{table} WHERE date >= CURRENT_DATE - INTERVAL '30 days' AND {col} IS NOT NULL"
    )
    sql = f"{select} {from_where}"
    with engine.connect() as conn:
        row = conn.execute(text(sql)).mappings().fetchone()
    if row is None or row.get("n_rows") in (None, 0):
        return {
            "available": False,
            "table": table,
            "column": metric_column,
            "reason": "no rows in last 30 days",
        }
    return {
        "available": True,
        "table": table,
        "column": metric_column,
        **{k: _to_jsonable(v) for k, v in row.items()},
    }


def query_latest_brief(engine: Engine) -> dict[str, Any] | None:
    """Return the latest ``atlas_daily_briefs`` row as a dict, or None."""
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT as_of_date, regime_state, regime_delta, narrative, "
                    "key_themes, regime_summary, top_sector_mentions, model, "
                    "prompt_version, generated_at "
                    "FROM atlas.atlas_daily_briefs "
                    "ORDER BY as_of_date DESC LIMIT 1"
                )
            )
            .mappings()
            .fetchone()
        )
    if row is None:
        return None
    return {k: _to_jsonable(v) for k, v in row.items()}


def query_top_conviction(
    engine: Engine,
    *,
    n: int = 10,
    tier: str | None = None,
    confidence_label: str | None = None,
) -> list[dict[str, Any]]:
    """Return top-N stocks by conviction_score from the production composite.

    ``tier`` and ``confidence_label`` are optional filters. Both are
    whitelist-validated; an unknown value is silently dropped (the LLM
    sometimes misspells categorical args).

    Returns rows from ``atlas_stock_conviction_daily`` joined to
    ``atlas_universe_stocks`` for the symbol + sector. ``conviction_score``
    is rescaled to 0-100 for the agent narrative.
    """
    lim = max(1, min(int(n), 50))
    filters = ["c.date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)"]
    params: dict[str, Any] = {"lim": lim}

    if tier and tier in _VALID_CONVICTION_TIERS:
        filters.append("c.tier = :tier")
        params["tier"] = tier
    if confidence_label and confidence_label in _VALID_CONFIDENCE_LABELS:
        filters.append("c.confidence_label = :cl")
        params["cl"] = confidence_label

    where_sql = " AND ".join(filters)
    sql = text(
        f"""
        SELECT
            c.instrument_id::text  AS instrument_id,
            u.symbol,
            u.sector,
            c.tier,
            ROUND((c.conviction_score * 100)::numeric, 1) AS conviction_score,
            c.confidence_label,
            c.backing_ic,
            c.weight_set_version
        FROM atlas.atlas_stock_conviction_daily c
        LEFT JOIN atlas.atlas_universe_stocks u
               ON u.instrument_id = c.instrument_id
        WHERE {where_sql}
        ORDER BY c.conviction_score DESC
        LIMIT :lim
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().fetchall()
    return [{k: _to_jsonable(v) for k, v in r.items()} for r in rows]


def query_tv_analysis(engine: Engine, *, symbol: str) -> dict[str, Any] | None:
    """Return cached TradingView screener metrics for one symbol from atlas.tv_metrics."""
    sql = text("""
        SELECT symbol, tv_recommend_label, recommend_all, recommend_ma,
               recommend_other, rsi_14, macd_macd, ema_20, ema_50, ema_200,
               atr_14, price, high_52w, low_52w, fetched_at
        FROM atlas.tv_metrics
        WHERE symbol = :sym
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"sym": symbol.upper()}).mappings().first()
    if row is None:
        return None
    return {k: _to_jsonable(v) for k, v in dict(row).items()}


def _to_jsonable(value: Any) -> Any:
    """Convert SQL-row values to JSON-serialisable primitives.

    Decimals → str (preserves precision for money-adjacent fields), dates →
    ISO strings, datetimes → ISO strings.
    """
    if value is None:
        return None
    name = type(value).__name__
    if name == "Decimal":
        return str(value)
    if name in {"date", "datetime"}:
        return value.isoformat()
    return value
