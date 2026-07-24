"""Equity-curve engine — the "story curve" behind each client's chart.

  wealth.client_curves       month-end portfolio value: units held (per real
                             wealth.transactions) x month-end NAV, mapped
                             schemes only. coverage_pct is the honest share of
                             CURRENT book market value sitting in mapped
                             schemes (mstar_id + has_nav_series) — no fake
                             curves for the unmapped remainder; <70% is the
                             app's own "insufficient" flag, this engine just
                             records the number.
  wealth.client_curve_events story markers, every one traced to a real
                             wealth.transactions row: panic_sell (external
                             sell inside a behaviour_fingerprints.
                             drawdown_windows window), sip_stop (a >=3-month
                             SIP stream whose last payment is stale), and
                             big_inflow/big_outflow (a single external flow
                             >= this client's own p90 |flow|).

Unit reconstruction: direction is authoritative wealth.transactions.is_debit
(units LEAVING when true) for every txn_type EXCEPT NO_UNIT_EFFECT — types
that move cash/collateral but not fund ownership (div_payout = cash payout,
pledge/unpledge = collateral lock, no unit change). This is deliberately
broader than build_lots.BUY_TYPES/SELL_TYPES or behaviour_fingerprints.
ADD_TYPES/REMOVE_TYPES (both miss real live types like consolidation_in/out
and reversal) — is_debit is the schema's own documented direction, so there
is nothing to guess for any type not in the denylist.

net_flow_rs sign: +ve = client added money that month (flipped from
engine_common.external_flows' XIRR convention where inflows are negative).

Usage: set -a; source .env; set +a; .venv/bin/python scripts/wealth/build_equity_curves.py
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict

import pandas as pd
from behaviour_fingerprints import EXTERNAL_SELL, drawdown_windows
from engine_common import BENCH_ID, EXTERNAL_IN, NavLookup, connect, external_flows, nav_series
from psycopg2.extras import execute_values

# cash/collateral moves that do not change units held (schema-documented, not guessed).
NO_UNIT_EFFECT = {"div_payout", "pledge", "unpledge"}
SIP_STOP_GAP_DAYS = 45  # same "stream gone stale" cutoff as behaviour_fingerprints


def _bulk_navs(conn, mstar_ids: list[str]) -> dict[str, pd.Series]:
    """One round-trip NAV load for many schemes (nav_series() does 1 query each)."""
    if not mstar_ids:
        return {}
    nav = pd.read_sql(
        "select mstar_id, nav_date, nav from atlas_foundation.de_mf_nav_daily "
        "where mstar_id = any(%s) and nav > 0 order by mstar_id, nav_date",
        conn,
        params=(mstar_ids,),
    )
    out = {}
    for mid, g in nav.groupby("mstar_id"):
        s = g.set_index(pd.to_datetime(g.nav_date)).nav.astype(float)
        out[mid] = s[~s.index.duplicated(keep="last")]
    return out


def _coverage(conn) -> dict[int, float | None]:
    """client_id -> honest coverage_pct (None when the client has no MV to cover)."""
    hold = pd.read_sql(
        """select h.client_id, h.market_value::float mv, s.mstar_id, s.has_nav_series
           from wealth.holdings h join wealth.schemes s using (scheme_id)""",
        conn,
    )
    hold["mapped"] = hold.mstar_id.notna() & hold.has_nav_series
    total = hold.groupby("client_id").mv.sum()
    mapped = hold[hold.mapped].groupby("client_id").mv.sum()
    out: dict[int, float | None] = {}
    for cid, tot in total.items():
        if not tot or tot <= 0:
            out[int(cid)] = None
            continue
        out[int(cid)] = round(float(mapped.get(cid, 0.0)) / tot * 100, 2)
    return out


def compute_all(conn) -> tuple[list[dict], list[dict]]:
    txns = pd.read_sql(
        """select client_id, scheme_id, fund_name, folio, txn_date, txn_type,
                  is_debit, units::float units, amount::float amount
           from wealth.transactions
           order by client_id, txn_date nulls first, txn_id""",
        conn,
    )
    txns["txn_date"] = pd.to_datetime(txns.txn_date)

    schemes = pd.read_sql(
        "select scheme_id, mstar_id from wealth.schemes "
        "where mstar_id is not null and has_nav_series",
        conn,
    )
    nav_by_mstar = _bulk_navs(conn, schemes.mstar_id.unique().tolist())
    nav_lookup = {
        int(sid): NavLookup(nav_by_mstar[mid])
        for sid, mid in zip(schemes.scheme_id, schemes.mstar_id)
        if mid in nav_by_mstar and len(nav_by_mstar[mid])
    }

    windows = drawdown_windows(nav_series(conn, BENCH_ID))

    def in_dd(t: pd.Timestamp) -> bool:
        return any(a <= t <= b for a, b in windows)

    ext = external_flows(conn)
    ext["month"] = pd.to_datetime(ext.txn_date).dt.to_period("M")
    flow_by_month = ext.groupby(["client_id", "month"]).signed.sum()
    ext_by_client = dict(tuple(ext.groupby("client_id")))

    coverage = _coverage(conn)
    ledger_end = txns.txn_date.max()
    now_month_end = pd.Timestamp.now().normalize() + pd.offsets.MonthEnd(0)

    curve_rows: list[dict] = []
    event_rows: list[dict] = []

    for cid, g in txns.groupby("client_id"):
        dated = g[g.txn_date.notna()]
        if dated.empty:
            continue
        cov_pct = coverage.get(int(cid))
        first_month_end = dated.txn_date.min() + pd.offsets.MonthEnd(0)
        months = pd.date_range(first_month_end, now_month_end, freq="ME")

        recs = list(g.itertuples())
        idx, n = 0, len(recs)
        units: dict[int, float] = defaultdict(float)

        for month_end in months:
            while idx < n and (pd.isna(recs[idx].txn_date) or recs[idx].txn_date <= month_end):
                r = recs[idx]
                if (
                    pd.notna(r.scheme_id)
                    and pd.notna(r.units)
                    and r.units
                    and r.txn_type not in NO_UNIT_EFFECT
                ):
                    units[int(r.scheme_id)] += -r.units if r.is_debit else r.units
                idx += 1

            value = 0.0
            for sid, u in units.items():
                if u <= 1e-6:
                    continue
                nl = nav_lookup.get(sid)
                nav = nl.at(month_end.date()) if nl else None
                if nav:
                    value += u * nav

            net_flow = -float(flow_by_month.get((cid, month_end.to_period("M")), 0.0))
            curve_rows.append(dict(
                client_id=int(cid), month=month_end.date(),
                value_rs=int(round(max(value, 0.0))),
                net_flow_rs=int(round(net_flow)),
                coverage_pct=cov_pct,
            ))

        # -- story events, all traced to real wealth.transactions rows --
        cext = ext_by_client.get(cid)
        if cext is not None and len(cext):
            thresh = cext.amount.quantile(0.9)
            for r in cext.itertuples():
                if r.txn_type in EXTERNAL_SELL and in_dd(pd.Timestamp(r.txn_date)):
                    event_rows.append(dict(
                        client_id=int(cid), event_date=r.txn_date, kind="panic_sell",
                        amount_rs=int(round(r.amount)),
                        note=f"{r.txn_type} of ~Rs {r.amount:,.0f} during a >10% NAV drawdown",
                    ))
                if thresh > 0 and r.amount >= thresh:
                    kind = "big_inflow" if r.txn_type in EXTERNAL_IN else "big_outflow"
                    event_rows.append(dict(
                        client_id=int(cid), event_date=r.txn_date, kind=kind,
                        amount_rs=int(round(r.amount)),
                        note=f"{r.txn_type} of Rs {r.amount:,.0f}, top decile for this client",
                    ))

        sips = dated[dated.txn_type == "sip"]
        for (_sid, fname, folio), sg in sips.groupby(["scheme_id", "fund_name", "folio"], dropna=False):
            if sg.txn_date.dt.to_period("M").nunique() < 3:
                continue
            last = sg.loc[sg.txn_date.idxmax()]
            if (ledger_end - last.txn_date).days > SIP_STOP_GAP_DAYS:
                event_rows.append(dict(
                    client_id=int(cid), event_date=last.txn_date.date(), kind="sip_stop",
                    amount_rs=int(round(last.amount)) if pd.notna(last.amount) else 0,
                    note=f"SIP into {fname} (folio {folio}) stopped; last payment {last.txn_date.date()}",
                ))

    return curve_rows, event_rows


def main() -> int:
    conn = connect()
    curve_rows, event_rows = compute_all(conn)

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.client_curve_events")
    cur.execute("drop table if exists wealth.client_curves")
    cur.execute(
        """create table wealth.client_curves (
             client_id bigint not null references wealth.clients(client_id),
             month date not null,
             value_rs numeric(18,0) not null,
             net_flow_rs numeric(18,0) not null,
             coverage_pct numeric(5,2),
             primary key (client_id, month)
           )"""
    )
    execute_values(
        cur,
        "insert into wealth.client_curves (client_id, month, value_rs, net_flow_rs, coverage_pct) values %s",
        [(r["client_id"], r["month"], r["value_rs"], r["net_flow_rs"], r["coverage_pct"]) for r in curve_rows],
        page_size=2000,
    )
    cur.execute("revoke all on wealth.client_curves from anon, authenticated")

    cur.execute(
        """create table wealth.client_curve_events (
             event_id bigint generated always as identity primary key,
             client_id bigint not null references wealth.clients(client_id),
             event_date date not null,
             kind text not null,
             amount_rs numeric(18,0) not null,
             note text
           )"""
    )
    execute_values(
        cur,
        "insert into wealth.client_curve_events (client_id, event_date, kind, amount_rs, note) values %s",
        [(r["client_id"], r["event_date"], r["kind"], r["amount_rs"], r["note"]) for r in event_rows],
        page_size=2000,
    )
    cur.execute("create index on wealth.client_curve_events (client_id)")
    cur.execute("revoke all on wealth.client_curve_events from anon, authenticated")
    conn.commit()

    curve_clients = {r["client_id"] for r in curve_rows}
    per_client_cov = {r["client_id"]: r["coverage_pct"] for r in curve_rows}
    covs = sorted(c for c in per_client_cov.values() if c is not None)
    below70 = sum(1 for c in covs if c < 70)
    kind_counts = Counter(r["kind"] for r in event_rows)

    print(f"client_curves: {len(curve_rows)} rows across {len(curve_clients)} clients")
    if covs:
        mid = len(covs) // 2
        median_cov = covs[mid] if len(covs) % 2 else (covs[mid - 1] + covs[mid]) / 2
        print(f"coverage_pct: median {median_cov:.1f}% ({below70} of {len(covs)} clients <70%)")
    print(
        f"client_curve_events: {len(event_rows)} rows -> "
        + ", ".join(f"{k}={v}" for k, v in kind_counts.items())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
