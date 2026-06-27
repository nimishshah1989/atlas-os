"""Strategy Lab nightly recommendation generator.

Reads the top-N genomes from atlas.atlas_strategy_leaderboard, runs each on
today's market state, and writes today's recommendations to
atlas.atlas_strategy_recommendations_daily.

Runs after the incubator step in run_atlas_intelligence_nightly.sh. The
goal-post-aligned persistent state: every morning, /strategies/lab/today
reads from this table to show what to buy with quantified confidence.

Pipeline per genome:
  1. Reconstruct Genome from atlas_strategy_genomes.genome_json
  2. Load last 60 days of metrics + regime (enough for state computation)
  3. Compute today's conviction matrix (full pipeline, not full simulation)
  4. Apply entry rules in today's regime
  5. Rank candidates by conviction, truncate at max_concurrent_positions
  6. Compute position size via Core 4 risk-parity formula
  7. Compute stop price from today's close × (1 − stop_loss_pct)
  8. Bucket confidence: HIGH if IR>=0.5 AND t-stat>=2, MEDIUM if IR>=0.3, LOW else
  9. UPSERT into atlas_strategy_recommendations_daily

No vectorbt simulation needed — we just need the model's view of today.

Usage:
  python scripts/strategy_lab_today.py [--top-n 3] [--date YYYY-MM-DD]

Env:
  ATLAS_DB_URL — required.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import structlog
from atlas.trading.decision import apply_entry_rules, compute_conviction
from atlas.trading.genome import Genome
from atlas.trading.perception import (
    compute_blended_rs_pctile,
    compute_rs_velocity,
    derive_momentum_state,
    derive_regime_state,
    derive_rs_state,
    derive_vol_state,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

log = structlog.get_logger()

_LOOKBACK_DAYS = 60
_DEFAULT_TOP_N = 3


def _confidence_band(ir: float, t_stat: float, hit_rate: float) -> str:
    """Bucket genome confidence for the recommendation row.

    HIGH:   IR >= 0.5 AND t-stat >= 2 AND hit_rate >= 0.6
    MEDIUM: IR >= 0.3 AND hit_rate >= 0.5
    LOW:    everything else
    """
    if ir >= 0.5 and t_stat >= 2.0 and hit_rate >= 0.6:
        return "HIGH"
    if ir >= 0.3 and hit_rate >= 0.5:
        return "MEDIUM"
    return "LOW"


def _load_top_genomes(conn: Connection, top_n: int) -> list[dict[str, Any]]:
    rows = (
        conn.execute(
            text(
                """
            SELECT
                l.genome_id::text, l.rank, l.strategy_name,
                l.alpha_oos, l.information_ratio, l.hit_rate, l.alpha_t_stat,
                g.genome_json
            FROM atlas.atlas_strategy_leaderboard l
            JOIN atlas.atlas_strategy_genomes g ON g.id = l.genome_id
            ORDER BY l.rank
            LIMIT :n
            """
            ),
            {"n": top_n},
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def _load_recent_data(
    conn: Connection, as_of: date, lookback_days: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start_date = as_of - timedelta(days=lookback_days)
    metrics = pd.DataFrame(
        conn.execute(
            text(
                """
                SELECT
                    m.instrument_id, m.date, p.close_adj AS close,
                    m.rs_pctile_1w, m.rs_pctile_1m, m.rs_pctile_3m,
                    m.vol_ratio_63, m.ema_20_ratio
                FROM atlas.atlas_stock_metrics_daily m
                JOIN public.de_equity_ohlcv p
                  ON p.instrument_id = m.instrument_id
                 AND p.date = m.date
                WHERE m.date BETWEEN :start AND :end
                  AND p.close_adj IS NOT NULL
                ORDER BY m.date, m.instrument_id
                """
            ),
            {"start": start_date, "end": as_of},
        )
        .mappings()
        .all()
    )
    regime = pd.DataFrame(
        conn.execute(
            text(
                """
                SELECT date, pct_above_ema_50, india_vix, nifty500_close
                FROM atlas.atlas_market_regime_daily
                WHERE date BETWEEN :start AND :end
                ORDER BY date
                """
            ),
            {"start": start_date, "end": as_of},
        )
        .mappings()
        .all()
    )
    return metrics, regime


def _compute_today_actions(
    genome: Genome,
    metrics_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    as_of: date,
) -> list[dict[str, Any]]:
    """Run the genome's perception + entry rules on today and return BUY actions.

    Returns a list of {instrument_id, conviction, position_size_pct, stop_price}
    dicts. HOLD/SELL detection requires portfolio state we don't have yet —
    those are added in Phase 4 (live tracking).
    """
    if metrics_df.empty or regime_df.empty:
        log.warning("today_no_data", as_of=str(as_of), genome_id=genome.genome_id)
        return []

    df = metrics_df.sort_values(["date", "instrument_id"])
    dates = sorted(df["date"].unique())
    if dates[-1] != as_of:
        log.warning(
            "today_data_stale",
            requested=str(as_of),
            last_available=str(dates[-1]),
            genome_id=genome.genome_id,
        )
        as_of = dates[-1]

    instruments = sorted(df["instrument_id"].unique())

    def _pivot(col: str) -> np.ndarray:
        pivoted = df.pivot(index="instrument_id", columns="date", values=col)
        return pivoted.reindex(index=instruments, columns=dates).values.astype(np.float32)

    close = _pivot("close")
    # Scale RS percentiles + breadth from DB's 0-1 representation to the 0-100
    # scale that genome thresholds and conviction normalization both assume.
    # Same fix as atlas/trading/simulator.py:_run_window.
    rs_arrays = {
        "1w": _pivot("rs_pctile_1w") * 100.0,
        "1m": _pivot("rs_pctile_1m") * 100.0,
        "3m": _pivot("rs_pctile_3m") * 100.0,
    }
    vol_ratio = _pivot("vol_ratio_63")
    ema_ratio = _pivot("ema_20_ratio")

    rdf = regime_df.set_index("date").reindex(dates)
    breadth = rdf["pct_above_ema_50"].values.astype(np.float32) * 100.0
    vix_arr = rdf["india_vix"].values.astype(np.float32)

    # CTS stage defaults (Stage 2 neutral) — keeps the entry rules functional
    # without requiring CTS columns to be present on every metrics row.
    n_stocks, n_days = close.shape
    cts_stage = np.full((n_stocks, n_days), 2, dtype=np.int8)
    ppc = np.zeros((n_stocks, n_days), dtype=np.int8)
    contraction = np.zeros((n_stocks, n_days), dtype=np.int8)

    blended_rs = compute_blended_rs_pctile(rs_arrays, genome.layer1.rs_timeframe_weights)
    rs_state = derive_rs_state(blended_rs, genome.layer1)
    regime_state = derive_regime_state(breadth, vix_arr, genome.layer1)
    vol_state = derive_vol_state(vol_ratio, genome.layer1)
    mom_state = derive_momentum_state(ema_ratio, genome.layer1)
    days_in_state, direction = compute_rs_velocity(
        rs_state, genome.layer1.state_velocity_lookback_days
    )

    # Only need today's conviction column — skip the full matrix loop.
    d = n_days - 1
    today_conv = np.zeros(n_stocks, dtype=np.float32)
    for s in range(n_stocks):
        if np.isnan(blended_rs[s, d]):
            continue
        today_conv[s] = compute_conviction(
            rs_pctile_norm=float(blended_rs[s, d]) / 100.0,
            rs_state=int(rs_state[s, d]),
            momentum_state=int(mom_state[s, d]),
            vol_state=int(vol_state[s, d]),
            days_in_state=int(days_in_state[s, d]),
            direction=int(direction[s, d]),
            layer1=genome.layer1,
            ppc=int(ppc[s, d]),
            contraction=int(contraction[s, d]),
        )

    today_regime = int(regime_state[d])
    today_stage = cts_stage[:, d]

    # Core 4 risk-parity sizing — same formula as simulator.
    risk_parity_size = float(genome.layer1.risk_per_trade_pct) / max(
        float(genome.layer1.stop_loss_pct), 0.001
    )
    eff_pos = min(risk_parity_size, float(genome.layer1.genome_max_position_pct))
    max_concurrent = int(genome.layer1.max_concurrent_positions)

    # Apply the genome's entry rules. portfolio_heat=0 because this is "today's
    # NEW entries with zero existing positions" — we're producing the model's
    # opinion on what to enter today, not maintaining a live portfolio yet.
    entry_mask = apply_entry_rules(
        conviction=today_conv,
        regime=today_regime,
        portfolio_heat=0.0,
        genome=genome,
        max_portfolio_heat_pct=float(genome.layer1.genome_max_heat_pct),
        stage=today_stage,
    )
    candidate_idx = np.where(entry_mask)[0]
    if len(candidate_idx) == 0:
        return []

    # Rank by conviction, truncate at max_concurrent_positions.
    top_k = candidate_idx[np.argsort(-today_conv[candidate_idx])[:max_concurrent]]

    actions: list[dict[str, Any]] = []
    for s in top_k:
        close_today = float(close[s, d])
        if not (close_today > 0):
            continue
        stop_price = close_today * (1.0 - float(genome.layer1.stop_loss_pct))
        actions.append(
            {
                "instrument_id": str(instruments[s]),
                "conviction": float(today_conv[s]),
                "position_size_pct": float(eff_pos),
                "stop_price": float(stop_price),
            }
        )
    return actions


def _write_recommendations(
    conn: Connection,
    as_of: date,
    genome_row: dict[str, Any],
    actions: list[dict[str, Any]],
) -> int:
    if not actions:
        return 0
    band = _confidence_band(
        ir=float(genome_row["information_ratio"]),
        t_stat=float(genome_row["alpha_t_stat"]),
        hit_rate=float(genome_row["hit_rate"]),
    )
    inserted = 0
    for a in actions:
        conn.execute(
            text(
                """
                INSERT INTO atlas.atlas_strategy_recommendations_daily
                    (date, genome_id, rank, instrument_id, action,
                     conviction, position_size_pct, stop_price,
                     genome_alpha_oos, genome_information_ratio,
                     genome_hit_rate, genome_t_stat, confidence_band)
                VALUES
                    (:date, CAST(:gid AS uuid), :rank, CAST(:iid AS uuid), 'BUY',
                     :conv, :pos_size, :stop_price,
                     :alpha, :ir, :hit_rate, :t_stat, :band)
                ON CONFLICT (date, genome_id, instrument_id, action)
                DO UPDATE SET
                    conviction = EXCLUDED.conviction,
                    position_size_pct = EXCLUDED.position_size_pct,
                    stop_price = EXCLUDED.stop_price,
                    confidence_band = EXCLUDED.confidence_band
                """
            ),
            {
                "date": as_of,
                "gid": genome_row["genome_id"],
                "rank": int(genome_row["rank"]),
                "iid": a["instrument_id"],
                "conv": Decimal(str(a["conviction"])),
                "pos_size": Decimal(str(a["position_size_pct"])),
                "stop_price": Decimal(str(a["stop_price"])),
                "alpha": Decimal(str(genome_row["alpha_oos"])),
                "ir": Decimal(str(genome_row["information_ratio"])),
                "hit_rate": Decimal(str(genome_row["hit_rate"])),
                "t_stat": Decimal(str(genome_row["alpha_t_stat"])),
                "band": band,
            },
        )
        inserted += 1
    return inserted


def run(top_n: int, as_of: date | None = None) -> dict[str, Any]:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise RuntimeError("ATLAS_DB_URL not set")
    engine = create_engine(db_url)
    target_date = as_of or date.today()
    total_written = 0
    summary: dict[str, Any] = {
        "date": str(target_date),
        "top_n": top_n,
        "genomes": [],
        "total_recommendations": 0,
    }
    with engine.connect() as conn:
        genomes = _load_top_genomes(conn, top_n)
        if not genomes:
            log.warning("no_leaderboard_genomes")
            summary["status"] = "aborted_no_genomes"
            return summary

        metrics_df, regime_df = _load_recent_data(conn, target_date, _LOOKBACK_DAYS)
        if metrics_df.empty:
            log.error("no_recent_metrics", as_of=str(target_date))
            summary["status"] = "aborted_no_metrics"
            return summary

        for row in genomes:
            genome_json = row["genome_json"]
            if isinstance(genome_json, str):
                genome_json = json.loads(genome_json)
            genome = Genome.from_dict(genome_json)
            actions = _compute_today_actions(genome, metrics_df, regime_df, target_date)
            inserted = _write_recommendations(conn, target_date, row, actions)
            total_written += inserted
            summary["genomes"].append(
                {
                    "genome_id": row["genome_id"],
                    "rank": int(row["rank"]),
                    "strategy_name": row["strategy_name"],
                    "recommendations": inserted,
                }
            )
            log.info(
                "genome_recommendations_written",
                genome_id=row["genome_id"],
                rank=row["rank"],
                inserted=inserted,
            )
        conn.commit()

    summary["total_recommendations"] = total_written
    summary["status"] = "ok"
    log.info("strategy_lab_today_done", **summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strategy Lab daily recommendations")
    parser.add_argument("--top-n", type=int, default=_DEFAULT_TOP_N)
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC).date(),
        default=None,
        help="As-of date, defaults to today",
    )
    args = parser.parse_args()
    result = run(top_n=args.top_n, as_of=args.date)
    print(json.dumps(result, indent=2))
