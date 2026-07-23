"""Shared bits for the wealth transaction engine (DB conn, XIRR, NAV series).

External-flow semantics (single source of truth for every engine module):
  money the client sent in  = purchase | sip
  money the client took out = redemption | swp | div_payout (cash left the book)
  internal (excluded)       = switch_* | dtp_* | div_reinvest | bonus | segregation
                              | merger_* | transfer_* | pledge | unpledge | opening_balance
Opening-balance / transfer-in positions have no cash-flow record — clients
carrying them are flagged `approx` by callers that care.
"""

from __future__ import annotations

import os
from datetime import date

import numpy as np
import pandas as pd
import psycopg2

BENCH_ID = "F0GBR06R0H"  # ICICI Pru Nifty 50 Index Reg Gr, NAV history to 2006
EXTERNAL_IN = ("purchase", "sip")
EXTERNAL_OUT = ("redemption", "swp", "div_payout")


def connect():
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    return psycopg2.connect(dsn)


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Bisection IRR on dated flows (sign convention: invest < 0); % p.a. or None."""
    flows = [(d, a) for d, a in flows if a]
    if len(flows) < 2:
        return None
    t0 = min(d for d, _ in flows)
    yrs = np.array([(d - t0).days / 365.25 for d, _ in flows])
    amt = np.array([a for _, a in flows], float)
    if (amt < 0).all() or (amt > 0).all():
        return None

    def npv(r):
        return float((amt / (1 + r) ** yrs).sum())

    lo, hi = -0.9999, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return round(((lo + hi) / 2) * 100, 2)


def nav_series(conn, mstar_id: str) -> pd.Series:
    nav = pd.read_sql(
        "select nav_date, nav from atlas_foundation.de_mf_nav_daily "
        "where mstar_id = %s and nav > 0 order by nav_date",
        conn,
        params=(mstar_id,),
    )
    s = nav.set_index(pd.to_datetime(nav.nav_date)).nav.astype(float)
    return s[~s.index.duplicated(keep="last")]


class NavLookup:
    """Forward-fill NAV lookup (last NAV on/before date)."""

    def __init__(self, series: pd.Series):
        self.idx = series.index
        self.vals = series.to_numpy()

    def at(self, d: date) -> float | None:
        i = self.idx.searchsorted(pd.Timestamp(d), side="right") - 1
        return float(self.vals[i]) if i >= 0 else None


def external_flows(conn) -> pd.DataFrame:
    """One row per external cash flow: client_id, txn_date, amount (signed: in<0)."""
    df = pd.read_sql(
        f"""select client_id, scheme_id, txn_date, txn_type, amount::float amount
            from wealth.transactions
            where txn_date is not null and amount is not null and amount > 0
              and txn_type in {EXTERNAL_IN + EXTERNAL_OUT}""",
        conn,
    )
    df["txn_date"] = pd.to_datetime(df.txn_date).dt.date
    df["signed"] = np.where(df.txn_type.isin(EXTERNAL_IN), -df.amount, df.amount)
    return df
