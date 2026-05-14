from decimal import Decimal

from atlas.trading.config import PortfolioConfig


def test_defaults_are_decimal():
    cfg = PortfolioConfig()
    assert isinstance(cfg.stcg_rate, Decimal)
    assert cfg.stcg_rate == Decimal("0.20")
    assert cfg.ltcg_rate == Decimal("0.125")
    assert cfg.starting_capital == Decimal("10000000")


def test_roundtrip_json():
    cfg = PortfolioConfig(
        stcg_rate=Decimal("0.15"),
        label="test profile",
    )
    data = cfg.to_json()
    cfg2 = PortfolioConfig.from_json(data)
    assert cfg2.stcg_rate == Decimal("0.15")
    assert cfg2.starting_capital == cfg.starting_capital


def test_geography_defaults():
    cfg = PortfolioConfig()
    assert cfg.geography == "india"
    assert cfg.currency == "INR"
    assert cfg.universe == "nifty500"
