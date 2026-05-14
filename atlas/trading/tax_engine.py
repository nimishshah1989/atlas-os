"""After-tax, after-cost P&L computation for the Atlas Strategy Lab.

All arithmetic uses Decimal — never float. Financial year is April–March (India).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from atlas.trading.config import PortfolioConfig


@dataclass
class TaxLedger:
    """Tracks LTCG exemption per financial year, per strategy genome."""

    # starting year (e.g. 2024 for FY2024-25)
    financial_year: int
    ltcg_exemption_remaining: Decimal = Decimal("125000")  # resets each April 1

    def reset_for_new_fy(self, new_fy: int, config: PortfolioConfig) -> None:
        self.financial_year = new_fy
        self.ltcg_exemption_remaining = config.ltcg_annual_exemption


def _financial_year(d: date) -> int:
    """Return the starting year of the Indian financial year containing date d."""
    return d.year if d.month >= 4 else d.year - 1


def compute_trade_net_pnl(
    entry_price: Decimal,
    exit_price: Decimal,
    shares: Decimal,
    entry_date: date,
    exit_date: date,
    config: PortfolioConfig,
    ledger: TaxLedger,
) -> Decimal:
    """Return after-tax, after-cost net P&L for one completed trade.

    Mutates ledger.ltcg_exemption_remaining if LTCG applies.
    Handles financial year rollover automatically.
    """
    entry_value = entry_price * shares
    exit_value = exit_price * shares
    gross_pnl = (exit_price - entry_price) * shares

    # Transaction costs
    brokerage = (entry_value + exit_value) * config.brokerage_rate
    stt = exit_value * config.stt_rate_sell
    combined_rate = config.exchange_charge_rate + config.sebi_charge_rate
    exchange_fees = (entry_value + exit_value) * combined_rate
    total_costs = brokerage + stt + exchange_fees

    # Tax
    holding_days = (exit_date - entry_date).days

    # Ensure ledger is for the correct financial year.
    # Only roll forward — a rollback (exit_fy < ledger.financial_year) means
    # the caller pre-populated an isolated ledger for a specific FY; honour it.
    exit_fy = _financial_year(exit_date)
    if exit_fy > ledger.financial_year:
        ledger.reset_for_new_fy(exit_fy, config)

    if gross_pnl <= Decimal("0"):
        tax = Decimal("0")
    elif holding_days < 365:
        tax = gross_pnl * config.stcg_rate
    else:
        # LTCG: apply annual exemption first
        exempt_amount = min(gross_pnl, ledger.ltcg_exemption_remaining)
        taxable = gross_pnl - exempt_amount
        tax = taxable * config.ltcg_rate
        ledger.ltcg_exemption_remaining -= exempt_amount

    return gross_pnl - total_costs - tax


def accrue_liquidbees(idle_cash: Decimal, days: int, config: PortfolioConfig) -> Decimal:
    """Net daily LiquidBees income after income tax.

    LiquidBees yield is taxed at income_tax_slab_rate (not STCG/LTCG).
    """
    daily_gross = idle_cash * config.liquidbees_annual_yield / Decimal("365") * Decimal(str(days))
    daily_tax = daily_gross * config.income_tax_slab_rate
    return daily_gross - daily_tax


def compute_portfolio_idle_cash(
    total_portfolio_value: Decimal,
    equity_positions_value: Decimal,
) -> Decimal:
    """Idle cash = total portfolio value minus all equity position market values.

    LiquidBees is NOT equity — it is always the complement of equity.
    Heat cap (max_portfolio_heat_pct) applies to equity_positions_value only.
    """
    return total_portfolio_value - equity_positions_value
