"""Portfolio data layer — ALL DB reads shared by portfolio_run and
portfolio_evolve: universe, technicals/composite panels, price panels on the
real NSE session calendar, cost/tax knobs, and FIFO enrichment of new trades.
Pure I/O + assembly; strategy/engine math lives in atlas.portfolio.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import _db
import pandas as pd

from atlas.portfolio.tax import TaxRates, enrich_trades

M = "atlas_foundation"


def load_portfolio(pid: str) -> dict:
    df = _db.read_df(f"select * from {M}.portfolio_master where portfolio_id = :p", {"p": pid})
    if df.empty:
        raise SystemExit(f"portfolio {pid} not found")
    return df.iloc[0].to_dict()


def load_universe(
    asset_classes: list[str], fund_categories: list[str] | None = None
) -> pd.DataFrame:
    """(instrument_key, asset_class, symbol, sector) for the declared universe.
    fund_categories (exact atlas_universe_funds.category_name values) restricts the
    fund sleeve — e.g. ['India Fund Large-Cap'] for a large-cap MF portfolio."""
    parts = []
    eq = [c for c in asset_classes if c in ("stock", "etf")]
    if eq:
        # Stocks are the SCORED universe (Nifty 500 as ranked by the lens pipeline),
        # not every listed name — composite ranking is the FM's selection rule.
        parts.append(
            _db.read_df(
                f"""select i.instrument_id::text as instrument_key, i.asset_class, i.symbol, i.sector
                    from {M}.instrument_master i
                    where i.is_active and i.kite_token is not null and i.asset_class = any(:ac)
                      and (i.asset_class <> 'stock' or exists (
                            select 1 from {M}.atlas_lens_scores_daily s
                            where s.instrument_id = i.instrument_id
                              and s.date = (select max(date) from {M}.atlas_lens_scores_daily)))""",
                {"ac": eq},
            )
        )
    if "fund" in asset_classes:
        if fund_categories:
            f = _db.read_df(
                f"select mstar_id, scheme_name from {M}.atlas_universe_funds "
                "where category_name = any(:c)",
                {"c": list(fund_categories)},
            )
        else:
            f = _db.read_df(f"select mstar_id, scheme_name from {M}.atlas_universe_funds")
        parts.append(
            pd.DataFrame(
                {
                    "instrument_key": f["mstar_id"],
                    "asset_class": "fund",
                    "symbol": f["scheme_name"],
                    "sector": None,
                }
            )
        )
    return (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame(columns=pd.Index(["instrument_key", "asset_class", "symbol", "sector"]))
    )


def load_tech(
    universe: pd.DataFrame, cols: tuple[str, ...], since: dt.date, until: dt.date
) -> pd.DataFrame:
    """EMA panel (instrument_key, date, <cols>) across asset classes."""
    collist = ", ".join(cols)
    parts = []
    if (universe["asset_class"] != "fund").any():
        parts.append(
            _db.read_df(
                f"""select t.instrument_id::text as instrument_key, t.date, {collist}
                    from {M}.technical_daily t
                    where t.instrument_id::text = any(:ks) and t.date between :a and :b
                    order by t.date""",
                {
                    "ks": universe.loc[
                        universe["asset_class"] != "fund", "instrument_key"
                    ].tolist(),
                    "a": since,
                    "b": until,
                },
            )
        )
    if (universe["asset_class"] == "fund").any():
        parts.append(
            _db.read_df(
                f"""select mstar_id as instrument_key, date, {collist}
                    from {M}.technical_fund_daily
                    where mstar_id = any(:ks) and date between :a and :b order by date""",
                {
                    "ks": universe.loc[
                        universe["asset_class"] == "fund", "instrument_key"
                    ].tolist(),
                    "a": since,
                    "b": until,
                },
            )
        )
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def load_prices(universe: pd.DataFrame, since: dt.date, until: dt.date) -> pd.DataFrame:
    """Date-indexed price panel (Decimal), one column per instrument_key, ffilled."""
    parts = []
    by_class = {c: g["instrument_key"].tolist() for c, g in universe.groupby("asset_class")}
    if by_class.get("stock"):
        parts.append(
            _db.read_df(
                f"""select instrument_id::text as instrument_key, date, close_adj as price
                    from {M}.ohlcv_stock
                    where instrument_id::text = any(:ks) and close_adj > 0
                      and date between :a and :b""",
                {"ks": by_class["stock"], "a": since, "b": until},
            )
        )
    if by_class.get("etf"):
        parts.append(
            _db.read_df(
                f"""select i.instrument_id::text as instrument_key, o.date, o.close_adj as price
                    from {M}.ohlcv_etf o
                    join {M}.instrument_master i on i.symbol = o.ticker and i.asset_class = 'etf'
                    where i.instrument_id::text = any(:ks) and o.close_adj > 0
                      and o.date between :a and :b""",
                {"ks": by_class["etf"], "a": since, "b": until},
            )
        )
    if by_class.get("fund"):
        parts.append(
            _db.read_df(
                f"""select mstar_id as instrument_key, nav_date as date, nav as price
                    from {M}.de_mf_nav_daily
                    where mstar_id = any(:ks) and nav > 0 and nav_date between :a and :b""",
                {"ks": by_class["fund"], "a": since, "b": until},
            )
        )
    long = pd.concat(parts, ignore_index=True)
    if long.empty:
        raise SystemExit("no prices in window — check universe/asset_classes")
    panel = long.pivot_table(
        index="date", columns="instrument_key", values="price", aggfunc="last"
    ).sort_index()
    # Day-loop calendar = REAL NSE sessions (NIFTY 50). A handful of instruments carry
    # spurious holiday rows; without this the engine booked trades on Republic Day.
    sessions = _db.read_df(
        f"""select date from {M}.index_prices
            where index_code = 'NIFTY 50' and date between :a and :b order by date""",
        {"a": since, "b": until},
    )["date"]
    return panel.reindex(sessions.tolist())


def load_composite(universe: pd.DataFrame, since: dt.date, until: dt.date) -> pd.DataFrame:
    return _db.read_df(
        f"""select instrument_id::text as instrument_key, date, composite
            from {M}.atlas_lens_scores_daily
            where instrument_id::text = any(:ks) and date between :a and :b""",
        {"ks": universe["instrument_key"].tolist(), "a": since, "b": until},
    )


def open_positions(pid: str, run_type: str = "live") -> dict[str, Decimal]:
    df = _db.read_df(
        f"""select instrument_key,
                   sum(case when side='buy' then qty else -qty end) as qty
            from {M}.portfolio_trades
            where portfolio_id = :p and run_type = :r group by 1""",
        {"p": pid, "r": run_type},
    )
    return {
        r["instrument_key"]: Decimal(r["qty"])
        for r in df.to_dict("records")
        if Decimal(r["qty"]) != 0
    }


def open_entry_dates(pid: str, run_type: str = "live") -> dict:
    """For each still-held instrument, the date its current lot was opened (latest
    buy after the last full exit) — needed so a fund's exit load is charged
    correctly when the nightly increment sells it. Crossover strategies buy once
    and hold, so max(buy trade_date) is the entry."""
    df = _db.read_df(
        f"""with net as (
              select instrument_key,
                     sum(case when side='buy' then qty else -qty end) qty,
                     max(trade_date) filter (where side='buy') last_buy
              from {M}.portfolio_trades where portfolio_id = :p and run_type = :r
              group by 1)
            select instrument_key, last_buy from net where qty <> 0""",
        {"p": pid, "r": run_type},
    )
    return {r["instrument_key"]: r["last_buy"] for r in df.to_dict("records")}


# ── cost / tax knobs (atlas_thresholds, category=portfolio) ────────────────


def load_cost_tax():
    th = _db.read_df(
        f"select threshold_key k, threshold_value v from {M}.atlas_thresholds "
        "where category = 'portfolio' and is_active"
    )
    m = {r["k"]: Decimal(str(r["v"])) for r in th.to_dict("records")}
    costs = {
        ac: (m[f"portfolio_cost_{ac}_buy_pct"], m[f"portfolio_cost_{ac}_sell_pct"])
        for ac in ("stock", "etf", "fund")
    }
    rates = TaxRates(
        stcg=m["portfolio_tax_stcg_pct"],
        ltcg=m["portfolio_tax_ltcg_pct"],
        ltcg_exemption=m["portfolio_tax_ltcg_exemption_inr"],
        ltcg_days=int(m["portfolio_tax_ltcg_days"]),
    )
    exit_load = (m["portfolio_exit_load_fund_pct"], int(m["portfolio_exit_load_fund_days"]))
    return costs, rates, exit_load


_TAX_COLS = ["realized_pnl", "holding_days", "tax_bucket", "tax"]


def _enrich_new_trades(pid: str, run_type: str, new: pd.DataFrame, rates: TaxRates) -> pd.DataFrame:
    """FIFO needs the FULL trade history — prepend stored trades, enrich, take the tail."""
    if new.empty or not (new["side"] == "sell").any():
        out = new.copy()
        for c in _TAX_COLS:
            out[c] = None
        return out
    prior = _db.read_df(
        f"""select trade_date, asset_class, instrument_key, symbol, side, qty, price,
                   value, cost, reason
            from {M}.portfolio_trades where portfolio_id = :p and run_type = :r
            order by trade_date, trade_id""",
        {"p": pid, "r": run_type},
    )
    cols = list(prior.columns if not prior.empty else new.columns)
    combined = pd.DataFrame(pd.concat([prior, new[cols]], ignore_index=True))
    enriched = enrich_trades(combined, rates)
    tail = enriched.tail(len(new)).reset_index(drop=True)
    out = new.reset_index(drop=True).copy()
    for c in _TAX_COLS:
        out[c] = tail[c].values
    return out
