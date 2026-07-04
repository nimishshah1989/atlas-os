"""FIFO capital-gains ledger for portfolio trades — Indian equity/equity-MF rules.

Pure (no I/O). Basis includes buy-side execution cost; sale proceeds are net of
sell-side cost (transfer expenses are deductible). Holding-period buckets:
STCG below `ltcg_days`, LTCG at/above. The LTCG exemption is applied per Indian
financial year (Apr–Mar), in chronological order, PER PORTFOLIO — the real
exemption is per taxpayer across all holdings (documented approximation).

Row-level `tax` is provisional (this gain in isolation, exemption applied in
sequence). `summarize()` is the honest year-end figure: per-FY netting with
set-off (ST losses offset LT gains; LT losses only LT; no loss carry-forward —
ponytail: add carry-forward if multi-year backtests need it).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

_MONEY = Decimal("0.01")


@dataclass(frozen=True)
class TaxRates:
    stcg: Decimal
    ltcg: Decimal
    ltcg_exemption: Decimal
    ltcg_days: int


def indian_fy(d) -> str:
    """'FY25-26' for dates in Apr 2025 – Mar 2026."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"FY{start % 100:02d}-{(start + 1) % 100:02d}"


def enrich_trades(trades: pd.DataFrame, rates: TaxRates) -> pd.DataFrame:
    """Return a copy with realized_pnl / holding_days / tax_bucket / tax filled on
    sells (plus realized_st / realized_lt split for summarize()); buys get NULLs.
    `trades` must be one portfolio+run_type, chronological (booking order)."""
    out = trades.reset_index(drop=True).copy()
    for col in ("realized_pnl", "holding_days", "tax_bucket", "tax", "realized_st", "realized_lt"):
        out[col] = None
    lots: dict[str, deque] = {}  # key -> deque[(buy_date, qty, unit_basis)]
    exemption_left: dict[str, Decimal] = {}

    for i, r in enumerate(out.to_dict("records")):
        k, qty = r["instrument_key"], Decimal(r["qty"])
        cost = Decimal(r["cost"] or 0)
        if r["side"] == "buy":
            unit_basis = (Decimal(r["value"]) + cost) / qty
            lots.setdefault(k, deque()).append((r["trade_date"], qty, unit_basis))
            continue

        net_per_unit = (Decimal(r["value"]) - cost) / qty
        st: Decimal = Decimal(0)
        lt: Decimal = Decimal(0)
        remaining, oldest = qty, None
        q = lots.get(k, deque())
        while remaining > 0 and q:
            b_date, b_qty, b_basis = q[0]
            take = min(remaining, b_qty)
            gain = (net_per_unit - b_basis) * take
            days = (r["trade_date"] - b_date).days
            oldest = b_date if oldest is None else min(oldest, b_date)
            if days >= rates.ltcg_days:
                lt += gain
            else:
                st += gain
            if take == b_qty:
                q.popleft()
            else:
                q[0] = (b_date, b_qty - take, b_basis)
            remaining -= take

        fy = indian_fy(r["trade_date"])
        ex = exemption_left.setdefault(fy, Decimal(rates.ltcg_exemption))
        used = min(ex, lt) if lt > 0 else Decimal(0)
        exemption_left[fy] = ex - used
        tax = (max(st, Decimal(0)) * rates.stcg + max(lt - used, Decimal(0)) * rates.ltcg).quantize(
            _MONEY
        )

        bucket = "mixed" if (st != 0 and lt != 0) else ("ltcg" if lt != 0 else "stcg")
        days_held = (r["trade_date"] - oldest).days if oldest is not None else None
        out.loc[i, ["realized_pnl", "holding_days", "tax_bucket", "tax"]] = [
            (st + lt).quantize(_MONEY),
            days_held,
            bucket,
            tax,
        ]
        out.loc[i, ["realized_st", "realized_lt"]] = [st.quantize(_MONEY), lt.quantize(_MONEY)]
    return out


def summarize(enriched: pd.DataFrame, rates: TaxRates) -> dict:
    """Year-end view: per-FY ST/LT netting with set-off + exemption → tax_total."""
    sells = enriched.loc[enriched["side"] == "sell"]
    by_fy: dict[str, dict] = {}
    for r in sells.to_dict("records"):
        fy = indian_fy(r["trade_date"])
        agg = by_fy.setdefault(fy, {"st_net": Decimal(0), "lt_net": Decimal(0)})
        agg["st_net"] += Decimal(r["realized_st"] or 0)
        agg["lt_net"] += Decimal(r["realized_lt"] or 0)

    tax_total = Decimal(0)
    for agg in by_fy.values():
        st, lt = agg["st_net"], agg["lt_net"]
        if st < 0 and lt > 0:  # ST loss sets off LT gains
            lt, st = lt + st, Decimal(0)
        lt_taxable = max(lt - Decimal(rates.ltcg_exemption), Decimal(0))
        agg["tax"] = (max(st, Decimal(0)) * rates.stcg + lt_taxable * rates.ltcg).quantize(_MONEY)
        tax_total += agg["tax"]
    return {
        "realized_st": sum((f["st_net"] for f in by_fy.values()), Decimal(0)),
        "realized_lt": sum((f["lt_net"] for f in by_fy.values()), Decimal(0)),
        "tax_total": tax_total,
        "by_fy": by_fy,
    }
