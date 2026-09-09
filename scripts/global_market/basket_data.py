"""Data layer for the basket scripts — every ``atlas_global`` read the marker, the worker and
the gate share: active baskets and their current-version constituents, the SPY session
calendar, the price bars, the trades a book is made of, and the M2 thresholds.

Pure I/O and assembly (India's ``scripts/foundation/portfolio_data.py`` shape). The
accounting lives in ``mark_baskets.py`` and ``atlas.portfolio.engine``; nothing here decides.

PRICES — TWO CLOSES, ONE JOB EACH. ``ohlcv_daily`` carries ``close_adj`` (split-only) and
``close_tr`` (splits AND dividends). A basket is valued on TOTAL RETURN — the plan's "NAV on
close_tr" (docs/global/plan.md, M2) — because a buy-and-hold of dividend payers that ignores
the dividends understates every holding by its yield, ~1.6 percent a year on SPY alone
(``atlas/global_market/price_basis.py``). But the total-return series is anchored to the
PRESENT: ``ingest_prices.py`` rewrites an instrument's whole ``close_tr`` history the night a
dividend goes ex, so the level a fill was booked against yesterday is not the level the same
date carries tomorrow. A fixed quantity times an absolute ``close_tr`` would therefore lose
each dividend on its ex-date and disagree with the stored fill price a quarter later. So:

* the FILL price is ``close_adj`` — the real, transactable print on the split basis, stable
  until a split (India's ``close_adj`` rule, ``validate_portfolios`` check C);
* the MARK grows that fill by total return since entry, ``close_tr[d] / close_tr[entry]``,
  both ends read in the same run and so on the same vintage — invariant to re-basing.

``close_adj`` stands in for ``close_tr`` ONLY where ``close_tr`` is NULL at either end (the
Stooq archive rows carry ``close_tr`` alone and never ``close_adj``, so the reverse fallback
covers the fill), and every such substitution is returned as evidence for the run report —
never a silent switch of series.
"""

from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb (sibling module)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package
import _gdb
import pandas as pd

from atlas.db import load_thresholds
from atlas.global_market import calendar as gcal

M = _gdb.M
RUN_TYPE = "live"

# The M2 rows every basket script needs; a missing one is a seed problem, never a default.
THRESHOLD_KEYS = (
    "basket_default_capital_usd",
    "basket_max_position_pct",
    "basket_cost_bps_buy",
    "basket_cost_bps_sell",
    "basket_min_weight_frac",
)

BASKET_SQL = f"""
SELECT basket_id::text AS basket_id, name, kind, status, current_version,
       initial_capital, inception_date, benchmark_code, created_by
FROM {M}.basket_master
WHERE status = 'active'
ORDER BY created_at, basket_id
"""

CONSTITUENTS_SQL = f"""
SELECT c.instrument_id::text AS instrument_id, im.symbol, im.name, im.asset_class,
       im.is_active, im.fractionable, c.target_weight_frac, c.effective_from
FROM {M}.basket_constituents c
JOIN {M}.instrument_master im USING (instrument_id)
WHERE c.basket_id = :b AND c.version = :v
ORDER BY c.target_weight_frac DESC, im.symbol
"""

SESSIONS_SQL = f"""
SELECT DISTINCT o.date
FROM {M}.ohlcv_daily o
JOIN {M}.instrument_master im ON im.instrument_id = o.instrument_id
WHERE im.symbol = :anchor AND im.is_active AND o.date BETWEEN :a AND :b
ORDER BY o.date
"""

BARS_SQL = f"""
SELECT instrument_id::text AS instrument_id, date, close_adj, close_tr
FROM {M}.ohlcv_daily
WHERE instrument_id = ANY(CAST(:ids AS uuid[])) AND date BETWEEN :a AND :b
ORDER BY instrument_id, date
"""

TRADES_SQL = f"""
SELECT trade_id, trade_date, asset_class, instrument_id::text AS instrument_id, symbol, side,
       qty, price, value, cost, reason, run_id::text AS run_id, version
FROM {M}.basket_trades
WHERE basket_id = :b AND run_type = :r
ORDER BY trade_date, trade_id
"""

UNMARKED_SQL = f"""
SELECT m.basket_id::text AS basket_id
FROM {M}.basket_master m
WHERE m.status = 'active'
  AND NOT EXISTS (SELECT 1 FROM {M}.basket_nav_daily n
                  WHERE n.basket_id = m.basket_id AND n.run_type = :r)
ORDER BY m.created_at, m.basket_id
"""


