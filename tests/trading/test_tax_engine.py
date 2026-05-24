from datetime import date
from decimal import Decimal

import pytest

from atlas.trading.config import PortfolioConfig
from atlas.trading.tax_engine import TaxLedger, accrue_liquidbees, compute_trade_net_pnl


@pytest.fixture
def cfg():
    return PortfolioConfig()


@pytest.fixture
def ledger():
    return TaxLedger(financial_year=2025)


def test_stcg_trade(cfg, ledger):
    net = compute_trade_net_pnl(
        entry_price=Decimal("100"),
        exit_price=Decimal("120"),
        shares=Decimal("100"),
        entry_date=date(2024, 6, 1),
        exit_date=date(2024, 9, 1),  # 92 days < 365 → STCG
        config=cfg,
        ledger=ledger,
    )
    gross = (Decimal("120") - Decimal("100")) * Decimal("100")  # 2000
    tax = gross * cfg.stcg_rate  # 400
    entry_val = Decimal("100") * Decimal("100")
    exit_val = Decimal("120") * Decimal("100")
    brokerage = (entry_val + exit_val) * cfg.brokerage_rate
    stt = exit_val * cfg.stt_rate_sell
    exchange = (entry_val + exit_val) * (cfg.exchange_charge_rate + cfg.sebi_charge_rate)
    assert net < gross  # tax + costs reduce it
    assert net == gross - tax - brokerage - stt - exchange


def test_ltcg_trade_with_exemption(cfg, ledger):
    ledger.ltcg_exemption_remaining = Decimal("125000")
    _ = compute_trade_net_pnl(
        entry_price=Decimal("100"),
        exit_price=Decimal("150"),
        shares=Decimal("1000"),  # gross_pnl = 50,000
        entry_date=date(2023, 1, 1),
        exit_date=date(2024, 2, 1),  # 397 days ≥ 365 → LTCG
        config=cfg,
        ledger=ledger,
    )
    # gross_pnl = 50,000; exemption = 125,000 → taxable = 0 → no LTCG tax
    # exemption remaining after: 125,000 - 50,000 = 75,000
    assert ledger.ltcg_exemption_remaining == Decimal("75000")


def test_ltcg_trade_partial_exemption(cfg, ledger):
    ledger.ltcg_exemption_remaining = Decimal("50000")
    _ = compute_trade_net_pnl(
        entry_price=Decimal("100"),
        exit_price=Decimal("200"),
        shares=Decimal("1000"),  # gross_pnl = 100,000
        entry_date=date(2023, 1, 1),
        exit_date=date(2024, 2, 1),
        config=cfg,
        ledger=ledger,
    )
    # taxable = 100,000 - 50,000 = 50,000; tax = 50,000 * 0.125 = 6,250
    # exemption remaining = 0
    assert ledger.ltcg_exemption_remaining == Decimal("0")


def test_ltcg_loss_no_tax(cfg, ledger):
    net = compute_trade_net_pnl(
        entry_price=Decimal("200"),
        exit_price=Decimal("150"),
        shares=Decimal("100"),  # gross_pnl = -5000 (loss)
        entry_date=date(2023, 1, 1),
        exit_date=date(2024, 2, 1),
        config=cfg,
        ledger=ledger,
    )
    gross_pnl = (Decimal("150") - Decimal("200")) * Decimal("100")
    entry_val = Decimal("200") * Decimal("100")
    exit_val = Decimal("150") * Decimal("100")
    brokerage = (entry_val + exit_val) * cfg.brokerage_rate
    stt = exit_val * cfg.stt_rate_sell
    exchange = (entry_val + exit_val) * (cfg.exchange_charge_rate + cfg.sebi_charge_rate)
    total_costs = brokerage + stt + exchange
    # No tax on losses — net must equal gross_pnl minus costs only
    assert net == gross_pnl - total_costs


def test_liquidbees_accrual(cfg):
    idle = Decimal("1000000")  # ₹10L
    daily_net = accrue_liquidbees(idle, 1, cfg)
    # Exact Decimal computation matching the implementation
    expected_gross = idle * cfg.liquidbees_annual_yield / Decimal("365") * Decimal("1")
    expected_net = expected_gross * (Decimal("1") - cfg.income_tax_slab_rate)
    assert daily_net == expected_net
