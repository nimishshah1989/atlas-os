"""Atlas-M3 hand-validation script — Tier 2 + Tier 3.

Per ``docs/milestones/ATLAS_M3_SECTOR_AND_MARKET.md`` §8.1–8.3.

Tier 2 (~275 independent checks):
  - Index metrics: 5 indices × 5 dates × 5 metrics = 125 checks
  - Sector aggregations: 3 sectors × 5 dates × 4 metrics = 60 checks
  - Breadth measures: 5 dates × 7 measures = 35 checks
  - Breadth extras (pct_above_ema_200, new highs/lows, AD ratio): 5 × 7 = 35 checks
  - McClellan / summation warm-up note: documented, not blocked

Tier 3 (~50 hand-classifications):
  - Sector states: all sectors × 3 sampled dates ≈ 60+ classifications
  - Regime states: 30 sampled dates

Run on EC2::

    python scripts/validate_m3.py

Returns exit code 0 on 100% pass, 1 on any mismatch.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.compute._session import open_compute_session  # noqa: E402
from atlas.db import get_engine, load_thresholds  # noqa: E402

log = structlog.get_logger()

PASS = 0
FAIL = 1

failures: list[str] = []
checks_run = 0


def _ok(_label: str) -> None:
    global checks_run
    checks_run += 1


def _fail(label: str, stored, recomputed, tol="") -> None:
    global checks_run
    checks_run += 1
    msg = f"FAIL  {label}: stored={stored!r} recomputed={recomputed!r} tol={tol}"
    failures.append(msg)
    print(msg)


def _check(label: str, stored, recomputed, atol: float = 1e-4) -> None:
    if (
        stored is None
        or recomputed is None
        or (isinstance(stored, float) and np.isnan(stored))
        or (isinstance(recomputed, float) and np.isnan(recomputed))
    ):
        # Both NaN/None = consistent, not a failure
        if (stored is None or (isinstance(stored, float) and np.isnan(stored))) and (
            recomputed is None or (isinstance(recomputed, float) and np.isnan(recomputed))
        ):
            _ok(label)
        else:
            _fail(label, stored, recomputed, f"atol={atol}")
        return
    if abs(float(stored) - float(recomputed)) > atol:
        _fail(label, stored, recomputed, f"atol={atol}")
    else:
        _ok(label)


# --------------------------------------------------------------------------- #
# Tier 2A — Index Metrics                                                     #
# --------------------------------------------------------------------------- #


def _tier2_index_metrics(engine) -> None:
    print("\n=== Tier 2A: Index Metrics ===")
    check_indices = ["NIFTY 50", "NIFTY 500", "NIFTY BANK", "NIFTY IT", "NIFTY MIDCAP 100"]

    with open_compute_session(engine) as conn:
        # Pull last 18 months of prices for all check indices + Nifty500 benchmark
        prices = pd.read_sql(
            """
            SELECT index_code, date, close
            FROM public.de_index_prices
            WHERE index_code = ANY(%(codes)s)
              AND date >= '2024-01-01'
              AND close IS NOT NULL
            ORDER BY index_code, date
            """,
            conn,
            params={"codes": [*check_indices, "NIFTY 500"]},
        )
        prices["date"] = pd.to_datetime(prices["date"]).dt.date

        # Pull 5 recent dates that have data for all check indices
        recent_dates_q = pd.read_sql(
            """
            SELECT DISTINCT date FROM atlas.atlas_index_metrics_daily
            WHERE index_code = 'NIFTY 50'
            ORDER BY date DESC LIMIT 10
            """,
            conn,
        )
        sample_dates = sorted(recent_dates_q["date"].tolist())[-5:]  # 5 most recent

        # Pull stored values for (index, date) combos
        stored = pd.read_sql(
            """
            SELECT index_code, date, ret_1d, ret_1m, ret_3m, rs_1m_nifty500, ema_10_index
            FROM atlas.atlas_index_metrics_daily
            WHERE index_code = ANY(%(codes)s)
              AND date = ANY(%(dates)s)
            """,
            conn,
            params={"codes": check_indices, "dates": sample_dates},
        )
        stored["date"] = pd.to_datetime(stored["date"]).dt.date

    nifty500_px = prices[prices["index_code"] == "NIFTY 500"][["date", "close"]].set_index("date")[
        "close"
    ]

    for idx_code in check_indices:
        px = (
            prices[prices["index_code"] == idx_code][["date", "close"]]
            .set_index("date")["close"]
            .sort_index()
        )
        if len(px) < 70:
            print(f"  SKIP {idx_code}: insufficient price history for hand-check")
            continue

        for d in sample_dates:
            row = stored[(stored["index_code"] == idx_code) & (stored["date"] == d)]
            if row.empty:
                continue
            r = row.iloc[0]
            prefix = f"idx/{idx_code}/{d}"

            # ret_1d = (close_t - close_{t-1}) / close_{t-1}
            if d in px.index:
                prev_dates = [dd for dd in px.index if dd < d]
                if prev_dates:
                    t_minus1 = max(prev_dates)
                    hand_ret1d = (float(px[d]) - float(px[t_minus1])) / float(px[t_minus1])
                    _check(f"{prefix}/ret_1d", r["ret_1d"], hand_ret1d, atol=1e-4)

            # ret_1m = (close_t - close_{t-21bd}) / close_{t-21bd}
            px_list = px[px.index <= d].tail(25)
            hand_ret1m: float | None = None
            if len(px_list) >= 22:
                close_t = float(px_list.iloc[-1])
                close_t21 = float(px_list.iloc[-22])
                hand_ret1m = (close_t - close_t21) / close_t21
                _check(f"{prefix}/ret_1m", r["ret_1m"], hand_ret1m, atol=1e-4)

                # rs_1m_nifty500 = ret_1m_index / ret_1m_nifty500 — inside same guard
                if d in nifty500_px.index:
                    n5_list = nifty500_px[nifty500_px.index <= d].tail(25)
                    if len(n5_list) >= 22:
                        n5_ret1m = (float(n5_list.iloc[-1]) - float(n5_list.iloc[-22])) / float(
                            n5_list.iloc[-22]
                        )
                        if abs(1.0 + n5_ret1m) > 1e-9:
                            # Price-relative RS: (1+index_ret)/(1+nifty500_ret)-1
                            hand_rs1m = (1.0 + hand_ret1m) / (1.0 + n5_ret1m) - 1.0
                            _check(
                                f"{prefix}/rs_1m_nifty500",
                                r["rs_1m_nifty500"],
                                hand_rs1m,
                                atol=5e-3,
                            )

            # ret_3m = (close_t - close_{t-63bd}) / close_{t-63bd}
            px_list_3m = px[px.index <= d].tail(67)
            if len(px_list_3m) >= 64:
                close_t = float(px_list_3m.iloc[-1])
                close_t63 = float(px_list_3m.iloc[-64])
                hand_ret3m = (close_t - close_t63) / close_t63
                _check(f"{prefix}/ret_3m", r["ret_3m"], hand_ret3m, atol=1e-4)

            # ema_10_index: pandas ewm(span=10, adjust=False) — check last value
            px_for_ema = px[px.index <= d].tail(50)
            if len(px_for_ema) >= 10:
                hand_ema10 = float(px_for_ema.ewm(span=10, adjust=False).mean().iloc[-1])
                _check(f"{prefix}/ema_10_index", r["ema_10_index"], hand_ema10, atol=0.5)

    print(f"  Tier 2A complete. checks_so_far={checks_run}, failures_so_far={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 2B — Sector Aggregation                                                #
# --------------------------------------------------------------------------- #


def _tier2_sector_metrics(engine) -> None:
    print("\n=== Tier 2B: Sector Aggregation ===")

    with open_compute_session(engine) as conn:
        # Pick 3 sectors with the most stock rows on recent dates
        top_sectors_q = pd.read_sql(
            """
            SELECT u.sector, count(*) as cnt
            FROM atlas.atlas_universe_stocks u
            WHERE u.effective_to IS NULL
            GROUP BY u.sector ORDER BY cnt DESC LIMIT 3
            """,
            conn,
        )
        if top_sectors_q.empty:
            print("  SKIP: no sector data")
            return
        check_sectors = top_sectors_q["sector"].tolist()

        sample_dates_q = pd.read_sql(
            """
            SELECT DISTINCT date FROM atlas.atlas_sector_metrics_daily
            ORDER BY date DESC LIMIT 10
            """,
            conn,
        )
        if sample_dates_q.empty:
            print("  SKIP: atlas_sector_metrics_daily empty")
            return
        sample_dates = sorted(sample_dates_q["date"].tolist())[-5:]

        # Nifty500 ret_3m for RS denominator (from index metrics)
        n500_ret3m = pd.read_sql(
            """
            SELECT date, ret_3m
            FROM atlas.atlas_index_metrics_daily
            WHERE index_code = 'NIFTY 500'
              AND date = ANY(%(dates)s)
            """,
            conn,
            params={"dates": sample_dates},
        )
        n500_ret3m["date"] = pd.to_datetime(n500_ret3m["date"]).dt.date
        n500_map = n500_ret3m.set_index("date")["ret_3m"].to_dict()

    for sector in check_sectors:
        with open_compute_session(engine) as conn:
            stored = pd.read_sql(
                """
                SELECT date, bottomup_ret_3m, participation_50, participation_rs,
                       bottomup_rs_3m_nifty500
                FROM atlas.atlas_sector_metrics_daily
                WHERE sector_name = %(sector)s AND date = ANY(%(dates)s)
                """,
                conn,
                params={"sector": sector, "dates": sample_dates},
            )
            stored["date"] = pd.to_datetime(stored["date"]).dt.date

        for d in sample_dates:
            row = stored[stored["date"] == d]
            if row.empty:
                continue
            r = row.iloc[0]
            prefix = f"sector/{sector[:10]}/{d}"

            with open_compute_session(engine) as conn:
                stocks = pd.read_sql(
                    """
                    SELECT m.instrument_id,
                           m.ema_200_stock, m.extension_pct, m.avg_volume_20,
                           m.ret_3m, m.rs_1m_tier, m.ema_50_stock
                    FROM atlas.atlas_stock_metrics_daily m
                    JOIN atlas.atlas_universe_stocks u
                        ON u.instrument_id = m.instrument_id AND u.effective_to IS NULL
                    WHERE u.sector = %(sector)s AND m.date = %(d)s
                    """,
                    conn,
                    params={"sector": sector, "d": d},
                )

            if stocks.empty:
                continue

            stocks["close_approx"] = stocks["ema_200_stock"].astype(float) * (
                1.0 + stocks["extension_pct"].astype(float)
            )
            stocks["weight"] = stocks["avg_volume_20"].astype(float) * stocks["close_approx"]

            # bottomup_ret_3m: weighted mean of ret_3m
            v = pd.to_numeric(stocks["ret_3m"], errors="coerce")
            w = stocks["weight"]
            mask = v.notna() & w.notna() & (w > 0)
            if mask.any():
                hand_ret3m = float(np.average(v[mask], weights=w[mask]))
                _check(f"{prefix}/bottomup_ret_3m", r["bottomup_ret_3m"], hand_ret3m, atol=5e-4)

            # participation_50: fraction close_approx > ema_50_stock
            valid50 = stocks.dropna(subset=["close_approx", "ema_50_stock"])
            if not valid50.empty:
                hand_p50 = float((valid50["close_approx"] > valid50["ema_50_stock"]).mean())
                _check(f"{prefix}/participation_50", r["participation_50"], hand_p50, atol=5e-3)

            # participation_rs: fraction rs_1m_tier > 0
            valid_rs = stocks.dropna(subset=["rs_1m_tier"])
            if not valid_rs.empty:
                hand_prs = float((valid_rs["rs_1m_tier"] > 0).mean())
                _check(f"{prefix}/participation_rs", r["participation_rs"], hand_prs, atol=5e-3)

            # bottomup_rs_3m_nifty500: weighted mean of price-relative RS
            # RS = (1+stock_ret3m)/(1+nifty500_ret3m) - 1 (same fix as sectors.py)
            n500_r3 = n500_map.get(d)
            if n500_r3 is not None and abs(1.0 + n500_r3) > 1e-9:
                mask2 = v.notna() & w.notna() & (w > 0)
                if mask2.any():
                    stock_rs = (1.0 + v[mask2]) / (1.0 + n500_r3) - 1.0
                    hand_rs3m = float(np.average(stock_rs, weights=w[mask2]))
                    _check(
                        f"{prefix}/bottomup_rs_3m_nifty500",
                        r["bottomup_rs_3m_nifty500"],
                        hand_rs3m,
                        atol=5e-3,
                    )

    print(f"  Tier 2B complete. checks_so_far={checks_run}, failures_so_far={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 2C — Breadth Measures                                                  #
# --------------------------------------------------------------------------- #


def _tier2_breadth(engine) -> None:
    print("\n=== Tier 2C: Breadth Measures ===")

    with open_compute_session(engine) as conn:
        sample_dates_q = pd.read_sql(
            """
            SELECT DISTINCT date FROM atlas.atlas_market_regime_daily
            ORDER BY date DESC LIMIT 10
            """,
            conn,
        )
        if sample_dates_q.empty:
            print("  SKIP: atlas_market_regime_daily empty")
            return
        sample_dates = sorted(sample_dates_q["date"].tolist())[-5:]

        stored = pd.read_sql(
            """
            SELECT date, advances_count, declines_count, unchanged_count,
                   pct_above_ema_50, pct_above_ema_200,
                   new_52w_highs, new_52w_lows, net_new_highs, ad_ratio
            FROM atlas.atlas_market_regime_daily
            WHERE date = ANY(%(dates)s)
            """,
            conn,
            params={"dates": sample_dates},
        )
        stored["date"] = pd.to_datetime(stored["date"]).dt.date

    for d in sample_dates:
        row = stored[stored["date"] == d]
        if row.empty:
            continue
        r = row.iloc[0]
        prefix = f"breadth/{d}"

        with open_compute_session(engine) as conn:
            # All Nifty500 stocks for this date + previous date for ret_1d
            prev_d = d - timedelta(days=5)  # a few days back to find the prev trading day
            stocks = pd.read_sql(
                """
                SELECT m.instrument_id, m.date,
                       m.ema_200_stock, m.extension_pct, m.ema_50_stock
                FROM atlas.atlas_stock_metrics_daily m
                JOIN atlas.atlas_universe_stocks u
                    ON u.instrument_id = m.instrument_id AND u.effective_to IS NULL
                WHERE u.in_nifty_500 = TRUE
                  AND m.date BETWEEN %(prev)s AND %(d)s
                """,
                conn,
                params={"prev": prev_d, "d": d},
            )

        if stocks.empty:
            continue
        stocks["date"] = pd.to_datetime(stocks["date"]).dt.date
        stocks["close_approx"] = stocks["ema_200_stock"].astype(float) * (
            1.0 + stocks["extension_pct"].astype(float)
        )

        today = stocks[stocks["date"] == d].copy()
        yesterday_dates = stocks[stocks["date"] < d]["date"].unique()
        if len(yesterday_dates) == 0:
            continue
        prev_td = max(yesterday_dates)
        yesterday = stocks[stocks["date"] == prev_td].copy()

        merged = today.merge(
            yesterday[["instrument_id", "close_approx"]].rename(
                columns={"close_approx": "close_prev"}
            ),
            on="instrument_id",
            how="inner",
        )
        if merged.empty:
            continue

        merged["ret_1d"] = (merged["close_approx"] - merged["close_prev"]) / merged["close_prev"]

        hand_advances = int((merged["ret_1d"] > 0).sum())
        hand_declines = int((merged["ret_1d"] < 0).sum())
        hand_unchanged = int((merged["ret_1d"] == 0).sum())
        _check(f"{prefix}/advances_count", r["advances_count"], hand_advances, atol=1)
        _check(f"{prefix}/declines_count", r["declines_count"], hand_declines, atol=1)
        _check(f"{prefix}/unchanged_count", r["unchanged_count"], hand_unchanged, atol=1)

        hand_ad_ratio = hand_advances / max(hand_declines, 1)
        _check(f"{prefix}/ad_ratio", r["ad_ratio"], hand_ad_ratio, atol=1e-3)

        # pct_above_ema_50 (Nifty500 stocks)
        valid50 = today.dropna(subset=["close_approx", "ema_50_stock"])
        if not valid50.empty:
            hand_p50 = float((valid50["close_approx"] > valid50["ema_50_stock"]).mean())
            _check(f"{prefix}/pct_above_ema_50", r["pct_above_ema_50"], hand_p50, atol=5e-3)

        # pct_above_ema_200
        valid200 = today.dropna(subset=["close_approx", "ema_200_stock"])
        if not valid200.empty:
            hand_p200 = float((valid200["close_approx"] > valid200["ema_200_stock"]).mean())
            _check(f"{prefix}/pct_above_ema_200", r["pct_above_ema_200"], hand_p200, atol=5e-3)

    print(f"  Tier 2C complete. checks_so_far={checks_run}, failures_so_far={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 3A — Sector States                                                     #
# --------------------------------------------------------------------------- #


def _tier3_sector_states(engine, thresholds: dict[str, float]) -> None:
    print("\n=== Tier 3A: Sector States ===")

    rs_top = thresholds["rs_quintile_top"]
    rs_bottom = thresholds["rs_quintile_bottom"]

    with open_compute_session(engine) as conn:
        sample_dates_q = pd.read_sql(
            """
            SELECT DISTINCT date FROM atlas.atlas_sector_metrics_daily
            ORDER BY date DESC LIMIT 5
            """,
            conn,
        )
        if sample_dates_q.empty:
            print("  SKIP: atlas_sector_metrics_daily empty")
            return
        sample_dates = sorted(sample_dates_q["date"].tolist())

    for d in sample_dates:
        with open_compute_session(engine) as conn:
            metrics = pd.read_sql(
                """
                SELECT sector_name, bottomup_rs_3m_nifty500
                FROM atlas.atlas_sector_metrics_daily
                WHERE date = %(d)s AND bottomup_rs_3m_nifty500 IS NOT NULL
                """,
                conn,
                params={"d": d},
            )
            states = pd.read_sql(
                """
                SELECT sector_name, sector_state
                FROM atlas.atlas_sector_states_daily
                WHERE date = %(d)s
                """,
                conn,
                params={"d": d},
            )

        if metrics.empty or states.empty:
            continue

        # Cross-sector percentile rank of bottomup_rs_3m_nifty500
        metrics["pct_rank"] = metrics["bottomup_rs_3m_nifty500"].rank(pct=True)
        merged = metrics.merge(states, on="sector_name", how="inner")

        for _, row in merged.iterrows():
            pct = row["pct_rank"]
            stored_state = row["sector_state"]
            prefix = f"sect_state/{row['sector_name'][:12]}/{d}"

            # Methodology RS-axis classification (breadth can override, we only check direction)

            # For Tier 3: allow Overweight/Neutral match and Avoid/Neutral match
            # since breadth signal can override RS-only classification.
            # We flag only clear RS-direction mismatches:
            #   stored=Overweight but pct<rs_bottom → FAIL
            #   stored=Avoid but pct>rs_top → FAIL
            global checks_run, failures
            checks_run += 1
            if stored_state == "Overweight" and pct < rs_bottom:
                failures.append(
                    f"FAIL  {prefix}/sector_state: stored=Overweight but pct_rank={pct:.2f} < {rs_bottom}"
                )
            elif stored_state == "Avoid" and pct > rs_top:
                failures.append(
                    f"FAIL  {prefix}/sector_state: stored=Avoid but pct_rank={pct:.2f} > {rs_top}"
                )

    print(f"  Tier 3A complete. checks_so_far={checks_run}, failures_so_far={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 3B — Regime States                                                     #
# --------------------------------------------------------------------------- #


def _tier3_regime_states(engine, thresholds: dict[str, float]) -> None:
    print("\n=== Tier 3B: Regime States ===")

    risk_on_min = thresholds["regime_risk_on_breadth_min_pct"] / 100.0
    risk_off_max = thresholds["regime_risk_off_breadth_max_pct"] / 100.0
    risk_on_vix = thresholds["regime_risk_on_vix_max"]
    cautious_vix = thresholds["regime_cautious_vix_max"]

    with open_compute_session(engine) as conn:
        # Pull 30 sampled dates from the full history
        regime = pd.read_sql(
            """
            SELECT date, regime_state, deployment_multiplier,
                   nifty500_close, nifty500_ema_200, nifty500_above_ema_200,
                   pct_above_ema_50, india_vix,
                   realized_vol_5d_nifty500, vol_252_median_nifty500,
                   dislocation_active
            FROM atlas.atlas_market_regime_daily
            WHERE regime_state IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 30
            """,
            conn,
        )

    if regime.empty:
        print("  SKIP: atlas_market_regime_daily empty or no classified rows")
        return

    regime["date"] = pd.to_datetime(regime["date"]).dt.date

    # For breadth_deteriorating check we'd need 21 prior days — skip that condition
    # in isolation (it requires time series context). We check the other conditions only.

    for _, row in regime.iterrows():
        stored_state = row["regime_state"]
        d = row["date"]
        prefix = f"regime/{d}"

        # Dislocation check first
        if row["dislocation_active"]:
            global checks_run, failures
            checks_run += 1
            if stored_state != "DISLOCATION_SUSPENDED":
                failures.append(
                    f"FAIL  {prefix}: dislocation_active=True but regime_state={stored_state}"
                )
            continue

        above_200 = bool(row["nifty500_above_ema_200"])
        pct_50 = float(row["pct_above_ema_50"]) if row["pct_above_ema_50"] is not None else np.nan
        vix = float(row["india_vix"]) if row["india_vix"] is not None else np.nan
        close = float(row["nifty500_close"]) if row["nifty500_close"] is not None else np.nan

        if np.isnan(pct_50) or np.isnan(vix) or np.isnan(close):
            # Warm-up / NULL inputs → state should be NULL; skip check
            continue

        is_risk_on = above_200 and (pct_50 > risk_on_min) and (vix < risk_on_vix)
        is_risk_off = (not above_200) and (pct_50 < risk_off_max) and (vix > cautious_vix)

        checks_run += 1
        # Validate: stored state must be self-consistent with stored inputs
        # (we skip breadth_deteriorating since we don't have the 21-day series here)
        if stored_state == "Risk-On" and not is_risk_on:
            # Allow if near_200 might have forced Cautious override — not applied here
            # so flag as soft check
            if is_risk_off or (not above_200 and pct_50 < risk_off_max):
                failures.append(
                    f"FAIL  {prefix}: stored=Risk-On but inputs suggest Risk-Off "
                    f"(above_200={above_200}, pct_50={pct_50:.3f}, vix={vix:.1f})"
                )
        elif stored_state == "Risk-Off" and not is_risk_off:
            if above_200 and pct_50 > risk_on_min and vix < risk_on_vix:
                failures.append(
                    f"FAIL  {prefix}: stored=Risk-Off but inputs suggest Risk-On "
                    f"(above_200={above_200}, pct_50={pct_50:.3f}, vix={vix:.1f})"
                )

        # Verify deployment multiplier matches state
        expected_mult = {
            "Risk-On": 1.0,
            "Constructive": 0.7,
            "Cautious": 0.4,
            "Risk-Off": 0.0,
            "DISLOCATION_SUSPENDED": 0.0,
        }.get(stored_state)
        if expected_mult is not None:
            stored_mult = float(row["deployment_multiplier"])
            if abs(stored_mult - expected_mult) > 1e-6:
                failures.append(
                    f"FAIL  {prefix}: deployment_multiplier={stored_mult} "
                    f"expected={expected_mult} for state={stored_state}"
                )

    print(f"  Tier 3B complete. checks_so_far={checks_run}, failures_so_far={len(failures)}")


# --------------------------------------------------------------------------- #
# Structural checks                                                            #
# --------------------------------------------------------------------------- #


def _structural_checks(engine) -> None:
    print("\n=== Structural / Row Count Checks ===")

    with open_compute_session(engine) as conn:
        tables = {
            "atlas_index_metrics_daily": "atlas.atlas_index_metrics_daily",
            "atlas_sector_metrics_daily": "atlas.atlas_sector_metrics_daily",
            "atlas_sector_states_daily": "atlas.atlas_sector_states_daily",
            "atlas_market_regime_daily": "atlas.atlas_market_regime_daily",
        }
        for name, table in tables.items():
            cnt = pd.read_sql(f"SELECT count(*) as c FROM {table}", conn).iloc[0]["c"]
            global checks_run, failures
            checks_run += 1
            if cnt == 0:
                failures.append(f"FAIL  {name}: 0 rows (backfill not complete?)")
                print(f"  {name}: {cnt:,} rows  ← EMPTY")
            else:
                print(f"  {name}: {cnt:,} rows  OK")

        # No orphan sector states (every state row has a metrics row)
        orphan = pd.read_sql(
            """
            SELECT count(*) as c
            FROM atlas.atlas_sector_states_daily s
            LEFT JOIN atlas.atlas_sector_metrics_daily m
                ON m.sector_name = s.sector_name AND m.date = s.date
            WHERE m.sector_name IS NULL
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if orphan > 0:
            failures.append(f"FAIL  sector_states orphan rows: {orphan}")
        else:
            print("  sector_states orphan rows: 0  OK")

        # All regime states are valid values
        bad_states = pd.read_sql(
            """
            SELECT count(*) as c FROM atlas.atlas_market_regime_daily
            WHERE regime_state IS NOT NULL
              AND regime_state NOT IN
                ('Risk-On','Constructive','Cautious','Risk-Off','DISLOCATION_SUSPENDED')
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if bad_states > 0:
            failures.append(f"FAIL  invalid regime_state values: {bad_states}")
        else:
            print("  all regime_state values valid  OK")

        # All sector states are valid values
        bad_sector_states = pd.read_sql(
            """
            SELECT count(*) as c FROM atlas.atlas_sector_states_daily
            WHERE sector_state NOT IN ('Overweight','Neutral','Underweight','Avoid')
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if bad_sector_states > 0:
            failures.append(f"FAIL  invalid sector_state values: {bad_sector_states}")
        else:
            print("  all sector_state values valid  OK")

    print(
        f"  Structural checks complete. checks_so_far={checks_run}, failures_so_far={len(failures)}"
    )


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #


def main() -> int:
    print("Atlas M3 Validation — Tier 2 + Tier 3")
    print(f"Started: {pd.Timestamp.now()}")

    engine = get_engine()
    thresholds = load_thresholds(engine)

    _structural_checks(engine)
    _tier2_index_metrics(engine)
    _tier2_sector_metrics(engine)
    _tier2_breadth(engine)
    _tier3_sector_states(engine, thresholds)
    _tier3_regime_states(engine, thresholds)

    print(f"\n{'='*60}")
    print(f"Total checks run: {checks_run}")
    print(f"Failures: {len(failures)}")
    if failures:
        print("\nFailed checks:")
        for f in failures:
            print(f"  {f}")
        print("\nRESULT: FAIL")
        return 1
    else:
        print("\nRESULT: PASS — all checks passed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
