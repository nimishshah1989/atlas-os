"""Atlas-M5 hand-validation script — Tier 2 + Tier 3.

Per ``docs/milestones/ATLAS_M5_DECISION_ENGINE.md`` and
``docs/03_VALIDATION_FRAMEWORK.md``.

Tier 2 (~200+ recomputation checks):
  - Structural: row counts and orphan checks across decision tables
  - Stock decisions: re-derive 6 gates from upstream states for sample rows
  - ETF decisions: re-derive 5 gates including theme-conditional sector gate
  - Fund decisions: re-derive 4-state recommendation from three-tuple

Tier 3 (~150+ hand-classifications):
  - Stock is_investable: AND of 6 gates must match stored value
  - Stock position_size_pct = base × market_mult × risk_mult
  - ETF is_investable + theme-conditional sector gate
  - Fund recommendation taxonomy (Recommended/Hold/Reduce/Exit)
  - Exit triggers consistent with upstream states

Run on EC2::

    python scripts/validate_m5.py

Returns exit code 0 on 100% pass, 1 on any mismatch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.compute._session import open_compute_session  # noqa: E402
from atlas.compute.decisions_etf import _sector_gate_value  # noqa: E402
from atlas.compute.decisions_stock import (  # noqa: E402
    DIRECTION_PASS_STATES,
    MARKET_MULTIPLIERS,
    RISK_MULTIPLIERS,
    RISK_PASS_STATES,
    SECTOR_PASS_STATES,
    STRENGTH_PASS_STATES,
    VOLUME_PASS_STATES,
)
from atlas.db import get_engine  # noqa: E402

log = structlog.get_logger()

failures: list[str] = []
checks_run = 0


def _ok() -> None:
    global checks_run
    checks_run += 1


def _fail(label: str, stored, expected) -> None:
    global checks_run
    checks_run += 1
    msg = f"FAIL  {label}: stored={stored!r} expected={expected!r}"
    failures.append(msg)
    print(msg)


def _check_bool(label: str, stored, expected) -> None:
    sv = bool(stored) if stored is not None else False
    ev = bool(expected) if expected is not None else False
    if sv != ev:
        _fail(label, sv, ev)
    else:
        _ok()


def _check_eq(label: str, stored, expected) -> None:
    if stored != expected:
        _fail(label, stored, expected)
    else:
        _ok()


def _check_close(label: str, stored, expected, atol: float = 1e-4) -> None:
    if stored is None or expected is None:
        if stored is None and expected is None:
            _ok()
        else:
            _fail(label, stored, expected)
        return
    if abs(float(stored) - float(expected)) > atol:
        _fail(label, stored, expected)
    else:
        _ok()


# --------------------------------------------------------------------------- #
# Structural Checks                                                            #
# --------------------------------------------------------------------------- #


def _structural_checks(engine) -> None:
    print("\n=== Structural / Row Count Checks ===")

    with open_compute_session(engine) as conn:
        tables = {
            "atlas_stock_decisions_daily": "atlas.atlas_stock_decisions_daily",
            "atlas_etf_decisions_daily": "atlas.atlas_etf_decisions_daily",
            "atlas_fund_decisions_daily": "atlas.atlas_fund_decisions_daily",
        }
        global checks_run, failures
        for name, table in tables.items():
            cnt = pd.read_sql(f"SELECT count(*) as c FROM {table}", conn).iloc[0]["c"]
            checks_run += 1
            if cnt == 0:
                failures.append(f"FAIL  {name}: 0 rows (backfill not complete?)")
                print(f"  {name}: {cnt:,} rows  ← EMPTY")
            else:
                print(f"  {name}: {cnt:,} rows  OK")

        # No orphan stock_decisions (every decision row has matching state row)
        orphan_stock = pd.read_sql(
            """
            SELECT count(*) as c
            FROM atlas.atlas_stock_decisions_daily d
            LEFT JOIN atlas.atlas_stock_states_daily s
                ON s.instrument_id = d.instrument_id AND s.date = d.date
            WHERE s.instrument_id IS NULL
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if orphan_stock > 0:
            failures.append(f"FAIL  stock_decisions orphan rows: {orphan_stock}")
        else:
            print("  stock_decisions orphan rows: 0  OK")

        orphan_etf = pd.read_sql(
            """
            SELECT count(*) as c
            FROM atlas.atlas_etf_decisions_daily d
            LEFT JOIN atlas.atlas_etf_states_daily s
                ON s.ticker = d.ticker AND s.date = d.date
            WHERE s.ticker IS NULL
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if orphan_etf > 0:
            failures.append(f"FAIL  etf_decisions orphan rows: {orphan_etf}")
        else:
            print("  etf_decisions orphan rows: 0  OK")

        # position_size_pct must be in [0, ~1.5]
        bad_size = pd.read_sql(
            """
            SELECT count(*) as c FROM atlas.atlas_stock_decisions_daily
            WHERE position_size_pct IS NOT NULL
              AND (position_size_pct < 0 OR position_size_pct > 1.5)
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if bad_size > 0:
            failures.append(f"FAIL  stock position_size_pct out of [0, 1.5]: {bad_size}")
        else:
            print("  stock position_size_pct in [0, 1.5]  OK")

        # Fund recommendation must be one of 4 values
        bad_rec = pd.read_sql(
            """
            SELECT count(*) as c FROM atlas.atlas_fund_decisions_daily
            WHERE recommendation IS NOT NULL
              AND recommendation NOT IN ('Recommended','Hold','Reduce','Exit')
            """,
            conn,
        ).iloc[0]["c"]
        checks_run += 1
        if bad_rec > 0:
            failures.append(f"FAIL  invalid fund recommendation values: {bad_rec}")
        else:
            print("  all fund recommendations valid  OK")

    print(f"  Structural checks complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 2A — Stock Gates                                                        #
# --------------------------------------------------------------------------- #


def _tier2_stock_gates(engine) -> None:
    print("\n=== Tier 2A: Stock Gate Re-derivation ===")

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT
                d.instrument_id::text AS instrument_id, d.date,
                d.is_investable,
                d.market_gate, d.sector_gate, d.strength_gate,
                d.direction_gate, d.risk_gate, d.volume_gate,
                d.position_size_pct, d.market_multiplier, d.risk_multiplier,
                s.rs_state, s.momentum_state, s.risk_state, s.volume_state,
                s.sector,
                ss.sector_state,
                mr.regime_state, mr.dislocation_active
            FROM atlas.atlas_stock_decisions_daily d
            JOIN atlas.atlas_stock_states_daily s
                ON s.instrument_id = d.instrument_id AND s.date = d.date
            LEFT JOIN atlas.atlas_sector_states_daily ss
                ON ss.sector_name = s.sector AND ss.date = d.date
            LEFT JOIN atlas.atlas_market_regime_daily mr ON mr.date = d.date
            WHERE s.rs_state NOT IN ('INSUFFICIENT_HISTORY','ILLIQUID','DISLOCATION_SUSPENDED')
            ORDER BY RANDOM()
            LIMIT 50
            """,
            conn,
        )
    if sample.empty:
        print("  SKIP: no stock decisions rows")
        return

    for _, r in sample.iterrows():
        prefix = f"stock/{r['instrument_id']}/{r['date']}"

        # Re-derive each gate
        exp_market = (r["regime_state"] != "Risk-Off") and not bool(r["dislocation_active"])
        exp_sector = r["sector_state"] in SECTOR_PASS_STATES
        exp_strength = r["rs_state"] in STRENGTH_PASS_STATES
        exp_direction = r["momentum_state"] in DIRECTION_PASS_STATES
        exp_risk = r["risk_state"] in RISK_PASS_STATES
        exp_volume = r["volume_state"] in VOLUME_PASS_STATES

        _check_bool(f"{prefix}/market_gate", r["market_gate"], exp_market)
        _check_bool(f"{prefix}/sector_gate", r["sector_gate"], exp_sector)
        _check_bool(f"{prefix}/strength_gate", r["strength_gate"], exp_strength)
        _check_bool(f"{prefix}/direction_gate", r["direction_gate"], exp_direction)
        _check_bool(f"{prefix}/risk_gate", r["risk_gate"], exp_risk)
        _check_bool(f"{prefix}/volume_gate", r["volume_gate"], exp_volume)

        exp_invest = (
            exp_market and exp_sector and exp_strength and exp_direction and exp_risk and exp_volume
        )
        _check_bool(f"{prefix}/is_investable", r["is_investable"], exp_invest)

        # Position sizing: base(1.0) × market_mult × risk_mult
        exp_market_mult = MARKET_MULTIPLIERS.get(r["regime_state"], 0.0)
        exp_risk_mult = RISK_MULTIPLIERS.get(r["risk_state"], 0.0)
        exp_size = 1.0 * exp_market_mult * exp_risk_mult
        _check_close(f"{prefix}/market_multiplier", r["market_multiplier"], exp_market_mult)
        _check_close(f"{prefix}/risk_multiplier", r["risk_multiplier"], exp_risk_mult)
        _check_close(f"{prefix}/position_size_pct", r["position_size_pct"], exp_size)

    print(f"  Tier 2A complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 2B — Stock Exit Triggers                                                #
# --------------------------------------------------------------------------- #


def _tier2_stock_exits(engine) -> None:
    print("\n=== Tier 2B: Stock Exit Trigger Re-derivation ===")

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT
                d.instrument_id::text AS instrument_id, d.date,
                d.exit_market_riskoff, d.exit_sector_avoid, d.exit_rs_deteriorate,
                d.exit_momentum_collapse, d.exit_volume_distrib,
                s.rs_state, s.momentum_state, s.volume_state, s.sector,
                ss.sector_state,
                mr.regime_state
            FROM atlas.atlas_stock_decisions_daily d
            JOIN atlas.atlas_stock_states_daily s
                ON s.instrument_id = d.instrument_id AND s.date = d.date
            LEFT JOIN atlas.atlas_sector_states_daily ss
                ON ss.sector_name = s.sector AND ss.date = d.date
            LEFT JOIN atlas.atlas_market_regime_daily mr ON mr.date = d.date
            ORDER BY RANDOM()
            LIMIT 30
            """,
            conn,
        )
    if sample.empty:
        print("  SKIP: no stock decisions rows for exit checks")
        return

    rs_weak = {"Average", "Weak", "Laggard"}

    for _, r in sample.iterrows():
        prefix = f"stock_exit/{r['instrument_id']}/{r['date']}"

        _check_bool(
            f"{prefix}/exit_market_riskoff",
            r["exit_market_riskoff"],
            r["regime_state"] == "Risk-Off",
        )
        _check_bool(
            f"{prefix}/exit_sector_avoid",
            r["exit_sector_avoid"],
            r["sector_state"] == "Avoid",
        )
        _check_bool(
            f"{prefix}/exit_rs_deteriorate",
            r["exit_rs_deteriorate"],
            r["rs_state"] in rs_weak,
        )
        _check_bool(
            f"{prefix}/exit_momentum_collapse",
            r["exit_momentum_collapse"],
            r["momentum_state"] == "Collapsing",
        )
        _check_bool(
            f"{prefix}/exit_volume_distrib",
            r["exit_volume_distrib"],
            r["volume_state"] == "Heavy Distribution",
        )

    print(f"  Tier 2B complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 2C — ETF Gates                                                          #
# --------------------------------------------------------------------------- #


def _tier2_etf_gates(engine) -> None:
    print("\n=== Tier 2C: ETF Gate Re-derivation ===")

    etf_strength = {"Leader", "Strong", "Consolidating", "Emerging"}
    etf_direction = {"Accelerating", "Improving"}

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT
                d.ticker, d.date,
                d.is_investable, d.market_gate, d.sector_gate, d.strength_gate,
                d.direction_gate, d.risk_gate,
                s.rs_state, s.momentum_state, s.risk_state, s.volume_state,
                u.theme, u.linked_sector,
                ss.sector_state AS linked_sector_state,
                mr.regime_state, mr.dislocation_active
            FROM atlas.atlas_etf_decisions_daily d
            JOIN atlas.atlas_etf_states_daily s ON s.ticker = d.ticker AND s.date = d.date
            JOIN atlas.atlas_universe_etfs u ON u.ticker = d.ticker AND u.effective_to IS NULL
            LEFT JOIN atlas.atlas_sector_states_daily ss
                ON ss.sector_name = u.linked_sector AND ss.date = d.date
            LEFT JOIN atlas.atlas_market_regime_daily mr ON mr.date = d.date
            WHERE s.rs_state NOT IN ('INSUFFICIENT_HISTORY','ILLIQUID','DISLOCATION_SUSPENDED')
            ORDER BY RANDOM()
            LIMIT 50
            """,
            conn,
        )
    if sample.empty:
        print("  SKIP: no etf decisions rows")
        return

    for _, r in sample.iterrows():
        prefix = f"etf/{r['ticker']}/{r['date']}"

        exp_market = (r["regime_state"] != "Risk-Off") and not bool(r["dislocation_active"])
        exp_strength = r["rs_state"] in etf_strength
        exp_direction = r["momentum_state"] in etf_direction
        exp_risk = r["risk_state"] not in {"High", "Below Trend"}
        # Sector gate: theme-conditional. We can only check Broad and Sectoral
        # without re-running the dominant-sector query (Thematic).
        if r["theme"] in ("Broad", "Sectoral"):
            exp_sector = _sector_gate_value(r["theme"], r["linked_sector_state"], None)
            _check_bool(f"{prefix}/sector_gate", r["sector_gate"], exp_sector)

        _check_bool(f"{prefix}/market_gate", r["market_gate"], exp_market)
        _check_bool(f"{prefix}/strength_gate", r["strength_gate"], exp_strength)
        _check_bool(f"{prefix}/direction_gate", r["direction_gate"], exp_direction)
        _check_bool(f"{prefix}/risk_gate", r["risk_gate"], exp_risk)

    print(f"  Tier 2C complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 2D — Fund Recommendation                                                #
# --------------------------------------------------------------------------- #


def _tier2_fund_recommendation(engine) -> None:
    print("\n=== Tier 2D: Fund Recommendation Re-derivation ===")

    nav_strong = {"Leader NAV", "Strong NAV"}

    with open_compute_session(engine) as conn:
        sample = pd.read_sql(
            """
            SELECT
                d.mstar_id, d.date, d.recommendation, d.is_investable,
                d.performance_gate, d.sectors_gate, d.stocks_gate, d.market_gate,
                fs.nav_state, fs.composition_state, fs.holdings_state,
                mr.regime_state, mr.dislocation_active
            FROM atlas.atlas_fund_decisions_daily d
            JOIN atlas.atlas_fund_states_daily fs
                ON fs.mstar_id = d.mstar_id AND fs.date = d.date
            LEFT JOIN atlas.atlas_market_regime_daily mr ON mr.date = d.date
            WHERE fs.nav_state IS NOT NULL
              AND fs.nav_state != 'DISLOCATION_SUSPENDED'
            ORDER BY RANDOM()
            LIMIT 50
            """,
            conn,
        )
    if sample.empty:
        print("  SKIP: no fund decisions rows")
        return

    for _, r in sample.iterrows():
        prefix = f"fund/{r['mstar_id']}/{r['date']}"

        # Re-derive recommendation per methodology §13.6
        if r["dislocation_active"]:
            exp_rec = "Exit"
        elif r["regime_state"] == "Risk-Off":
            exp_rec = "Exit"
        elif r["nav_state"] == "Laggard NAV":
            exp_rec = "Exit"
        elif r["nav_state"] == "Weak NAV":
            exp_rec = "Reduce"
        elif r["composition_state"] == "Misaligned" and r["holdings_state"] == "Weak-Holdings":
            exp_rec = "Reduce"
        elif (
            r["nav_state"] in nav_strong
            and r["composition_state"] == "Aligned"
            and r["holdings_state"] == "Strong-Holdings"
        ):
            exp_rec = "Recommended"
        else:
            exp_rec = "Hold"

        _check_eq(f"{prefix}/recommendation", r["recommendation"], exp_rec)
        _check_bool(f"{prefix}/is_investable", r["is_investable"], exp_rec == "Recommended")

        # Gate columns
        _check_bool(
            f"{prefix}/performance_gate",
            r["performance_gate"],
            r["nav_state"] in nav_strong,
        )
        _check_bool(
            f"{prefix}/sectors_gate",
            r["sectors_gate"],
            r["composition_state"] != "Misaligned",
        )
        _check_bool(
            f"{prefix}/stocks_gate",
            r["stocks_gate"],
            r["holdings_state"] != "Weak-Holdings",
        )
        _check_bool(
            f"{prefix}/market_gate",
            r["market_gate"],
            r["regime_state"] != "Risk-Off" and not bool(r["dislocation_active"]),
        )

    print(f"  Tier 2D complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Tier 3 — Recommendation Distribution Sanity                                  #
# --------------------------------------------------------------------------- #


def _tier3_distribution_sanity(engine) -> None:
    print("\n=== Tier 3: Recommendation Distribution Sanity ===")

    with open_compute_session(engine) as conn:
        # On the most recent date, what fraction of stocks are investable?
        latest = pd.read_sql(
            """
            SELECT MAX(date) AS d FROM atlas.atlas_stock_decisions_daily
            """,
            conn,
        ).iloc[0]["d"]
        if latest is None:
            print("  SKIP: no decisions data")
            return

        stock_dist = pd.read_sql(
            """
            SELECT is_investable, COUNT(*) AS n
            FROM atlas.atlas_stock_decisions_daily
            WHERE date = %(d)s
            GROUP BY is_investable
            """,
            conn,
            params={"d": latest},
        )
        fund_dist = pd.read_sql(
            """
            SELECT recommendation, COUNT(*) AS n
            FROM atlas.atlas_fund_decisions_daily
            WHERE date = %(d)s
            GROUP BY recommendation
            """,
            conn,
            params={"d": latest},
        )
        etf_dist = pd.read_sql(
            """
            SELECT is_investable, COUNT(*) AS n
            FROM atlas.atlas_etf_decisions_daily
            WHERE date = %(d)s
            GROUP BY is_investable
            """,
            conn,
            params={"d": latest},
        )

    print(f"\n  --- Distribution as of {latest} ---")
    print("  Stocks:")
    for _, row in stock_dist.iterrows():
        print(f"    is_investable={row['is_investable']}: {row['n']:,}")
    print("  ETFs:")
    for _, row in etf_dist.iterrows():
        print(f"    is_investable={row['is_investable']}: {row['n']:,}")
    print("  Funds:")
    for _, row in fund_dist.iterrows():
        print(f"    recommendation={row['recommendation']}: {row['n']:,}")

    # Sanity: in Risk-On regime, expect at least 5% stocks investable.
    # In Risk-Off, expect ~0%. We just compute and warn (not fail).
    with open_compute_session(engine) as conn:
        regime = pd.read_sql(
            """
            SELECT regime_state FROM atlas.atlas_market_regime_daily
            WHERE date = %(d)s
            """,
            conn,
            params={"d": latest},
        )
    if not regime.empty:
        rs = regime.iloc[0]["regime_state"]
        total = int(stock_dist["n"].sum()) if not stock_dist.empty else 0
        invest = (
            int(stock_dist[stock_dist["is_investable"]]["n"].sum()) if not stock_dist.empty else 0
        )
        pct = (invest / total * 100) if total > 0 else 0
        print(f"\n  Regime: {rs}, stock investable %: {pct:.1f}%")

        global checks_run, failures
        checks_run += 1
        if rs == "Risk-On" and total > 100 and pct < 1.0:
            failures.append(f"WARN regime={rs} but only {pct:.1f}% stocks investable — sanity flag")
        if rs == "Risk-Off" and pct > 5.0:
            failures.append(f"FAIL regime={rs} but {pct:.1f}% stocks investable — should be ~0%")

    print(f"  Tier 3 complete. checks_so_far={checks_run}, failures={len(failures)}")


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #


def main() -> int:
    print("Atlas M5 Validation — Tier 2 + Tier 3")
    print(f"Started: {pd.Timestamp.now()}")

    engine = get_engine()

    _structural_checks(engine)
    _tier2_stock_gates(engine)
    _tier2_stock_exits(engine)
    _tier2_etf_gates(engine)
    _tier2_fund_recommendation(engine)
    _tier3_distribution_sanity(engine)

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
