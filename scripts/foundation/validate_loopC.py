#!/usr/bin/env python3
"""INDEPENDENT Loop-C gate — the falsifiable definition of done for the stock atom.

Hand-written (NOT emitted by the build loop). Asserts on REAL produced output in
atlas.atlas_lens_scores_daily + the raw feeds — never synthetic fixtures. The
build must make the real journal satisfy C1–C8; this file must NOT be weakened to
pass (that would defeat its purpose, exactly the class of bug — green tests over a
broken feed — that RULE #0 exists to stop).

    python validate_loopC.py --mode full       # C1..C8 (the goalpost)
    python validate_loopC.py --mode progress    # C1,C2,C5 — cheap, run between rebuild chunks
    python validate_loopC.py --check C6          # one assertion group

Exit 0 iff every selected assertion passes.

The eight assertions (see scripts/loops/loopC_atom_complete.md):
  C1 time-variance, all six lenses (policy structural-exempt)
  C2 no snapshot stamping (fundamental/valuation/flow byte-identical-every-date < 5%)
  C3 PIT correctness fundamental/valuation — no lookahead, reconciled to raw feed
  C4 PIT correctness flow/catalyst — adapter never returns future-dated inputs
  C5 depth — every NIFTY-50 session in range scored (count DERIVED at runtime), ≥80% deep
  C6 composite consumes DB lens weights (blocker 0a proven fixed)
  C7 forward returns are forward + walk-forward OOS IC ≥ floor + persisted (blocker 0b)
  C8 graceful degradation is real (coverage_factor lower early; absent source -> None)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import pandas as pd

import _db

L = "atlas.atlas_lens_scores_daily"
TD = "foundation_staging.technical_daily"
FQ = "foundation_staging.financials_quarterly"
OHLCV = "foundation_staging.ohlcv_stock"
IDX = "foundation_staging.index_prices"
IM = "foundation_staging.instrument_master"
START = date(2019, 1, 1)

# Non-policy lenses that must become genuinely point-in-time. C1 variance floors
# are per-lens because the feeds differ in grain: technical/valuation/catalyst
# move daily (price/filings), fundamental steps quarterly, flow steps quarterly +
# insider rolling-window. Floors encode the spec's "large majority" while being
# honest about each feed's natural cadence. They are FLOORS — never lower them to
# dodge a real regression.
C1_FLOORS = {"technical": 0.80, "catalyst": 0.80, "valuation": 0.70,
             "fundamental": 0.55, "flow": 0.55}
IC_FLOOR = 0.03


def _scalar(sql, p=None):
    return _db.scalar(sql, p)


def _df(sql, p=None):
    return _db.read_df(sql, p)


def _sessions(start: date, end: date) -> list[date]:
    """NIFTY-50 sessions in [start, end] — the calendar source of truth (D9)."""
    d = _df(f"SELECT DISTINCT date FROM {IDX} WHERE index_code='NIFTY 50' "
            "AND date>=:s AND date<=:e ORDER BY date", {"s": start, "e": end})
    return [x.date() if hasattr(x, "date") else x for x in d["date"].tolist()]


def _max_session() -> date:
    return _scalar(f"SELECT max(date) FROM {IDX} WHERE index_code='NIFTY 50'")


def _session_on_or_before(target: date) -> date:
    return _scalar(f"SELECT max(date) FROM {IDX} WHERE index_code='NIFTY 50' AND date<=:t",
                   {"t": target})


def _lag_q() -> int:
    v = _scalar("SELECT threshold_value FROM atlas.atlas_thresholds "
                "WHERE threshold_key='fundamental_reporting_lag_days' AND is_active")
    return int(v) if v is not None else 60


class Gate:
    def __init__(self):
        self.fails = 0

    def check(self, name, ok, detail=""):
        tag = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        print(f"  [{tag}] {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            self.fails += 1
        return ok


# ───────────────────────────── C1 time-variance ─────────────────────────────
def check_C1(g: Gate):
    print("== C1: within-instrument time-variance, all six lenses ==")
    for lens, floor in C1_FLOORS.items():
        r = _df(f"""
            WITH t AS (
              SELECT instrument_id, count(*) n, count(DISTINCT {lens}) d
              FROM {L} WHERE asset_class='stock' AND {lens} IS NOT NULL
              GROUP BY 1 HAVING count(*) > 5)
            SELECT count(*) pop, sum((d>1)::int) vary FROM t""")
        pop = int(r["pop"].iloc[0] or 0)
        vary = int(r["vary"].iloc[0] or 0)
        frac = vary / pop if pop else 0.0
        g.check(f"{lens} varies ≥{floor:.0%}", frac >= floor,
                f"{vary}/{pop} = {frac:.0%}")
    # policy is structural — assert it is (correctly) static, not a leak masquerading as signal
    pr = _df(f"""WITH t AS (SELECT instrument_id, count(DISTINCT policy) d FROM {L}
                 WHERE asset_class='stock' AND policy IS NOT NULL GROUP BY 1 HAVING count(*)>5)
                 SELECT count(*) pop, sum((d>1)::int) vary FROM t""")
    pol_frac = (int(pr["vary"].iloc[0] or 0) / int(pr["pop"].iloc[0] or 1))
    g.check("policy is structural (static by design)", pol_frac <= 0.05,
            f"{pol_frac:.0%} vary (expected ~0)")


# ───────────────────────────── C2 no stamping ─────────────────────────────
def check_C2(g: Gate):
    print("== C2: no snapshot stamping (byte-identical on every date < 5%) ==")
    for lens in ("fundamental", "valuation", "flow"):
        r = _df(f"""
            WITH t AS (
              SELECT instrument_id, count(*) n, count(DISTINCT {lens}) d
              FROM {L} WHERE asset_class='stock' AND {lens} IS NOT NULL
              GROUP BY 1 HAVING count(*) > 5)
            SELECT count(*) pop, sum((d=1)::int) stamped FROM t""")
        pop = int(r["pop"].iloc[0] or 0)
        stamped = int(r["stamped"].iloc[0] or 0)
        frac = stamped / pop if pop else 1.0
        g.check(f"{lens} stamped < 5%", frac < 0.05, f"{stamped}/{pop} = {frac:.1%}")


# ──────────────────── C3 PIT correctness fundamental/valuation ────────────────────
def _asof_ttm_eps(iid, as_of: date, lag: int) -> float | None:
    """Trailing-4-quarter EPS using ONLY quarters with period_end <= as_of-lag,
    dedup consolidated-else-standalone. Computed independently of the adapter."""
    q = _df(f"""
        WITH dedup AS (
          SELECT DISTINCT ON (period_end) period_end, eps
          FROM {FQ}
          WHERE instrument_id=:i AND period_end <= :cut AND eps IS NOT NULL
          ORDER BY period_end DESC, consolidated DESC)
        SELECT period_end, eps FROM dedup ORDER BY period_end DESC LIMIT 4""",
            {"i": str(iid), "cut": as_of - timedelta(days=lag)})
    if len(q) < 4:
        return None
    return float(q["eps"].sum())


def _asof_close(iid, as_of: date) -> float | None:
    return _scalar(f"SELECT close FROM {OHLCV} WHERE instrument_id=:i AND date<=:d "
                   "AND close>0 ORDER BY date DESC LIMIT 1", {"i": str(iid), "d": as_of})


def _abs_pe_band(pe: float) -> int:
    if pe <= 0:    return 0
    if pe < 8:     return 25
    if pe < 15:    return 18
    if pe < 25:    return 10
    if pe < 40:    return 3
    return 0


def check_C3(g: Gate):
    print("== C3: PIT correctness fundamental/valuation — NO lookahead, reconciled ==")
    lag = _lag_q()
    as_of = _session_on_or_before(date(2022, 3, 15))
    today = _max_session()
    print(f"   as_of session = {as_of}, reporting_lag = {lag}d")
    # Names with a journal valuation row on as_of AND ≥4 trailing quarters then.
    cand = _df(f"""
        SELECT l.instrument_id, l.val_absolute_pe
        FROM {L} l WHERE l.asset_class='stock' AND l.date=:d
          AND l.val_absolute_pe IS NOT NULL
        ORDER BY l.instrument_id LIMIT 400""", {"d": as_of})
    matched = disc = disc_ok = checked = 0
    for _, row in cand.iterrows():
        iid = row["instrument_id"]
        eps_asof = _asof_ttm_eps(iid, as_of, lag)
        close_asof = _asof_close(iid, as_of)
        if not eps_asof or eps_asof <= 0 or not close_asof:
            continue
        pe_asof = float(close_asof) / eps_asof
        band_asof = _abs_pe_band(pe_asof)
        checked += 1
        if abs(float(row["val_absolute_pe"]) - band_asof) <= 0.5:
            matched += 1
        # lookahead discriminator: TODAY's TTM EPS (uses future quarters)
        eps_today = _asof_ttm_eps(iid, today, lag)
        if eps_today and eps_today > 0:
            band_today = _abs_pe_band(float(close_asof) / eps_today)
            if band_today != band_asof:
                disc += 1
                if abs(float(row["val_absolute_pe"]) - band_asof) <= 0.5:
                    disc_ok += 1
        if checked >= 40:
            break
    g.check("≥20 names reconciled to as-of PE", checked >= 20, f"{checked} checked")
    g.check("journal abs-PE matches as-of trailing-4Q EPS (≥85%)",
            checked >= 20 and matched / max(checked, 1) >= 0.85,
            f"{matched}/{checked} reconciled")
    g.check("no-lookahead: discriminating names match as-of not today (≥80%)",
            disc >= 3 and disc_ok / max(disc, 1) >= 0.80,
            f"{disc_ok}/{disc} discriminators match as-of (≥3 needed)")


# ──────────────────── C4 PIT correctness flow/catalyst ────────────────────
def check_C4(g: Gate):
    print("== C4: PIT correctness flow/catalyst — adapter returns no future inputs ==")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    from atlas.db import get_engine
    from atlas.lenses.data.adapters import load_catalyst_data, load_flow_data
    eng = get_engine()
    as_of = _session_on_or_before(date(2021, 6, 30))
    cat = load_catalyst_data(eng, as_of=as_of)
    ok_cat = cat.empty or pd.to_datetime(cat["filing_date"]).dt.date.max() <= as_of
    g.check("catalyst: every filing_date ≤ as_of", ok_cat,
            f"max filing_date={None if cat.empty else pd.to_datetime(cat['filing_date']).dt.date.max()} ≤ {as_of}")
    flow = load_flow_data(eng, as_of=as_of)
    ins, sh = flow["insider"], flow["shareholding"]
    ok_ins = ins.empty or pd.to_datetime(ins["transaction_date"]).dt.date.max() <= as_of
    ok_sh = sh.empty or pd.to_datetime(sh["period_end"]).dt.date.max() <= as_of
    g.check("flow insider: every transaction_date ≤ as_of", ok_ins)
    g.check("flow shareholding: every period_end ≤ as_of", ok_sh)


# ───────────────────────────── C5 depth ─────────────────────────────
def check_C5(g: Gate):
    print("== C5: depth — every NIFTY-50 session scored (runtime-derived), ≥80% deep ==")
    end = _max_session()
    sess = _sessions(START, end)
    nsess = len(sess)
    jdates = _df(f"SELECT DISTINCT date FROM {L} WHERE asset_class='stock' "
                 "AND date>=:s AND date<=:e", {"s": START, "e": end})
    njournal = len(jdates)
    g.check(f"journal distinct dates == NIFTY-50 sessions ({nsess}, runtime-derived)",
            njournal == nsess, f"journal={njournal} sessions={nsess}")
    # per-instrument depth credited from first tradable session (late listings ok)
    depth = _df(f"""
        WITH first_seen AS (
          SELECT instrument_id, min(date) f0 FROM {TD}
          WHERE date>=:s AND date<=:e GROUP BY 1),
        expected AS (
          SELECT fs.instrument_id,
                 (SELECT count(*) FROM {IDX} WHERE index_code='NIFTY 50'
                    AND date>=fs.f0 AND date<=:e) exp_dates
          FROM first_seen fs),
        got AS (
          SELECT instrument_id, count(DISTINCT date) g FROM {L}
          WHERE asset_class='stock' AND date>=:s AND date<=:e GROUP BY 1)
        SELECT count(*) pop,
               sum((g.g >= 0.95*e.exp_dates)::int) deep
        FROM expected e JOIN got g USING (instrument_id)
        WHERE e.exp_dates > 0""", {"s": START, "e": end})
    pop = int(depth["pop"].iloc[0] or 0)
    deep = int(depth["deep"].iloc[0] or 0)
    frac = deep / pop if pop else 0.0
    g.check("≥80% instruments scored on ≥95% of their tradable sessions",
            frac >= 0.80, f"{deep}/{pop} = {frac:.0%}")


# ──────────────────── C6 composite consumes DB weights ────────────────────
def check_C6(g: Gate):
    print("== C6: composite consumes DB lens weights (blocker 0a) ==")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    from decimal import Decimal
    from atlas.db import get_engine, load_thresholds
    from atlas.lenses.compute.composite import _DEFAULT_WEIGHTS, compute_composite
    from atlas.lenses.compute.thresholds_view import nest_thresholds
    eng = get_engine()
    raw = load_thresholds(engine=eng)
    flat = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in raw.items()}
    th = nest_thresholds(flat)

    def f(v): return float(v) if v is not None and pd.notna(v) else None

    def comp(r, thr):
        return float(compute_composite(
            technical=f(r["technical"]), fundamental=f(r["fundamental"]),
            valuation_score=f(r["valuation"]), catalyst=f(r["catalyst"]),
            flow=f(r["flow"]), policy=f(r["policy"]),
            valuation_multiplier=f(r["valuation_multiplier"]) or 1.0,
            smart_money_score=f(r["smart_money_score"]) or 0.0,
            degradation_score=f(r["degradation_score"]) or 0.0, thresholds=thr).final_score)

    end = _max_session()
    sample = _df(f"""SELECT technical,fundamental,valuation,catalyst,flow,policy,
                            valuation_multiplier,smart_money_score,degradation_score,composite
                     FROM {L} WHERE asset_class='stock' AND date=:d AND composite IS NOT NULL
                       AND technical IS NOT NULL AND catalyst IS NOT NULL
                     LIMIT 60""", {"d": end})

    # Perturbed weights (differ from BOTH the DB and the hard-coded defaults) — used
    # to prove the recompute genuinely depends on the weights, so reconciliation (a)
    # is a real constraint rather than a no-op (review finding #1/#8).
    pflat = dict(flat); pflat["lens_weight_technical"] = 0.0; pflat["lens_weight_catalyst"] = 0.50
    thp = nest_thresholds(pflat)
    # Default-weighted thresholds — the journal must NOT match these once the DB
    # weights diverge from defaults (post-IC-calibration); this is the definitive
    # catch for a pipeline that stopped consuming DB weights.
    dflat = dict(flat)
    for ln, w in _DEFAULT_WEIGHTS.items():
        dflat[f"lens_weight_{ln}"] = w
    thd = nest_thresholds(dflat)

    rec = sensitive = 0
    for _, r in sample.iterrows():
        db_s = comp(r, th)
        if abs(db_s - float(r["composite"])) <= 0.1:
            rec += 1
        if abs(db_s - comp(r, thp)) > 0.5:
            sensitive += 1
    g.check("stored composite reconciles to DB-weighted compute_composite (≥95%)",
            len(sample) >= 20 and rec >= 0.95 * len(sample), f"{rec}/{len(sample)} reconciled")
    g.check("recompute is weight-sensitive (DB≠perturbed) — reconciliation (a) is a real constraint",
            sensitive >= 0.75 * len(sample), f"{sensitive}/{len(sample)} rows move on perturbation")

    # Definitive discriminator: if the DB weights diverge from the composite
    # defaults (true after IC calibration), the journal must track the DB weights,
    # NOT the defaults — i.e. a sizeable share of rows must MISMATCH the
    # default-weighted recompute. While DB==defaults (pre-calibration) this is
    # vacuous and we say so rather than pretend it discriminates.
    db_w = {ln: float(flat.get(f"lens_weight_{ln}", w)) for ln, w in _DEFAULT_WEIGHTS.items()}
    diverged = any(abs(db_w[ln] - w) > 1e-9 for ln, w in _DEFAULT_WEIGHTS.items())
    if diverged:
        mism = sum(1 for _, r in sample.iterrows() if abs(comp(r, thd) - float(r["composite"])) > 0.1)
        g.check("journal tracks DB (IC-learned) weights, not composite defaults",
                mism >= 0.5 * len(sample), f"{mism}/{len(sample)} rows differ from default-weighted")
    else:
        print("   [note] DB lens weights still == composite defaults; the default-vs-DB "
              "discriminator becomes active once IC calibration writes non-default weights.")


# ──────────────────── C7 forward returns + walk-forward IC ────────────────────
def check_C7(g: Gate):
    print("== C7: forward returns are forward + walk-forward OOS IC ≥ floor + persisted ==")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    from atlas.db import get_engine
    from atlas.lenses.calibration import _load_fwd_returns, walk_forward_folds
    eng = get_engine()
    h = 21
    rw = _load_fwd_returns(eng, h)
    g.check("forward-return panel non-empty", not rw.empty, f"shape={getattr(rw,'shape',None)}")

    # (a) the returns fed to IC are TRUE forward: rw.loc[D, i] == px(D+h)/px(D)-1
    # where D+h is h NSE SESSIONS ahead (matching the loader's calendar reindex),
    # and NOT the trailing technical_daily.ret_1m. Verified independently using the
    # SAME price column the loader uses (COALESCE(close_adj, close)).
    sess = _sessions(START, _max_session())
    sess_pos = {pd.Timestamp(d): i for i, d in enumerate(sess)}
    if not rw.empty:
        fwd_ok = trail_diff = samp = 0
        cols = list(rw.columns)[:80]
        for iid in cols:
            ser = rw[iid].dropna()
            if ser.empty:
                continue
            D = ser.index[len(ser) // 2]
            if D not in sess_pos or sess_pos[D] + h >= len(sess):
                continue
            val = float(ser.loc[D])
            Dh = sess[sess_pos[D] + h]
            c0 = _scalar(f"SELECT COALESCE(close_adj, close) FROM {OHLCV} "
                         "WHERE instrument_id=:i AND date=:d", {"i": str(iid), "d": pd.Timestamp(D).date()})
            ch = _scalar(f"SELECT COALESCE(close_adj, close) FROM {OHLCV} "
                         "WHERE instrument_id=:i AND date=:d", {"i": str(iid), "d": pd.Timestamp(Dh).date()})
            if c0 and ch and float(c0) > 0:
                exp = float(ch) / float(c0) - 1.0
                if abs(exp - val) <= 1e-4:
                    fwd_ok += 1
                # trailing ret_1m on date D (the OLD bug source) should usually differ
                tr = _scalar(f"SELECT ret_1m FROM {TD} WHERE instrument_id=:i AND date=:d",
                             {"i": str(iid), "d": pd.Timestamp(D).date()})
                if tr is not None and abs(float(tr) - val) > 1e-4:
                    trail_diff += 1
                samp += 1
            if samp >= 15:
                break
        g.check("fwd_return == px(D+h)/px(D)-1 over h NSE sessions (true forward, ≥14/15)",
                samp >= 10 and fwd_ok >= samp - 1, f"{fwd_ok}/{samp} match session-ahead close")
        g.check("fwd_return ≠ trailing ret_1m (the old tautology), ≥80%",
                samp >= 10 and trail_diff / max(samp, 1) >= 0.80,
                f"{trail_diff}/{samp} differ from trailing")

    # (b) walk-forward: ≥4 non-overlapping folds (purge+embargo), OOS test-IC ≥ floor for top-2 lenses
    folds = walk_forward_folds(eng, forward_days=h, n_folds=5, embargo=h)
    n_folds = len(folds)
    g.check("≥4 non-overlapping walk-forward folds", n_folds >= 4, f"{n_folds} folds")
    if folds:
        # aggregate OOS test IC per lens across folds
        agg: dict[str, list] = {}
        for fo in folds:
            for lens, ic in fo["test_ic"].items():
                if ic is not None and not pd.isna(ic):
                    agg.setdefault(lens, []).append(ic)
        means = {k: sum(v) / len(v) for k, v in agg.items() if v}
        top = sorted(means.items(), key=lambda kv: abs(kv[1]), reverse=True)[:2]
        passed = sum(1 for _, ic in top if abs(ic) >= IC_FLOOR)
        g.check(f"OOS test-IC ≥ {IC_FLOOR} for ≥2 lenses",
                passed >= 2, f"top: {[(k, round(v,4)) for k,v in top]}")

    # (c) persisted with PROVENANCE — constrained to the current run's as_of and
    # horizons so the 30 pre-existing stale NaN rows can't satisfy it (review #4),
    # and only ACTIVE weight rows count.
    nw = _scalar("SELECT count(*) FROM atlas.atlas_signal_weights "
                 "WHERE signal_name LIKE 'lens_%' AND effective_to IS NULL")
    nic_recent = _scalar("SELECT count(*) FROM atlas.atlas_signal_ic WHERE signal_name LIKE 'lens_%' "
                         "AND mean_ic IS NOT NULL AND as_of_date >= CURRENT_DATE - 7 "
                         "AND forward_period_days IN (21,63,126)")
    g.check("active lens weights persisted to atlas_signal_weights", (nw or 0) > 0, f"{nw} active rows")
    g.check("fresh non-NaN lens IC rows (recent as_of; stale NaN superseded)", (nic_recent or 0) >= 5,
            f"{nic_recent} fresh non-NaN lens-IC rows")


# ──────────────────── C8 graceful degradation ────────────────────
def check_C8(g: Gate):
    print("== C8: graceful degradation is real (not fabricated) ==")
    early = _scalar(f"SELECT avg(coverage_factor) FROM {L} WHERE asset_class='stock' "
                    "AND date BETWEEN '2019-01-01' AND '2020-12-31'")
    late = _scalar(f"SELECT avg(coverage_factor) FROM {L} WHERE asset_class='stock' "
                   "AND date BETWEEN '2024-01-01' AND '2026-12-31'")
    g.check("early-year coverage_factor < late-year (real sparsity)",
            early is not None and late is not None and float(early) < float(late),
            f"early={None if early is None else round(float(early),3)} late={None if late is None else round(float(late),3)}")
    # names with xbrl_state='no_data' must have fundamental NULL on every date
    bad = _scalar(f"""
        SELECT count(*) FROM {L} l
        JOIN foundation_staging.xbrl_state x ON x.instrument_id=l.instrument_id
        WHERE x.status='no_data' AND l.asset_class='stock' AND l.fundamental IS NOT NULL""")
    g.check("xbrl no_data names have fundamental NULL on every date", (bad or 0) == 0,
            f"{bad} violating rows")
    # absent source -> None (never 0): a non-trivial share of early rows have NULL fundamental
    null_fund_early = _scalar(f"SELECT count(*) FROM {L} WHERE asset_class='stock' "
                              "AND date BETWEEN '2019-01-01' AND '2019-12-31' AND fundamental IS NULL")
    any_early = _scalar(f"SELECT count(*) FROM {L} WHERE asset_class='stock' "
                        "AND date BETWEEN '2019-01-01' AND '2019-12-31'")
    g.check("early-year fundamental legitimately NULL for sparse names (not coerced to 0)",
            (any_early or 0) > 0 and (null_fund_early or 0) > 0,
            f"{null_fund_early}/{any_early} early rows have NULL fundamental")


CHECKS = {"C1": check_C1, "C2": check_C2, "C3": check_C3, "C4": check_C4,
          "C5": check_C5, "C6": check_C6, "C7": check_C7, "C8": check_C8}
MODES = {"full": list(CHECKS), "progress": ["C1", "C2", "C5"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=list(MODES))
    ap.add_argument("--check", choices=list(CHECKS))
    args = ap.parse_args()
    if args.check:
        selected = [args.check]
    elif args.mode:
        selected = MODES[args.mode]
    else:
        selected = MODES["full"]
    g = Gate()
    for c in selected:
        try:
            CHECKS[c](g)
        except Exception as e:
            print(f"  \033[31mFAIL\033[0m {c} raised: {e!r}")
            g.fails += 1
    print(f"\n{'✅ ALL GREEN' if g.fails == 0 else f'❌ {g.fails} assertion(s) FAILED'} "
          f"({', '.join(selected)})")
    sys.exit(0 if g.fails == 0 else 1)


if __name__ == "__main__":
    main()
