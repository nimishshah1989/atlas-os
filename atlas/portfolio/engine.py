"""Shared portfolio day-loop — the ONE accounting engine for backtest replay and
the nightly live mark. Pure (no I/O): panels in, trades + NAV series out. All
money is Decimal.

Timing contract: an event detected at the close of session `e` executes at the
close of the NEXT session in `dates` — EOD data only exists after the close, so
same-close fills would be lookahead. This makes live and backtest identical.

Slot model: slots = floor(1 / max_position_pct). When entry candidates exceed
open slots, the FM rule is hold the top names by Atlas composite (as of the
signal date); ties/missing composite rank last, deterministic by key.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import cast

import pandas as pd

_MONEY = Decimal("0.01")
_FUND_QTY = Decimal("0.001")  # MF units trade in fractions; stocks/ETFs whole units


@dataclass(frozen=True)
class PortfolioConfig:
    portfolio_id: str
    kind: str  # 'strategy' | 'basket'
    initial_capital: Decimal
    max_position_pct: Decimal


def _qty_for(alloc: Decimal, price: Decimal, asset_class: str) -> Decimal:
    q = alloc / price
    if asset_class == "fund":
        return q.quantize(_FUND_QTY, rounding=ROUND_DOWN)
    return q.to_integral_value(rounding=ROUND_DOWN)


def replay(
    cfg: PortfolioConfig,
    prices: pd.DataFrame,
    events: pd.DataFrame | None,
    inception_state: pd.Series | None,
    composite: pd.DataFrame | None,
    asset_class: dict[str, str],
    symbols: dict[str, str],
    start_positions: dict[str, Decimal] | None = None,
    start_cash: Decimal | None = None,
    loop_dates: list | None = None,
    costs: dict[str, tuple[Decimal, Decimal]] | None = None,
    exit_load: tuple[Decimal, int] | None = None,
    start_entry_dates: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the day-loop over `loop_dates` (default: all of `prices.index`).
    Pass the FULL price panel even when looping few dates — valuation carry-forward
    and inception price-lookback both need the history before the first loop date.

    prices     — date-indexed frame (real trading sessions), one Decimal column per
                 instrument_key; NaN where the instrument had no print that session.
                 Trades fill ONLY at real prints; valuation carries the last known
                 price forward (suspended names keep their last close).
    events     — (instrument_key, date, event) from a strategy; empty for baskets.
    inception_state — bool per instrument_key: seed holdings at dates[0] (FM basket
                 picks only — strategy portfolios start all-cash and enter on events).
    composite  — (instrument_key, date, composite) for candidate ranking, or None.
    start_positions/start_cash — resume state for the nightly increment.
    costs      — {asset_class: (buy_rate, sell_rate)} execution-cost fractions;
                 cost = value × rate, deducted from cash on BOTH sides (real
                 outflows — STT/stamp/txn/GST). Sizing reserves for the buy cost.

    Returns (trades, navs): trades (trade_date, asset_class, instrument_key,
    symbol, side, qty, price, value, reason), navs (date, nav, cash, invested,
    n_positions).
    """
    dates = list(loop_dates) if loop_dates is not None else list(prices.index)
    if not dates:
        return _empty_trades(), _empty_navs()
    marks = prices.ffill()  # valuation only — a suspended name is worth its last close

    comp_panel = None
    if composite is not None and not composite.empty:
        comp_panel = composite.pivot(index="date", columns="instrument_key", values="composite")
        comp_panel = comp_panel.sort_index().ffill()

    # Map each event to its execution date: first trading date AFTER the event.
    entries_at: dict[object, list[tuple[str, object]]] = {}
    exits_at: dict[object, list[str]] = {}
    if events is not None and not events.empty:
        date_idx = pd.Index(dates)
        for ev in events.to_dict("records"):
            pos = int(date_idx.searchsorted(ev["date"], side="right"))
            if pos >= len(dates):
                continue  # signal at the last close — executes on a future run
            d = dates[pos]
            if ev["event"] == "entry":
                entries_at.setdefault(d, []).append((ev["instrument_key"], ev["date"]))
            else:
                exits_at.setdefault(d, []).append(ev["instrument_key"])

    positions: dict[str, Decimal] = dict(start_positions or {})
    entry_date: dict = dict(start_entry_dates or {})  # k -> buy date, for exit load
    cash = start_cash if start_cash is not None else Decimal(cfg.initial_capital)
    slots = int(Decimal(1) / Decimal(cfg.max_position_pct))
    trades: list[dict] = []
    navs: list[dict] = []

    def _px(d, k):
        """Real print at d, or None — trades never fill at a carried-forward price.
        ponytail: an exit whose instrument never prints again (delisting) stays
        held at its last close; add a delisting sweep if that ever bites."""
        v = prices.at[d, k] if k in prices.columns else None
        return None if v is None or pd.isna(v) else Decimal(v)

    def _fill(d, k, lookback: bool):
        """(price, trade_date) for a fill at d. Inception fills may look back to the
        instrument's own LAST real print (e.g. fund NAV lags stock EOD by a session)
        — FM rule: inception captures the last available price. Signal fills never
        look back."""
        p = _px(d, k)
        if p is not None:
            return p, d
        if not lookback or k not in prices.columns:
            return None
        s = prices.loc[:d, k].dropna()
        return (Decimal(s.iloc[-1]), s.index[-1]) if len(s) else None

    def _mark(d) -> Decimal:
        def val(k):
            v = marks.at[d, k] if k in marks.columns else None
            return Decimal(0) if v is None or pd.isna(v) else Decimal(v)

        return sum((q * val(k) for k, q in positions.items()), Decimal(0))

    def _rate(k, side) -> Decimal:
        pair = (costs or {}).get(asset_class.get(k, "stock"))
        return Decimal(0) if pair is None else Decimal(pair[0 if side == "buy" else 1])

    def _exit_load(k, d, value) -> Decimal:
        """MF redemption load: charged when a fund lot is sold within the load
        window. Deducted from proceeds AND folded into the trade cost, so the
        FIFO capital-gains basis nets it (a transfer expense)."""
        if exit_load is None or asset_class.get(k) != "fund":
            return Decimal(0)
        ed = entry_date.get(k)
        if ed is None or (d - ed).days >= exit_load[1]:
            return Decimal(0)
        return (value * exit_load[0]).quantize(_MONEY)

    def _book(trade_date, k, side, qty, price, reason, extra_cost=Decimal(0)):
        nonlocal cash
        value = (qty * price).quantize(_MONEY)
        cost = (value * _rate(k, side)).quantize(_MONEY) + extra_cost
        cash = cash - value - cost if side == "buy" else cash + value - cost
        trades.append(
            {
                "trade_date": trade_date,
                "asset_class": asset_class.get(k, "stock"),
                "instrument_key": k,
                "symbol": symbols.get(k, k),
                "side": side,
                "qty": qty,
                "price": price,
                "value": value,
                "cost": cost,
                "reason": reason,
            }
        )

    def _enter(d, candidates: list[tuple[str, object]], reason: str):
        lookback = reason == "inception"
        seen_c: set[str] = set()
        cands = []
        for k, sig in candidates:
            if k in positions or k in seen_c:
                continue  # dedup: never book the same name twice in one execution
            fill = _fill(d, k, lookback)
            if fill is not None:
                seen_c.add(k)
                cands.append((k, sig, fill))
        open_slots = slots - len(positions)
        if open_slots <= 0 or not cands:
            return
        # ALWAYS sort (composite desc, key): same-day sizing divides remaining cash
        # in candidate order, so arrival order (SQL scan order) must never matter —
        # replays have to be bit-reproducible run to run
        cands.sort(key=lambda c: (-_comp(c[0], c[1]), c[0]))
        cands = cands[:open_slots]
        nav_now = cash + _mark(d)
        remaining = len(cands)
        for k, _sig, (price, trade_date) in cands:
            alloc = min(nav_now * Decimal(cfg.max_position_pct), cash / remaining)
            remaining -= 1
            # reserve for the buy-side execution cost so cash never goes negative
            qty = _qty_for(alloc / (1 + _rate(k, "buy")), price, asset_class.get(k, "stock"))
            if qty > 0:
                _book(trade_date, k, "buy", qty, price, reason)
                positions[k] = qty
                entry_date[k] = trade_date

    def _comp(k, sig_date) -> float:
        if comp_panel is None or k not in comp_panel.columns:
            return float("-inf")
        v = cast("float | None", comp_panel[k].asof(sig_date))
        return float("-inf") if v is None or pd.isna(v) else float(v)

    pending_exits: set[str] = set()  # exits whose execution day had no real print
    for i, d in enumerate(dates):
        if i == 0 and not positions and inception_state is not None:
            picks: list[tuple[str, object]] = [(str(k), d) for k, v in inception_state.items() if v]
            _enter(d, picks, "inception")
        else:
            # today's exit signals + any carried forward from a no-print day
            for k in list(pending_exits) + exits_at.get(d, []):
                if k not in positions:
                    pending_exits.discard(k)
                    continue
                price = _px(d, k)
                if not price:  # suspended / no print — retry next session, don't drop
                    pending_exits.add(k)
                    continue
                qty = positions.pop(k)
                el = _exit_load(k, d, (qty * price).quantize(_MONEY))
                _book(d, k, "sell", qty, price, "signal", extra_cost=el)
                entry_date.pop(k, None)
                pending_exits.discard(k)
            _enter(d, entries_at.get(d, []), "signal")

        invested = _mark(d).quantize(_MONEY)
        navs.append(
            {
                "date": d,
                "nav": (cash + invested).quantize(_MONEY),
                "cash": cash.quantize(_MONEY),
                "invested": invested,
                "n_positions": len(positions),
            }
        )

    return (
        pd.DataFrame(trades) if trades else _empty_trades(),
        pd.DataFrame(navs) if navs else _empty_navs(),
    )


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(
        columns=pd.Index(
            [
                "trade_date",
                "asset_class",
                "instrument_key",
                "symbol",
                "side",
                "qty",
                "price",
                "value",
                "cost",
                "reason",
            ]
        )
    )


def _empty_navs() -> pd.DataFrame:
    return pd.DataFrame(columns=pd.Index(["date", "nav", "cash", "invested", "n_positions"]))
