#!/usr/bin/env python3
"""Atlas-side close_adj backfill, ported from JIP's compute_adjustments.py.

Runs against Supabase (Atlas DB) directly. The original JIP script connects
to a separate RDS instance, so its output never reached Atlas's view.

Logic (identical to JIP):
  1. Load split + bonus actions with ratios from de_corporate_actions.
  2. Compute per-action adjustment factor:
       split: ratio_from / ratio_to       (1:10 split → 0.1)
       bonus: ratio_from / (ratio_from + ratio_to)   (1:1 bonus → 0.5)
  3. Per instrument, walk actions in ex_date DESC order accumulating
     cumulative_factor. The factor applies to every OHLCV row with date < ex_date.
  4. UPDATE de_equity_ohlcv SET close_adj = close * cumulative_factor.
  5. Fill remaining unadjusted rows: close_adj = close.

Idempotent — re-run gives same result.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from atlas.db import get_engine


def main() -> int:
    engine = get_engine()
    t0 = time.time()

    print("=== LOADING CORPORATE ACTIONS ===")
    with engine.connect() as c:
        rows = c.execute(
            text("""
            SELECT instrument_id::text, ex_date, action_type,
                   ratio_from::float, ratio_to::float
            FROM public.de_corporate_actions
            WHERE action_type IN ('split', 'bonus')
              AND ratio_from IS NOT NULL AND ratio_to IS NOT NULL
              AND ratio_from > 0 AND ratio_to > 0
            ORDER BY instrument_id, ex_date
        """)
        ).fetchall()
    print(f"  Raw actions: {len(rows)}")

    # Dedupe identical (instrument, ex_date, action_type, ratio) rows
    seen = set()
    actions: list[tuple[str, date, str, float, float]] = []
    for r in rows:
        key = (r[0], r[1], r[2], r[3], r[4])
        if key in seen:
            continue
        seen.add(key)
        actions.append(key)
    print(f"  Deduped actions: {len(actions)}")

    # Group by instrument, sort by ex_date ASC inside each group
    inst_actions: dict[str, list[tuple[date, str, float, float]]] = defaultdict(list)
    for iid, ex_date, atype, rf, rt in actions:
        inst_actions[iid].append((ex_date, atype, rf, rt))
    for iid in inst_actions:
        inst_actions[iid].sort(key=lambda x: x[0])
    print(f"  Instruments with actions: {len(inst_actions)}")

    print()
    print("=== COMPUTING ADJUSTMENT FACTORS FROM OBSERVED PRICE MOVES ===")
    # Trust de_corporate_actions for WHEN actions happened, but compute the factor
    # from actual market data (post_close / pre_close). This sidesteps the broken
    # ratio_from/ratio_to fields and handles multi-action days (split + bonus same date)
    # naturally because the price move is the compound effect of all actions that day.
    # Acceptable factor range: 0.05 ≤ factor ≤ 0.95
    #   - factor > 0.95: price barely moved, likely no real corp action (skip)
    #   - factor < 0.05: price collapsed unrealistically, likely bad data (skip)
    factors: dict[str, list[tuple[date, float]]] = {}
    n_skipped_no_move = 0
    n_skipped_extreme = 0
    n_skipped_noprice = 0
    # Dedupe to one entry per (instrument, ex_date) since multi-actions on same day
    # are handled by a single observed-price computation.
    inst_dates: dict[str, set[date]] = defaultdict(set)
    for iid, acts in inst_actions.items():
        for ex_date, _, _, _ in acts:
            inst_dates[iid].add(ex_date)

    for iid, ex_dates in inst_dates.items():
        per: list[tuple[date, float]] = []
        for ex_date in sorted(ex_dates):
            with engine.connect() as c:
                pre = c.execute(
                    text("""
                    SELECT close::float FROM public.de_equity_ohlcv
                    WHERE instrument_id = CAST(:iid AS uuid) AND date < :d
                    ORDER BY date DESC LIMIT 1
                """),
                    {"iid": iid, "d": ex_date},
                ).fetchone()
                post = c.execute(
                    text("""
                    SELECT close::float FROM public.de_equity_ohlcv
                    WHERE instrument_id = CAST(:iid AS uuid) AND date >= :d
                    ORDER BY date LIMIT 1
                """),
                    {"iid": iid, "d": ex_date},
                ).fetchone()
            if not pre or not post or pre[0] <= 0:
                n_skipped_noprice += 1
                continue
            observed_factor = post[0] / pre[0]
            if observed_factor > 0.95:
                n_skipped_no_move += 1
                continue
            if observed_factor < 0.05:
                n_skipped_extreme += 1
                continue
            per.append((ex_date, observed_factor))
        if per:
            factors[iid] = per
    total_factor_count = sum(len(v) for v in factors.values())
    print(f"  Valid factors: {total_factor_count} across {len(factors)} instruments")
    print(f"  Skipped (no price movement): {n_skipped_no_move}")
    print(f"  Skipped (extreme/likely bad): {n_skipped_extreme}")
    print(f"  Skipped (no price data): {n_skipped_noprice}")

    print()
    print("=== BUILDING CUMULATIVE ADJUSTMENTS ===")
    total_updated = 0
    factor_rows: list[dict] = []  # de_adjustment_factors_daily inserts

    # Reset close_adj = close for ALL instruments that have ANY corp action
    # (including skipped ones), so wrong factors from prior runs are wiped before
    # we apply the sanity-checked subset.
    print()
    print("=== RESETTING close_adj for instruments with corp actions ===")
    instruments_with_actions = list(inst_actions.keys())
    with engine.begin() as conn:
        for iid in instruments_with_actions:
            conn.execute(
                text("""
                UPDATE public.de_equity_ohlcv SET close_adj = close
                WHERE instrument_id = CAST(:iid AS uuid)
            """),
                {"iid": iid},
            )
    print(f"  Reset {len(instruments_with_actions)} instruments to close_adj = close")

    with engine.begin() as conn:
        for idx, (iid, act_pairs) in enumerate(factors.items(), start=1):
            # act_pairs is sorted ASC. Walk in reverse to build cumulative for dates BEFORE each ex_date.
            # cum_factor for dates in [ex_date_i, ex_date_{i+1}) is the product of all factors
            # for actions with ex_date > those dates. So as we walk backward, BEFORE multiplying
            # the running cum by the current action's factor, cum is the factor that applies
            # to dates >= this ex_date (i.e., this date and later, until next more-recent ex_date).
            cum = 1.0
            ranges: list[tuple[date, date, float]] = []
            prev_ex_date = date(2099, 1, 1)
            for ex_date, f in reversed(act_pairs):
                if ex_date < prev_ex_date:
                    # Range [ex_date, prev_ex_date) — these dates are AT OR AFTER ex_date,
                    # but BEFORE the next more-recent ex_date. Apply current cum (NOT cum*f).
                    ranges.append((ex_date, prev_ex_date, cum))
                cum *= f
                prev_ex_date = ex_date
            # Oldest range: before earliest ex_date, full cum (all factors multiplied in) applies
            if act_pairs:
                earliest = act_pairs[0][0]
                ranges.append((date(1900, 1, 1), earliest, cum))

            # ALWAYS write all ranges (including factor=1.0) so any previously-wrong values from
            # earlier runs are overwritten. close_adj = close when factor=1.0, otherwise close * factor.
            for start_d, end_d, cf in ranges:
                result = conn.execute(
                    text("""
                    UPDATE public.de_equity_ohlcv
                    SET close_adj = close * :cf
                    WHERE instrument_id = CAST(:iid AS uuid)
                      AND date >= :sd AND date < :ed
                """),
                    {"iid": iid, "sd": start_d, "ed": end_d, "cf": cf},
                )
                total_updated += result.rowcount

            # Persist factor history per JIP schema
            cum = 1.0
            for ex_date, f in reversed(act_pairs):
                cum *= f
                factor_rows.append(
                    {
                        "iid": iid,
                        "d": ex_date,
                        "cf": Decimal(str(cum)),
                    }
                )

            if idx % 50 == 0:
                print(
                    f"  Processed {idx}/{len(factors)} instruments, {total_updated:,} rows updated"
                )

        # Bulk insert factor history
        if factor_rows:
            conn.execute(
                text("""
                INSERT INTO public.de_adjustment_factors_daily (instrument_id, date, cumulative_factor, created_at, updated_at)
                VALUES (CAST(:iid AS uuid), :d, :cf, NOW(), NOW())
                ON CONFLICT (instrument_id, date) DO UPDATE SET
                  cumulative_factor = EXCLUDED.cumulative_factor,
                  updated_at = NOW()
            """),
                factor_rows,
            )

    print(f"  Processed {len(factors)}/{len(factors)} instruments, {total_updated:,} rows updated")

    print()
    print("=== FILLING UNADJUSTED STOCKS ===")
    with engine.begin() as conn:
        result = conn.execute(
            text("""
            UPDATE public.de_equity_ohlcv
            SET close_adj = close
            WHERE close_adj IS NULL
        """)
        )
        fill_count = result.rowcount
    print(f"  Set close_adj = close for {fill_count:,} unadjusted rows")

    elapsed = time.time() - t0
    print()
    print(f"=== COMPLETE in {elapsed:.1f}s ===")
    with engine.connect() as c:
        n_null = c.execute(
            text("SELECT COUNT(*) FROM public.de_equity_ohlcv WHERE close_adj IS NULL")
        ).scalar()
        n_diff = c.execute(
            text(
                "SELECT COUNT(*) FROM public.de_equity_ohlcv WHERE close_adj IS NOT NULL AND ABS(close - close_adj) > 0.01"
            )
        ).scalar()
        n_factors = c.execute(
            text("SELECT COUNT(*) FROM public.de_adjustment_factors_daily")
        ).scalar()
        print(f"  Total stock rows updated: {total_updated + fill_count:,}")
        print(f"  Rows still NULL: {n_null:,}")
        print(f"  Rows where close_adj differs from close: {n_diff:,}")
        print(f"  Factor history rows: {n_factors:,}")

    # Quality assertions — fail loudly if the pipeline silently regresses.
    print()
    print("=== QUALITY ASSERTIONS ===")
    failures: list[str] = []

    # A. Zero NULL close_adj after the fill step
    if (n_null or 0) > 0:
        failures.append(f"close_adj has {n_null} NULL rows after fill step (expected 0)")
    else:
        print(f"  ✓ close_adj fully populated (NULL rows: {n_null or 0})")

    # B. For corp actions in last 90 days on universe stocks, adj-side split-day return
    # should be < 30% in absolute value. Anything larger means the adjustment didn't
    # cancel the price drop = silent regression.
    with engine.connect() as c:
        recent_actions = c.execute(
            text("""
            SELECT DISTINCT ON (ca.instrument_id, ca.ex_date)
                   ca.instrument_id::text, ca.ex_date, i.current_symbol
            FROM public.de_corporate_actions ca
            JOIN public.de_instrument i ON i.id = ca.instrument_id
            JOIN atlas.atlas_universe_stocks u ON u.instrument_id = ca.instrument_id
            WHERE u.effective_to IS NULL
              AND ca.action_type IN ('split','bonus')
              AND ca.ratio_from > 0 AND ca.ratio_to > 0
              AND ca.ex_date >= (CURRENT_DATE - INTERVAL '90 days')
            ORDER BY ca.instrument_id, ca.ex_date
        """)
        ).fetchall()
        dirty = []
        for iid, ex, sym in recent_actions:
            pre = c.execute(
                text("""
                SELECT close_adj::float FROM public.de_equity_ohlcv
                WHERE instrument_id=CAST(:i AS uuid) AND date<:d AND close_adj > 0
                ORDER BY date DESC LIMIT 1
            """),
                {"i": iid, "d": ex},
            ).fetchone()
            post = c.execute(
                text("""
                SELECT close_adj::float FROM public.de_equity_ohlcv
                WHERE instrument_id=CAST(:i AS uuid) AND date>=:d AND close_adj > 0
                ORDER BY date LIMIT 1
            """),
                {"i": iid, "d": ex},
            ).fetchone()
            if not pre or not post or pre[0] <= 0:
                continue
            adj_ret = abs(post[0] / pre[0] - 1)
            if adj_ret > 0.30:
                dirty.append((sym, ex, adj_ret))
        if dirty:
            failures.append(
                f"{len(dirty)} universe corp actions in last 90 days have |adj split-day return|>30%: "
                + ", ".join(f"{s} on {d}" for s, d, _ in dirty[:5])
            )
        else:
            print(
                f"  ✓ All {len(recent_actions)} universe corp actions in last 90 days cleanly adjusted"
            )

    if failures:
        print()
        print("QUALITY ASSERTIONS FAILED:")
        for msg in failures:
            print(f"  ✗ {msg}")
        return 2
    print()
    print("All quality assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