def active_baskets() -> pd.DataFrame:
    """Every ``status = 'active'`` basket, oldest first. ``initial_capital`` is a Decimal."""
    return _gdb.read_df(BASKET_SQL, coerce_float=False)


def unmarked_basket_ids(run_type: str = RUN_TYPE) -> list[str]:
    """Active baskets with no NAV row at all — what the 5-minute worker books."""
    return _gdb.read_df(UNMARKED_SQL, {"r": run_type})["basket_id"].tolist()


def constituents(basket_id: str, version: int) -> pd.DataFrame:
    """The target weights of one (basket, version) joined to the instrument's identity.
    ``target_weight_frac`` is a Decimal fraction of capital."""
    return _gdb.read_df(CONSTITUENTS_SQL, {"b": basket_id, "v": int(version)}, coerce_float=False)


def sessions(since: dt.date, until: dt.date) -> list[dt.date]:
    """The anchor calendar between two dates: every session SPY has a bar for
    (membership-by-presence, ``atlas.global_market.calendar``)."""
    df = _gdb.read_df(SESSIONS_SQL, {"anchor": gcal.CONFIG.calendar_anchor, "a": since, "b": until})
    return gcal.sessions(df["date"])


def bars(instrument_ids: list[str], since: dt.date, until: dt.date) -> pd.DataFrame:
    """``(instrument_id, date, close_adj, close_tr)`` — Decimals, ``None`` where a column is
    NULL — for the instruments over ``[since, until]``. Real prints only: a date with no row
    is a session the instrument did not trade (the engine carries its last mark forward)."""
    if not instrument_ids:
        return pd.DataFrame(columns=pd.Index(["instrument_id", "date", "close_adj", "close_tr"]))
    df = _gdb.read_df(
        BARS_SQL, {"ids": list(instrument_ids), "a": since, "b": until}, coerce_float=False
    )
    # NaN would make `is None` tests lie and Decimal arithmetic raise; None is the honest NULL.
    return df.astype(object).where(pd.notna(df), None)


def trades(basket_id: str, run_type: str = RUN_TYPE) -> pd.DataFrame:
    """Every stored trade of the book, oldest first, money as Decimal."""
    return _gdb.read_df(TRADES_SQL, {"b": basket_id, "r": run_type}, coerce_float=False)


def open_positions(trade_rows: pd.DataFrame) -> dict[str, Decimal]:
    """``{instrument_id: net qty}`` derived from the trades (no positions table — as India)."""
    out: dict[str, Decimal] = {}
    for r in trade_rows.to_dict("records"):
        q = Decimal(str(r["qty"]))
        out[r["instrument_id"]] = out.get(r["instrument_id"], Decimal(0)) + (
            q if r["side"] == "buy" else -q
        )
    return {k: q for k, q in out.items() if q != 0}


def cash_from_trades(initial_capital: Decimal, trade_rows: pd.DataFrame) -> Decimal:
    """capital − Σ(buy value + cost) + Σ(sell value − cost): the book's cash, stateless
    (India's ``_slice_cash``), so no stored cash ever has to be trusted or repaired."""
    cash = Decimal(initial_capital)
    for r in trade_rows.to_dict("records"):
        value = Decimal(str(r["value"]))
        cost = Decimal(str(r["cost"])) if r["cost"] is not None else Decimal(0)
        cash += (value - cost) if r["side"] == "sell" else -(value + cost)
    return cash


def last_nav_date(basket_id: str, run_type: str = RUN_TYPE) -> dt.date | None:
    return _gdb.scalar(
        f"SELECT max(date) FROM {M}.basket_nav_daily WHERE basket_id = :b AND run_type = :r",
        {"b": basket_id, "r": run_type},
    )


def thresholds() -> dict[str, Decimal]:
    """The active ``atlas_thresholds`` rows, with the M2 keys asserted present."""
    th = load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())
    missing = [k for k in THRESHOLD_KEYS if k not in th]
    if missing:
        raise SystemExit(
            f"{M}.atlas_thresholds is missing basket key(s) {missing} — run "
            "scripts/global_market/seed_thresholds.py (FM approval first); there are no defaults"
        )
    return th
