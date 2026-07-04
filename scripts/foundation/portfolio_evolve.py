#!/usr/bin/env python3
"""Walk-forward champion/challenger for system-generated portfolios (feature a).

The "expert agent" is deterministic and glass-box: it never picks a stock, it
tunes the AtlasPolicy rulebook (interpretable knobs over Atlas's own signals).
Each cycle:

  1. load the full panel ONCE for [train_start, val_end] (prices/EMAs/RS/composite/
     regime), so every candidate simulation is a fast in-memory pandas loop.
  2. champion = the portfolio's current params.
  3. challengers = one-knob mutations of the champion.
  4. simulate each on the TRAIN window; fitness = excess return over NIFTY 500,
     HARD-gated by max-drawdown-below-NIFTY-500. Disqualify constraint violators.
  5. take the best few by train fitness, VALIDATE on the later out-of-sample window.
  6. promote a challenger only if its validation excess beats the champion's by
     >= min_improve_pp AND it passes the DD constraint on validation.
  7. journal the evaluation (all candidates + verdict) and, on promotion, the change
     — full evidence, rendered as the portfolio's learning log.

    python portfolio_evolve.py                       # evolve every active system portfolio
    python portfolio_evolve.py --portfolio-id X       # just one
    python portfolio_evolve.py --portfolio-id X --seed # first-time: adopt best of the grid

Live money always runs the current champion; a promotion here is followed by the
nightly mark picking up the new params. Backtests are re-run on promotion so the
board's curve matches the live rulebook.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from decimal import Decimal

import _db
import pandas as pd
import portfolio_run as pr

from atlas.portfolio import PortfolioConfig, get_strategy, replay

M = "atlas_foundation"
_EMA_PAIRS = [(10, 21), (21, 50), (50, 200)]


def _knobs():
    th = _db.read_df(
        f"select threshold_key k, threshold_value v from {M}.atlas_thresholds "
        "where category = 'portfolio' and is_active"
    )
    m = {r["k"]: Decimal(str(r["v"])) for r in th.to_dict("records")}
    return {
        "train_years": int(m["portfolio_evolve_train_years"]),
        "val_months": int(m["portfolio_evolve_val_months"]),
        "min_improve_pp": float(m["portfolio_evolve_min_improve_pp"]),
        "min_days_change": int(m["portfolio_evolve_min_days_change"]),
        "min_trades": int(m["portfolio_evolve_min_trades"]),
    }


# ── candidate policy grid (one-knob neighbours of the champion) ─────────────


def neighbours(params: dict, equity_signals: bool = True) -> list[dict]:
    """One-knob mutations of `params` over the interpretable AtlasPolicy space.
    equity_signals=False (fund universes) drops composite/RS knobs — funds carry
    only EMA columns and a market-level regime."""
    base = {
        "fast": params.get("fast", 21),
        "slow": params.get("slow", 50),
        "confirm_200": params.get("confirm_200", False),
        "rs_min": params.get("rs_min", None) if equity_signals else None,
        "min_composite": params.get("min_composite", None) if equity_signals else None,
        "regime_gate": params.get("regime_gate", False),
    }
    out = [dict(base)]
    for fast, slow in _EMA_PAIRS:
        if (fast, slow) != (base["fast"], base["slow"]):
            out.append({**base, "fast": fast, "slow": slow})
    knob_space = [
        ("confirm_200", [not base["confirm_200"]]),
        ("regime_gate", [not base["regime_gate"]]),
    ]
    if equity_signals:
        knob_space += [
            ("rs_min", [v for v in (None, 0.0, 0.05) if v != base["rs_min"]]),
            ("min_composite", [v for v in (None, 50, 60, 70) if v != base["min_composite"]]),
        ]
    for knob, choices in knob_space:
        for v in choices:
            out.append({**base, knob: v})
    # de-dup (dicts unhashable → compare via json)
    seen, uniq = set(), []
    for c in out:
        key = json.dumps(c, sort_keys=True)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


# ── panel loading (ONCE) + fast in-memory simulation ────────────────────────


def load_panels(universe: pd.DataFrame, start: dt.date, end: dt.date) -> dict:
    equity_signals = (universe["asset_class"] != "fund").all()
    ema_cols = ["ema_10", "ema_21", "ema_50", "ema_200"]
    if equity_signals:
        ema_cols.append("rs_3m_n500")  # only technical_daily carries RS
    tech = pr.load_tech(universe, tuple(ema_cols), start, end)
    comp = pr.load_composite(universe, start, end)
    tech = tech.merge(comp, on=["instrument_key", "date"], how="left")
    regime = _db.read_df(
        f"select date, regime_state from {M}.atlas_market_regime_daily where date between :a and :b",
        {"a": start, "b": end},
    )
    tech = tech.merge(regime, on="date", how="left")
    prices = pr.load_prices(universe, start, end)
    bench = _db.read_df(
        f"select date, close from {M}.index_prices where index_code = 'NIFTY 500' "
        "and date between :a and :b order by date",
        {"a": start, "b": end},
    )
    return {
        "tech": tech,
        "comp": comp,
        "prices": prices,
        "asset_class": dict(zip(universe["instrument_key"], universe["asset_class"], strict=False)),
        "symbols": dict(zip(universe["instrument_key"], universe["symbol"], strict=False)),
        "bench": bench.set_index("date")["close"].astype(float),
    }


def _max_dd(series: pd.Series) -> float:
    if len(series) < 2:
        return 0.0
    peak = series.cummax()
    return float(((series - peak) / peak).min())


def simulate(
    params: dict, panel: dict, cfg: PortfolioConfig, costs, a: dt.date, b: dt.date
) -> dict:
    """Run AtlasPolicy(params) over [a, b] on the preloaded panel → window metrics."""
    strat = get_strategy("atlas_policy", params)
    tech = panel["tech"]
    tech_win = tech[(tech["date"] >= a - dt.timedelta(days=400)) & (tech["date"] <= b)]
    events = strat.events(tech_win)
    events = events[events["date"] >= a]
    px = panel["prices"]
    loop = [d for d in px.index if a <= d <= b]
    if not loop:
        return {"disq": True}
    _trades, navs = replay(
        cfg,
        prices=px,
        events=events,
        inception_state=None,
        composite=panel["comp"],
        asset_class=panel["asset_class"],
        symbols=panel["symbols"],
        loop_dates=loop,
        costs=costs,
    )
    nav = pd.Series(navs.set_index("date")["nav"].astype(float))
    bench = pd.Series(panel["bench"].reindex(nav.index).ffill())
    port_ret = float(nav.iloc[-1] / nav.iloc[0] - 1)
    bench_clean = bench.dropna()
    bench_ret = float(bench.iloc[-1] / bench.iloc[0] - 1) if len(bench_clean) > 1 else 0.0
    port_dd, bench_dd = _max_dd(nav), _max_dd(bench_clean)
    return {
        "disq": False,
        "excess": round((port_ret - bench_ret) * 100, 2),
        "port_return_pct": round(port_ret * 100, 2),
        "bench_return_pct": round(bench_ret * 100, 2),
        "port_maxdd_pct": round(port_dd * 100, 2),
        "bench_maxdd_pct": round(bench_dd * 100, 2),
        # constraint: portfolio drawdown SHALLOWER than the benchmark's
        "dd_ok": port_dd >= bench_dd,
        "n_trades": len(_trades),
    }


# ── the cycle ───────────────────────────────────────────────────────────────


def evolve_one(pid: str, seed: bool, knobs: dict) -> dict:
    p = pr.load_portfolio(pid)
    eod = _db.eod_cutoff()
    val_end = eod
    val_start = val_end - dt.timedelta(days=int(knobs["val_months"] * 30.44))
    train_end = val_start - dt.timedelta(days=1)
    train_start = train_end - dt.timedelta(days=int(knobs["train_years"] * 365))

    universe = pr.load_universe(list(p["asset_classes"]))
    costs, _rates = pr.load_cost_tax()
    cfg = PortfolioConfig(
        portfolio_id=pid,
        kind="strategy",
        initial_capital=Decimal(p["initial_capital"]),
        max_position_pct=Decimal(p["max_position_pct"]),
    )
    panel = load_panels(universe, train_start - dt.timedelta(days=400), val_end)

    equity_signals = (universe["asset_class"] != "fund").all()
    champ = p["params"] if isinstance(p["params"], dict) else json.loads(p["params"])
    # seed: champion is the whole grid's best; else neighbours of the current champion
    candidates = neighbours(champ if not seed else {}, equity_signals=equity_signals)

    # 1. score every candidate on TRAIN
    scored = []
    for c in candidates:
        tr = simulate(c, panel, cfg, costs, train_start, train_end)
        if tr["disq"] or tr["n_trades"] < knobs["min_trades"] or not tr["dd_ok"]:
            continue
        scored.append((c, tr))
    scored.sort(key=lambda x: -x[1]["excess"])

    # champion's own validation baseline
    champ_val = simulate(champ, panel, cfg, costs, val_start, val_end)

    # 2. validate the top few train performers OOS
    finalists = []
    for c, tr in scored[:4]:
        va = simulate(c, panel, cfg, costs, val_start, val_end)
        if not va["disq"] and va["dd_ok"]:
            finalists.append({"params": c, "train": tr, "val": va})
    finalists.sort(key=lambda f: -f["val"]["excess"])

    evidence = {
        "windows": {
            "train": [str(train_start), str(train_end)],
            "val": [str(val_start), str(val_end)],
        },
        "champion": {"params": champ, "val": champ_val},
        "candidates_scored": len(scored),
        "finalists": finalists[:4],
    }
    _journal(pid, "evaluation", None, None, evidence)

    # 3. promote?
    best = finalists[0] if finalists else None
    champ_val_excess = champ_val["excess"] if not champ_val["disq"] else -1e9
    promote = (
        best is not None
        and (seed or best["val"]["excess"] >= champ_val_excess + knobs["min_improve_pp"])
        and best["params"] != champ
    )
    if not promote or best is None:
        return {
            "portfolio": p["name"],
            "promoted": False,
            "reason": "no challenger cleared the bar",
        }

    _db.exec_sql(
        f"update {M}.portfolio_master set params = cast(:pp as jsonb) where portfolio_id = :id",
        {"pp": json.dumps(best["params"]), "id": pid},
    )
    _journal(pid, "change", champ, best["params"], {**evidence, "adopted": best})
    # board curve must reflect the live rulebook: re-run this portfolio's backtest
    pr.rebuild_backtest(pid)
    return {
        "portfolio": p["name"],
        "promoted": True,
        "old": champ,
        "new": best["params"],
        "val_excess": best["val"]["excess"],
    }


def _journal(pid, kind, old_params, new_params, evidence):
    _db.exec_sql(
        f"""insert into {M}.portfolio_policy_journal
            (portfolio_id, kind, old_params, new_params, evidence)
            values (:id, :k, cast(:op as jsonb), cast(:np as jsonb), cast(:ev as jsonb))""",
        {
            "id": pid,
            "k": kind,
            "op": json.dumps(old_params) if old_params is not None else None,
            "np": json.dumps(new_params) if new_params is not None else None,
            "ev": json.dumps(evidence, default=str),
        },
    )


def main():
    ap = argparse.ArgumentParser(description="Walk-forward evolve for system portfolios")
    ap.add_argument("--portfolio-id")
    ap.add_argument(
        "--seed", action="store_true", help="adopt the best of the full grid (first run)"
    )
    a = ap.parse_args()
    knobs = _knobs()
    if a.portfolio_id:
        ids = [a.portfolio_id]
    else:
        # ONLY atlas_policy portfolios evolve here — rank_policy/desk system rows
        # have different param spaces and would crash the neighbour grid
        ids = _db.read_df(
            f"select portfolio_id::text pid from {M}.portfolio_master "
            "where origin = 'system' and status = 'active' and strategy_key = 'atlas_policy'"
        )["pid"].tolist()
    for pid in ids:
        # anti-noise: skip if a change landed within min_days_change (unless seeding)
        if not a.seed:
            last = _db.scalar(
                f"select max(ts) from {M}.portfolio_policy_journal where portfolio_id = :p and kind = 'change'",
                {"p": pid},
            )
            if (
                last is not None
                and (dt.datetime.now(last.tzinfo) - last).days < knobs["min_days_change"]
            ):
                print(f"[evolve] {pid}: changed recently — skipping", flush=True)
                continue
        res = evolve_one(pid, a.seed, knobs)
        print(f"[evolve] {json.dumps(res, default=str)}", flush=True)


if __name__ == "__main__":
    main()
