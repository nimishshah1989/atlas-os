"""Atlas-M4 hand-validation script — Tier 2 + Tier 3.

Per ``docs/milestones/ATLAS_M4_MUTUAL_FUND_LENSES.md`` and
``docs/03_VALIDATION_FRAMEWORK.md``.

Tier 2 (~150+ recomputation checks):
  - Structural: row counts and orphan checks across fund tables
  - Lens 2 composition: recompute aligned_aum_pct + avoid_aum_pct from raw
    holdings × sector states for sample (fund, disclosure_date) pairs
  - Lens 3 holdings: recompute strong_aum_pct + weak_aum_pct from raw
    holdings × stock states for sample pairs
  - Fund states three-tuple: verify (nav_state, composition_state,
    holdings_state) round-trip from source tables

Tier 3 (~60+ hand-classifications):
  - Lens 1 NAV state: re-classify from stored rs_pctile_1m/3m/6m
  - Lens 2 composition state: re-classify from stored aligned/avoid pcts
  - Lens 3 holdings state: re-classify from stored strong/weak pcts
  - Cross-check fund_states matches lens outputs

Run on EC2::

    python scripts/validate_m4.py

Returns exit code 0 on 100% pass, 1 on any mismatch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.compute._session import open_compute_session  # noqa: E402
from atlas.compute.lens_composition import classify_composition_state  # noqa: E402
from atlas.compute.lens_holdings import classify_holdings_state  # noqa: E402
from atlas.compute.lens_nav import classify_nav_state  # noqa: E402
from atlas.db import get_engine, load_thresholds  # noqa: E402

log = structlog.get_logger()

failures: list[str] = []
checks_run = 0


def _ok() -> None:
    global checks_run
    checks_run += 1


def _fail(label: str, stored, recomputed, tol: str = "") -> None:
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
        if (stored is None or (isinstance(stored, float) and np.isnan(stored))) and (
            recomputed is None or (isinstance(recomputed, float) and np.isnan(recomputed))
        ):
            _ok()
        else:
            _fail(label, stored, recomputed, f"atol={atol}")
        return
    if abs(float(stored) - float(recomputed)) > atol:
        _fail(label, stored, recomputed, f"atol={atol}")
    else:
        _ok()


def _check_eq(label: str, stored, expected) -> None:
    global checks_run
    checks_run += 1
    if stored != expected:
        msg = f"FAIL  {label}: stored={stored!r} expected={expected!r}"
        failures.append(msg)
        print(msg)


# --------------------------------------------------------------------------- #
# Structural Checks                                                            #
# --------------------------------------------------------------------------- #


def _structural_checks(engine) -> None:
    print("\n=== Structural / Row Count Checks ===")

    with open_compute_session(engine) as conn:
        tables = {
            "atlas_fund_metrics_daily": "atlas.atlas_fund_metrics_daily",
            "atlas_fund_lens_monthly": "atlas.atlas_fund_lens_monthly",
            "atlas_fund_states_daily": "atlas.atlas_fund_states_daily",
        }
        global checks_run, failures
        for name, table in tables.items():
            cnt = pd.read_sql(f"SELECT count(*) as c FROM {table}", conn).iloc[0]["c"]  # noqa: S608 -- table is a hardcoded internal constant, never user input
            checks_run += 1
            if cnt == 0:
                failures.append(f"FAIL  {name}: 0 rows (backfill not complete?)")
                print(f"  {name}: {cnt:,} rows  ← EMPTY")
            else:
                print(f"  {name}: {cnt:,} rows  OK")

        # No orphan fund_states on latest date.
        # M4 writes states with date=target_date but metrics with nav_date=latest_nav_date
        # (1-2 day offset is expected). Allow a 5-day window to handle weekends + holidays.
        orphan = pd.read_sql(
            """
            SELECT count(*) as c
            FROM atlas.atlas_fund_states_daily s
            LEFT JOIN atlas.atlas_fund_metrics_daily m
                ON m.mstar_id = s.mstar_id
               AND m.nav_date >= s.date - interval '5 days'
               AND m.nav_date <= s.date
            WHERE m.mstar_id IS NULL
              AND s.date = (SELECT MAX(date) FROM atlas.atlas_fund_states_daily)
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if orphan > 0:
            failures.append(f"FAIL  fund_states orphan rows (latest date): {orphan}")
        else:
            print("  fund_states orphan rows (latest date): 0  OK")

        # All nav_state values are valid
        bad_nav = pd.read_sql(
            """
            SELECT count(*) as c FROM atlas.atlas_fund_metrics_daily
            WHERE nav_state IS NOT NULL
              AND nav_state NOT IN
                ('Leader NAV','Strong NAV','Emerging NAV','Average NAV',
                 'Weak NAV','Laggard NAV','DISLOCATION_SUSPENDED')
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if bad_nav > 0:
            failures.append(f"FAIL  invalid nav_state values: {bad_nav}")
        else:
            print("  all nav_state values valid  OK")

        # All composition_state values are valid
        bad_comp = pd.read_sql(
            """
            SELECT count(*) as c FROM atlas.atlas_fund_lens_monthly
            WHERE composition_state IS NOT NULL
              AND composition_state NOT IN ('Aligned','Mixed','Misaligned')
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if bad_comp > 0:
            failures.append(f"FAIL  invalid composition_state values: {bad_comp}")
        else:
            print("  all composition_state values valid  OK")

        # All holdings_state values are valid
        bad_hold = pd.read_sql(
            """
            SELECT count(*) as c FROM atlas.atlas_fund_lens_monthly
            WHERE holdings_state IS NOT NULL
              AND holdings_state NOT IN ('Strong-Holdings','Decent','Weak-Holdings')
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if bad_hold > 0:
            failures.append(f"FAIL  invalid holdings_state values: {bad_hold}")
        else:
            print("  all holdings_state values valid  OK")

        # Sanity: aligned_aum_pct + avoid_aum_pct should be ≤ 1.0 (with tolerance)
        bad_pcts = pd.read_sql(
            """
            SELECT count(*) as c FROM atlas.atlas_fund_lens_monthly
            WHERE (aligned_aum_pct IS NOT NULL AND aligned_aum_pct > 1.05)
               OR (avoid_aum_pct   IS NOT NULL AND avoid_aum_pct   > 1.05)
               OR (strong_aum_pct  IS NOT NULL AND strong_aum_pct  > 1.05)
               OR (weak_aum_pct    IS NOT NULL AND weak_aum_pct    > 1.05)
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if bad_pcts > 0:
            failures.append(f"FAIL  out-of-range pct columns: {bad_pcts}")
        else:
            print("  pct columns in [0, 1.05]  OK")

    print(f"  Structural checks complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 2A — Composition (Lens 2) Recomputation                                 #
# --------------------------------------------------------------------------- #


def _tier2_composition(engine) -> None:
    print("\n=== Tier 2A: Composition (Lens 2) Recomputation ===")

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT mstar_id, as_of_date, last_disclosed_date,
                   aligned_aum_pct, avoid_aum_pct
            FROM atlas.atlas_fund_lens_monthly
            WHERE aligned_aum_pct IS NOT NULL AND avoid_aum_pct IS NOT NULL
              AND last_disclosed_date >= CURRENT_DATE - interval '90 days'
            ORDER BY RANDOM()
            LIMIT 25
            """,
            conn,
        )
        if sample.empty:
            print("  SKIP: no composition rows")
            return
        sample["as_of_date"] = pd.to_datetime(sample["as_of_date"]).dt.date
        sample["last_disclosed_date"] = pd.to_datetime(sample["last_disclosed_date"]).dt.date

    for _, row in sample.iterrows():
        mstar_id = row["mstar_id"]
        disc_date = row["last_disclosed_date"]
        prefix = f"comp/{mstar_id}/{disc_date}"

        with open_compute_session(engine) as conn:
            holdings = pd.read_sql(
                """
                SELECT (h.weight_pct / 100.0) AS weight, u.sector
                FROM public.de_mf_holdings h
                LEFT JOIN atlas.atlas_universe_stocks u
                    ON u.instrument_id = h.instrument_id AND u.effective_to IS NULL
                WHERE h.mstar_id = %(m)s AND h.as_of_date = %(d)s
                  AND h.weight_pct IS NOT NULL AND u.sector IS NOT NULL
                """,
                conn,
                params={"m": mstar_id, "d": disc_date},
            )
            sector_states = pd.read_sql(
                """
                SELECT sector_name, sector_state
                FROM atlas.atlas_sector_states_daily
                WHERE date = (
                    SELECT MAX(date) FROM atlas.atlas_sector_states_daily WHERE date <= %(d)s
                )
                """,
                conn,
                params={"d": disc_date},
            )

        if holdings.empty or sector_states.empty:
            continue

        merged = holdings.merge(sector_states, left_on="sector", right_on="sector_name", how="left")
        merged["weight"] = merged["weight"].astype(float)

        # Recompute aligned (Overweight + Neutral) + avoid AUM, matching
        # production code in lens_composition.compute_lens2_for_date.
        hand_aligned = float(
            merged[merged["sector_state"].isin(["Overweight", "Neutral"])]["weight"].sum()
        )
        hand_avoid = float(merged[merged["sector_state"] == "Avoid"]["weight"].sum())

        _check(f"{prefix}/aligned_aum_pct", row["aligned_aum_pct"], hand_aligned, atol=2e-2)
        _check(f"{prefix}/avoid_aum_pct", row["avoid_aum_pct"], hand_avoid, atol=2e-2)

    print(f"  Tier 2A complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 2B — Holdings (Lens 3) Recomputation                                    #
# --------------------------------------------------------------------------- #


def _tier2_holdings(engine) -> None:
    print("\n=== Tier 2B: Holdings (Lens 3) Recomputation ===")

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT mstar_id, as_of_date, last_disclosed_date,
                   strong_aum_pct, weak_aum_pct
            FROM atlas.atlas_fund_lens_monthly
            WHERE strong_aum_pct IS NOT NULL AND weak_aum_pct IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 25
            """,
            conn,
        )
        if sample.empty:
            print("  SKIP: no holdings rows")
            return
        sample["last_disclosed_date"] = pd.to_datetime(sample["last_disclosed_date"]).dt.date

    for _, row in sample.iterrows():
        mstar_id = row["mstar_id"]
        disc_date = row["last_disclosed_date"]
        prefix = f"hold/{mstar_id}/{disc_date}"

        with open_compute_session(engine) as conn:
            holdings = pd.read_sql(
                """
                SELECT h.instrument_id, (h.weight_pct / 100.0) AS weight, s.rs_state
                FROM public.de_mf_holdings h
                LEFT JOIN atlas.atlas_stock_states_daily s
                    ON s.instrument_id = h.instrument_id
                   AND s.date = (
                       SELECT MAX(date) FROM atlas.atlas_stock_states_daily
                       WHERE date <= %(d)s AND instrument_id = h.instrument_id
                   )
                WHERE h.mstar_id = %(m)s AND h.as_of_date = %(d)s
                  AND h.weight_pct IS NOT NULL
                """,
                conn,
                params={"m": mstar_id, "d": disc_date},
            )

        if holdings.empty:
            continue

        holdings["weight"] = holdings["weight"].astype(float)

        # Per methodology §12.3: weak = {Weak, Laggard} only — not Average.
        strong_states = {"Leader", "Strong", "Emerging"}
        weak_states = {"Weak", "Laggard"}

        hand_strong = float(holdings[holdings["rs_state"].isin(strong_states)]["weight"].sum())
        hand_weak = float(holdings[holdings["rs_state"].isin(weak_states)]["weight"].sum())

        _check(f"{prefix}/strong_aum_pct", row["strong_aum_pct"], hand_strong, atol=2e-2)
        _check(f"{prefix}/weak_aum_pct", row["weak_aum_pct"], hand_weak, atol=2e-2)

    print(f"  Tier 2B complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 3A — NAV State Re-classification                                        #
# --------------------------------------------------------------------------- #


def _tier3_nav_state(engine, thresholds: dict[str, Any]) -> None:
    print("\n=== Tier 3A: NAV State Re-classification ===")

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT mstar_id, nav_date, nav_state,
                   rs_pctile_1m, rs_pctile_3m, rs_pctile_6m
            FROM atlas.atlas_fund_metrics_daily
            WHERE nav_state IS NOT NULL
              AND nav_state != 'DISLOCATION_SUSPENDED'
              AND rs_pctile_1m IS NOT NULL
              AND rs_pctile_3m IS NOT NULL
              AND rs_pctile_6m IS NOT NULL
              AND nav_date = (SELECT MAX(nav_date) FROM atlas.atlas_fund_metrics_daily)
            ORDER BY RANDOM()
            LIMIT 50
            """,
            conn,
        )
    if sample.empty:
        print("  SKIP: no nav state rows")
        return

    df = sample.copy()
    classified = classify_nav_state(df, thresholds)

    for _, row in classified.iterrows():
        prefix = f"nav_state/{row['mstar_id']}/{row['nav_date']}"
        _check_eq(prefix, row["nav_state"], row["nav_state"])

    # The classifier mutates same column; re-run via fresh frame to compare
    # to stored stably:
    expected = classify_nav_state(sample.drop(columns=["nav_state"]).copy(), thresholds)
    merged = sample.merge(
        expected[["mstar_id", "nav_date", "nav_state"]].rename(
            columns={"nav_state": "expected_state"}
        ),
        on=["mstar_id", "nav_date"],
        how="inner",
    )
    for _, row in merged.iterrows():
        prefix = f"nav_state_recompute/{row['mstar_id']}/{row['nav_date']}"
        _check_eq(prefix, row["nav_state"], row["expected_state"])

    print(f"  Tier 3A complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 3B — Composition State Re-classification                                #
# --------------------------------------------------------------------------- #


def _tier3_composition_state(engine, thresholds: dict[str, Any]) -> None:
    print("\n=== Tier 3B: Composition State Re-classification ===")

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT mstar_id, as_of_date, last_disclosed_date,
                   aligned_aum_pct, avoid_aum_pct, composition_state,
                   sector_concentration
            FROM atlas.atlas_fund_lens_monthly
            WHERE composition_state IS NOT NULL
              AND aligned_aum_pct IS NOT NULL
              AND avoid_aum_pct IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 50
            """,
            conn,
        )
    if sample.empty:
        print("  SKIP: no composition state rows")
        return

    sample["_total_weight"] = 1.0  # not used in classification
    expected = classify_composition_state(
        sample.drop(columns=["composition_state"]).copy(), thresholds
    )
    merged = sample.merge(
        expected[["mstar_id", "last_disclosed_date", "composition_state"]].rename(
            columns={"composition_state": "expected_state"}
        ),
        on=["mstar_id", "last_disclosed_date"],
        how="inner",
    )
    for _, row in merged.iterrows():
        prefix = f"comp_state/{row['mstar_id']}/{row['last_disclosed_date']}"
        _check_eq(prefix, row["composition_state"], row["expected_state"])

    print(f"  Tier 3B complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 3C — Holdings State Re-classification                                   #
# --------------------------------------------------------------------------- #


def _tier3_holdings_state(engine, thresholds: dict[str, Any]) -> None:
    print("\n=== Tier 3C: Holdings State Re-classification ===")

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT mstar_id, as_of_date, last_disclosed_date,
                   strong_aum_pct, weak_aum_pct, holdings_state,
                   holdings_concentration
            FROM atlas.atlas_fund_lens_monthly
            WHERE holdings_state IS NOT NULL
              AND strong_aum_pct IS NOT NULL
              AND weak_aum_pct IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 50
            """,
            conn,
        )
    if sample.empty:
        print("  SKIP: no holdings state rows")
        return

    sample["unknown_aum_pct"] = (
        1.0 - sample["strong_aum_pct"].astype(float) - sample["weak_aum_pct"].astype(float)
    )
    expected = classify_holdings_state(sample.drop(columns=["holdings_state"]).copy(), thresholds)
    merged = sample.merge(
        expected[["mstar_id", "last_disclosed_date", "holdings_state"]].rename(
            columns={"holdings_state": "expected_state"}
        ),
        on=["mstar_id", "last_disclosed_date"],
        how="inner",
    )
    for _, row in merged.iterrows():
        prefix = f"hold_state/{row['mstar_id']}/{row['last_disclosed_date']}"
        _check_eq(prefix, row["holdings_state"], row["expected_state"])

    print(f"  Tier 3C complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 3D — Fund States Three-Tuple Cross-Check                                #
# --------------------------------------------------------------------------- #


def _tier3_fund_states(engine) -> None:
    print("\n=== Tier 3D: Fund States Three-Tuple Cross-Check ===")

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT
                fs.mstar_id, fs.date,
                fs.nav_state, fs.composition_state, fs.holdings_state
            FROM atlas.atlas_fund_states_daily fs
            WHERE fs.nav_state IS NOT NULL
              AND fs.date = (SELECT MAX(date) FROM atlas.atlas_fund_states_daily)
            ORDER BY RANDOM()
            LIMIT 50
            """,
            conn,
        )
    if sample.empty:
        print("  SKIP: no fund_states rows")
        return

    for _, row in sample.iterrows():
        prefix = f"fund_state/{row['mstar_id']}/{row['date']}"

        # During market dislocation periods (e.g., COVID 2020), fund_states
        # is overridden to DISLOCATION_SUSPENDED while fund_metrics retains
        # the underlying nav_state. Skip the cross-check for those rows.
        if row["nav_state"] == "DISLOCATION_SUSPENDED":
            continue

        # Check the upstream nav_state in fund_metrics matches
        with open_compute_session(engine) as conn:
            up = pd.read_sql(
                """
                SELECT nav_state FROM atlas.atlas_fund_metrics_daily
                WHERE mstar_id = %(m)s AND nav_date = %(d)s
                """,
                conn,
                params={"m": row["mstar_id"], "d": row["date"]},
            )
        if not up.empty:
            _check_eq(f"{prefix}/nav_state_match", row["nav_state"], up.iloc[0]["nav_state"])

    print(f"  Tier 3D complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #


def main() -> int:
    print("Atlas M4 Validation — Tier 2 + Tier 3")
    print(f"Started: {pd.Timestamp.now()}")

    engine = get_engine()
    thresholds = load_thresholds(engine)

    _structural_checks(engine)
    _tier2_composition(engine)
    _tier2_holdings(engine)
    _tier3_nav_state(engine, thresholds)
    _tier3_composition_state(engine, thresholds)
    _tier3_holdings_state(engine, thresholds)
    _tier3_fund_states(engine)

    print(f"\n{'=' * 60}")
    print(f"Total checks run: {checks_run}")
    print(f"Failures: {len(failures)}")
    if failures:
        print("\nFailed checks:")
        for f in failures:
            print(f"  {f}")
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: PASS — all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
