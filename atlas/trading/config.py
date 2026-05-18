from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal
from typing import Any


@dataclass
class PortfolioConfig:
    """User-level portfolio configuration. All values act as hard ceilings on genome proposals.

    All financial values are Decimal to prevent floating-point precision errors.
    This configuration is immutable at runtime; changes require a database update
    followed by the next nightly run picking up the new config.
    """

    # Capital
    starting_capital: Decimal = Decimal("10000000")  # ₹1 crore

    # Indian equity tax (post Budget 2024 defaults)
    stcg_rate: Decimal = Decimal("0.20")
    ltcg_rate: Decimal = Decimal("0.125")
    ltcg_annual_exemption: Decimal = Decimal("125000")  # ₹1.25L per FY
    income_tax_slab_rate: Decimal = Decimal("0.30")  # LiquidBees income

    # Cash equivalent
    liquidbees_annual_yield: Decimal = Decimal("0.067")
    liquidbees_ticker: str = "LIQUIDBEES"

    # Transaction costs (Zerodha delivery defaults)
    brokerage_rate: Decimal = Decimal("0.005")
    stt_rate_sell: Decimal = Decimal("0.001")
    exchange_charge_rate: Decimal = Decimal("0.000325")
    sebi_charge_rate: Decimal = Decimal("0.000001")

    # Hard risk limits (PortfolioConfig is the hard ceiling; genome proposes within these)
    max_position_pct: Decimal = Decimal("0.05")
    max_portfolio_heat_pct: Decimal = Decimal("0.20")
    drawdown_circuit_breaker_pct: Decimal = Decimal("0.25")

    # Universe
    universe: str = "nifty500"
    rebalancing_frequency: str = "weekly"

    # Geography (for future IBKR extension)
    geography: str = "india"
    currency: str = "INR"

    # Internal label — not used in computation
    label: str = ""

    _DECIMAL_FIELDS: set[str] = field(default_factory=set, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Initialize the set of decimal field names for later serialization."""
        _str_fields = {
            "universe",
            "rebalancing_frequency",
            "geography",
            "currency",
            "label",
            "liquidbees_ticker",
            "_DECIMAL_FIELDS",
        }
        self._DECIMAL_FIELDS = {f.name for f in fields(self) if f.name not in _str_fields}

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict. Decimal fields become strings."""
        result = {}
        for f in fields(self):
            if f.name.startswith("_"):
                continue
            v = getattr(self, f.name)
            result[f.name] = str(v) if isinstance(v, Decimal) else v
        return result

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PortfolioConfig:
        """Deserialize from JSON dict. String numbers are converted to Decimal."""
        _str_fields = {
            "universe",
            "rebalancing_frequency",
            "geography",
            "currency",
            "label",
            "liquidbees_ticker",
        }
        kwargs: dict[str, Any] = {}
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if k not in _str_fields and v is not None:
                kwargs[k] = Decimal(str(v))
            else:
                kwargs[k] = v
        return cls(**kwargs)
