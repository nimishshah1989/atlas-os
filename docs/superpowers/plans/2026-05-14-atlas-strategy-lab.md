# Atlas Strategy Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Atlas Strategy Lab — a nightly evolutionary engine that runs 100–150 strategy genomes in parallel on India's Nifty 500, jointly optimizing Layer 1 perception thresholds and Layer 2 decision rules to surface top 3–5 after-tax, after-cost Sortino-optimal strategies as actionable replication guides.

**Architecture:** New bounded context `atlas/trading/` reads raw metrics from Postgres, applies per-genome Layer 1 thresholds in-memory via numpy, runs vectorbt portfolio simulations, and uses Optuna TPE + DEAP genetic algorithms to evolve the gene pool nightly. Groq Llama narrates results in plain English. Frontend: 3-layer progressive disclosure at `/strategies/lab/`.

**Tech Stack:** Python (vectorbt, optuna[postgres], deap, numpy, structlog), FastAPI, PostgreSQL, Next.js 15, Recharts, Tailwind

**Spec:** `docs/superpowers/specs/2026-05-14-atlas-strategy-lab-design.md`

---

## File Map

```
atlas/trading/__init__.py
atlas/trading/config.py          # PortfolioConfig dataclass
atlas/trading/genome.py          # Genome dataclasses + Optuna search space
atlas/trading/universe.py        # Point-in-time universe loader
atlas/trading/perception.py      # Layer 1: raw metrics → numpy state matrices
atlas/trading/tax_engine.py      # Per-trade net P&L + LTCG exemption + LiquidBees
atlas/trading/decision.py        # Layer 2: conviction score + entry/exit signals
atlas/trading/simulator.py       # vectorbt harness: one genome → SimResult
atlas/trading/optimizer.py       # Optuna study management
atlas/trading/evolver.py         # DEAP crossover + mutation
atlas/trading/tournament.py      # 3-round promotion + leaderboard writes
atlas/trading/insight.py         # Groq narration
atlas/trading/incubator.py       # Nightly orchestrator

migrations/versions/065_atlas_strategy_lab.py

atlas/api/trading.py             # Read-only FastAPI endpoints

frontend/src/app/strategies/lab/page.tsx
frontend/src/app/strategies/lab/[id]/page.tsx
frontend/src/app/strategies/lab/engine/page.tsx
frontend/src/lib/queries/strategy_lab.ts
frontend/src/components/trading/MorningBrief.tsx
frontend/src/components/trading/StrategyLeaderboard.tsx
frontend/src/components/trading/GenomeRadarChart.tsx
frontend/src/components/trading/EquityCurveChart.tsx
frontend/src/components/trading/WalkForwardChart.tsx
frontend/src/components/trading/ReplicationGuide.tsx
frontend/src/components/trading/TaxHarvestingAlert.tsx
frontend/src/components/trading/EngineRoom.tsx
frontend/src/components/trading/StrategyConfigurator.tsx

tests/trading/__init__.py
tests/trading/test_config.py
tests/trading/test_genome.py
tests/trading/test_perception.py
tests/trading/test_tax_engine.py
tests/trading/test_decision.py
tests/trading/test_simulator.py
tests/trading/test_optimizer.py
tests/trading/test_tournament.py
```

---

## Task 1: Dependencies + DB Migration (7 tables)

**Files:**
- Modify: `pyproject.toml`
- Create: `migrations/versions/065_atlas_strategy_lab.py`

- [ ] **Step 1: Add `deap` to pyproject.toml**

In `pyproject.toml`, find the `dependencies` array and add after the `optuna` line:
```toml
    "deap>=1.4",
```

- [ ] **Step 2: Write migration**

Create `migrations/versions/065_atlas_strategy_lab.py`:

```python
"""Atlas Strategy Lab — 7 new tables for genome-based portfolio simulation.

Revision ID: 065
Revises: 064
Create Date: 2026-05-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "atlas_strategy_genomes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("parent_ids", ARRAY(UUID(as_uuid=True)), nullable=True),
        sa.Column("genome_json", JSONB, nullable=False),
        sa.Column("born_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("kill_reason", sa.Text, nullable=True),
        sa.Column("generation", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("status IN ('active','promoted','killed','archived')", name="ck_genomes_status"),
    )

    op.create_table(
        "atlas_strategy_performance_daily",
        sa.Column("genome_id", UUID(as_uuid=True), sa.ForeignKey("atlas_strategy_genomes.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("sortino_insample", sa.Numeric(10, 4), nullable=True),
        sa.Column("sortino_oos", sa.Numeric(10, 4), nullable=True),
        sa.Column("calmar_oos", sa.Numeric(10, 4), nullable=True),
        sa.Column("alpha_vs_nifty500", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(10, 4), nullable=True),
        sa.Column("portfolio_heat", sa.Numeric(10, 4), nullable=True),
        sa.Column("ltcg_exemption_used", sa.Numeric(20, 4), nullable=True),
        sa.Column("total_trades", sa.Integer, nullable=True),
        sa.Column("turnover_pct", sa.Numeric(10, 4), nullable=True),
        sa.PrimaryKeyConstraint("genome_id", "date"),
    )

    op.create_table(
        "atlas_strategy_positions_daily",
        sa.Column("genome_id", UUID(as_uuid=True), sa.ForeignKey("atlas_strategy_genomes.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("instrument_id", sa.Integer, sa.ForeignKey("atlas_instruments.id"), nullable=False),
        sa.Column("position_type", sa.Text, nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("shares", sa.Numeric(20, 4), nullable=False),
        sa.Column("current_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(20, 4), nullable=False),
        sa.Column("holding_days", sa.Integer, nullable=False),
        sa.Column("tax_status", sa.Text, nullable=False),
        sa.Column("entry_signals", JSONB, nullable=True),
        sa.PrimaryKeyConstraint("genome_id", "date", "instrument_id"),
        sa.CheckConstraint("position_type IN ('equity','liquidbees')", name="ck_positions_type"),
        sa.CheckConstraint("tax_status IN ('stcg','ltcg_eligible','liquidbees')", name="ck_positions_tax"),
    )

    op.create_table(
        "atlas_strategy_leaderboard",
        sa.Column("rank", sa.Integer, primary_key=True),
        sa.Column("genome_id", UUID(as_uuid=True), sa.ForeignKey("atlas_strategy_genomes.id"), nullable=False),
        sa.Column("strategy_name", sa.Text, nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sortino_oos", sa.Numeric(10, 4), nullable=True),
        sa.Column("calmar_oos", sa.Numeric(10, 4), nullable=True),
        sa.Column("alpha_30d", sa.Numeric(10, 4), nullable=True),
        sa.Column("regime_breakdown", JSONB, nullable=True),
    )

    op.create_table(
        "atlas_strategy_insights",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("insight_bullets", JSONB, nullable=False),
        sa.Column("parameter_importance", JSONB, nullable=True),
        sa.Column("top_genome_deltas", JSONB, nullable=True),
    )

    op.create_table(
        "atlas_universe_membership_daily",
        sa.Column("instrument_id", sa.Integer, sa.ForeignKey("atlas_instruments.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("universe", sa.Text, nullable=False),
        sa.Column("was_member", sa.Boolean, nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("instrument_id", "date", "universe"),
    )
    op.create_index("ix_universe_membership_date_universe", "atlas_universe_membership_daily", ["date", "universe"])

    op.create_table(
        "atlas_strategy_evolution_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("genome_id", UUID(as_uuid=True), sa.ForeignKey("atlas_strategy_genomes.id"), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("parent_ids", ARRAY(UUID(as_uuid=True)), nullable=True),
        sa.Column("final_sortino", sa.Numeric(10, 4), nullable=True),
        sa.Column("final_calmar", sa.Numeric(10, 4), nullable=True),
        sa.Column("kill_reason", sa.Text, nullable=True),
        sa.Column("generation", sa.Integer, nullable=True),
        sa.Column("parameter_delta", JSONB, nullable=True),
        sa.CheckConstraint(
            "event_type IN ('born','killed','promoted','demoted','mutated','crossover')",
            name="ck_evolution_event_type",
        ),
    )

    op.create_table(
        "atlas_portfolio_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("config_json", JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("label", sa.Text, nullable=True),
    )


def downgrade() -> None:
    for table in [
        "atlas_portfolio_config",
        "atlas_strategy_evolution_log",
        "atlas_universe_membership_daily",
        "atlas_strategy_insights",
        "atlas_strategy_leaderboard",
        "atlas_strategy_positions_daily",
        "atlas_strategy_performance_daily",
        "atlas_strategy_genomes",
    ]:
        op.drop_table(table)
```

- [ ] **Step 3: Run migration locally**

```bash
alembic upgrade 065
```

Expected: `Running upgrade 064 -> 065, Atlas Strategy Lab — 7 new tables`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml migrations/versions/065_atlas_strategy_lab.py
git commit -m "feat(trading): add deap dep + migration 065 for Strategy Lab tables"
```

---

## Task 2: PortfolioConfig

**Files:**
- Create: `atlas/trading/__init__.py`
- Create: `atlas/trading/config.py`
- Create: `tests/trading/__init__.py`
- Create: `tests/trading/test_config.py`

- [ ] **Step 1: Write failing test**

`tests/trading/test_config.py`:
```python
from decimal import Decimal
import pytest
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
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/trading/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading'`

- [ ] **Step 3: Implement**

`atlas/trading/__init__.py`:
```python
"""Atlas Strategy Lab — genome-based two-layer portfolio simulation engine.

Bounded context: reads only from DB (shared kernel). No imports from
atlas.compute.*, atlas.simulation.*, or atlas.intelligence.*.
"""
```

`atlas/trading/config.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal
from typing import Any


@dataclass
class PortfolioConfig:
    # Capital
    starting_capital: Decimal = Decimal("10000000")  # ₹1 crore

    # Indian equity tax (post Budget 2024 defaults)
    stcg_rate: Decimal = Decimal("0.20")
    ltcg_rate: Decimal = Decimal("0.125")
    ltcg_annual_exemption: Decimal = Decimal("125000")  # ₹1.25L per FY
    income_tax_slab_rate: Decimal = Decimal("0.30")     # LiquidBees income

    # Cash equivalent
    liquidbees_annual_yield: Decimal = Decimal("0.067")
    liquidbees_ticker: str = "LIQUIDBEES"

    # Transaction costs (Zerodha delivery defaults)
    brokerage_rate: Decimal = Decimal("0.005")
    stt_rate_sell: Decimal = Decimal("0.001")
    exchange_charge_rate: Decimal = Decimal("0.000325")
    sebi_charge_rate: Decimal = Decimal("0.000001")

    # Hard risk limits (not genome variables)
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
        self._DECIMAL_FIELDS = {
            f.name for f in fields(self)
            if f.name not in ("universe", "rebalancing_frequency", "geography", "currency", "label", "_DECIMAL_FIELDS")
        }

    def to_json(self) -> dict[str, Any]:
        result = {}
        for f in fields(self):
            if f.name.startswith("_"):
                continue
            v = getattr(self, f.name)
            result[f.name] = str(v) if isinstance(v, Decimal) else v
        return result

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PortfolioConfig":
        decimal_field_names = {
            f.name for f in fields(cls)
            if f.name not in ("universe", "rebalancing_frequency", "geography", "currency", "label", "_DECIMAL_FIELDS")
            and not f.name.startswith("_")
        }
        kwargs: dict[str, Any] = {}
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if k in decimal_field_names and v is not None:
                kwargs[k] = Decimal(str(v))
            else:
                kwargs[k] = v
        return cls(**kwargs)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_config.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/__init__.py atlas/trading/config.py tests/trading/__init__.py tests/trading/test_config.py
git commit -m "feat(trading): add PortfolioConfig with Decimal fields + round-trip JSON"
```

---

## Task 3: Genome Schema + Optuna Search Space

**Files:**
- Create: `atlas/trading/genome.py`
- Create: `tests/trading/test_genome.py`

- [ ] **Step 1: Write failing tests**

`tests/trading/test_genome.py`:
```python
import pytest
from atlas.trading.genome import (
    Genome, GenomeFactory, LAYER1_SEARCH_SPACE, REGIME_SEARCH_SPACE
)


def test_random_genome_is_valid():
    g = GenomeFactory.random()
    assert 60 <= g.layer1.rs_leader_cutoff_pct <= 80
    assert g.layer1.rs_leader_cutoff_pct > g.layer1.rs_strong_cutoff_pct
    weights = g.layer1.rs_timeframe_weights
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert 2.0 <= g.risk_on.base_position_pct <= 6.0


def test_genome_json_roundtrip():
    g = GenomeFactory.random()
    data = g.to_dict()
    g2 = Genome.from_dict(data)
    assert g2.genome_id == g.genome_id
    assert g2.layer1.rs_leader_cutoff_pct == g.layer1.rs_leader_cutoff_pct
    assert g2.risk_on.min_conviction_to_enter == g.risk_on.min_conviction_to_enter


def test_optuna_trial_produces_valid_genome():
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")

    def _obj(trial):
        g = GenomeFactory.from_optuna_trial(trial)
        assert 60 <= g.layer1.rs_leader_cutoff_pct <= 80
        return 0.5

    study.optimize(_obj, n_trials=3)
    assert study.best_value == 0.5
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_genome.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading.genome'`

- [ ] **Step 3: Implement**

`atlas/trading/genome.py`:
```python
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Search space definitions (Optuna ranges)
# ---------------------------------------------------------------------------

LAYER1_SEARCH_SPACE: dict[str, tuple] = {
    "rs_leader_cutoff_pct":           ("int",   60,  80),
    "rs_strong_cutoff_pct":           ("int",   45,  65),
    "rs_average_cutoff_pct":          ("int",   25,  45),
    "rs_weak_cutoff_pct":             ("int",   10,  25),
    "rs_w1w":                         ("float", 0.10, 0.60),
    "rs_w1m":                         ("float", 0.10, 0.50),
    "rs_w3m":                         ("float", 0.05, 0.40),
    "rs_w6m":                         ("float", 0.02, 0.25),
    "rs_w12m":                        ("float", 0.01, 0.20),
    "regime_risk_on_breadth_pct":     ("int",   50,  70),
    "regime_constructive_breadth_pct":("int",   35,  55),
    "regime_cautious_breadth_pct":    ("int",   20,  40),
    "regime_risk_on_vix_ceiling":     ("float", 14.0, 22.0),
    "momentum_accel_ema_ratio":       ("float", 1.010, 1.040),
    "momentum_decel_ema_ratio":       ("float", 0.975, 0.995),
    "vol_elevated_ratio":             ("float", 1.2, 1.8),
    "vol_high_ratio":                 ("float", 1.5, 2.5),
    "state_velocity_lookback_days":   ("int",   5,   20),
    "synergy_weight":                 ("float", 0.0, 0.3),
    "penalty_weight":                 ("float", 0.0, 0.3),
}

REGIME_SEARCH_SPACE: dict[str, tuple] = {
    "min_conviction_to_enter": ("float", 0.35, 0.80),
    "base_position_pct":       ("float", 2.0,  6.0),
    "exit_rs_drop_tiers":      ("int",   1,    3),
    "profit_target_pct":       ("float", 10.0, 30.0),   # None handled separately
    "time_stop_days":          ("int",   10,   45),      # None handled separately
    "trailing_stop_pct":       ("float", 5.0,  20.0),   # None handled separately
    "min_hold_days":           ("int",   3,    15),
    "max_sector_concentration_pct": ("int", 15, 35),
    "dd_halt_entry_pct":       ("float", 8.0,  15.0),
    "dd_tighten_exit_pct":     ("float", 14.0, 22.0),
    "dd_liquidate_pct":        ("float", 19.0, 30.0),
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Layer1Perception:
    rs_leader_cutoff_pct: int
    rs_strong_cutoff_pct: int
    rs_average_cutoff_pct: int
    rs_weak_cutoff_pct: int
    rs_timeframe_weights: dict[str, float]   # keys: 1w, 1m, 3m, 6m, 12m; sum=1.0
    regime_risk_on_breadth_pct: int
    regime_constructive_breadth_pct: int
    regime_cautious_breadth_pct: int
    regime_risk_on_vix_ceiling: float
    momentum_accel_ema_ratio: float
    momentum_decel_ema_ratio: float
    vol_elevated_ratio: float
    vol_high_ratio: float
    state_velocity_lookback_days: int
    synergy_weight: float
    penalty_weight: float


@dataclass
class RegimePlaybook:
    min_conviction_to_enter: float
    base_position_pct: float
    exit_rs_drop_tiers: int
    exit_momentum_collapse: bool
    profit_target_pct: float | None
    time_stop_days: int | None
    trailing_stop_from_peak_pct: float | None
    min_hold_days: int
    max_sector_concentration_pct: int
    dd_halt_entry_pct: float
    dd_tighten_exit_pct: float
    dd_liquidate_pct: float


@dataclass
class Genome:
    genome_id: str
    parent_ids: list[str]
    born_at: datetime
    generation: int
    layer1: Layer1Perception
    risk_on: RegimePlaybook
    constructive: RegimePlaybook
    cautious: RegimePlaybook

    def to_dict(self) -> dict[str, Any]:
        def _convert(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _convert(v) for k, v in asdict(obj).items()}
            return obj

        return {
            "genome_id": self.genome_id,
            "parent_ids": self.parent_ids,
            "born_at": self.born_at.isoformat(),
            "generation": self.generation,
            "layer1": asdict(self.layer1),
            "risk_on": asdict(self.risk_on),
            "constructive": asdict(self.constructive),
            "cautious": asdict(self.cautious),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Genome":
        born_at = datetime.fromisoformat(d["born_at"])
        if born_at.tzinfo is None:
            born_at = born_at.replace(tzinfo=timezone.utc)
        return cls(
            genome_id=d["genome_id"],
            parent_ids=d.get("parent_ids", []),
            born_at=born_at,
            generation=d.get("generation", 0),
            layer1=Layer1Perception(**d["layer1"]),
            risk_on=RegimePlaybook(**d["risk_on"]),
            constructive=RegimePlaybook(**d["constructive"]),
            cautious=RegimePlaybook(**d["cautious"]),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _random_weights() -> dict[str, float]:
    raw = [random.random() for _ in range(5)]
    total = sum(raw)
    vals = [v / total for v in raw]
    return {"1w": vals[0], "1m": vals[1], "3m": vals[2], "6m": vals[3], "12m": vals[4]}


def _random_playbook(has_profit_target: bool, has_time_stop: bool, has_trailing: bool) -> RegimePlaybook:
    return RegimePlaybook(
        min_conviction_to_enter=random.uniform(0.35, 0.80),
        base_position_pct=random.uniform(2.0, 6.0),
        exit_rs_drop_tiers=random.randint(1, 3),
        exit_momentum_collapse=random.random() > 0.3,
        profit_target_pct=random.uniform(10.0, 30.0) if has_profit_target else None,
        time_stop_days=random.randint(10, 45) if has_time_stop else None,
        trailing_stop_from_peak_pct=random.uniform(5.0, 20.0) if has_trailing else None,
        min_hold_days=random.randint(3, 15),
        max_sector_concentration_pct=random.randint(15, 35),
        dd_halt_entry_pct=random.uniform(8.0, 15.0),
        dd_tighten_exit_pct=random.uniform(14.0, 22.0),
        dd_liquidate_pct=random.uniform(19.0, 30.0),
    )


class GenomeFactory:
    @staticmethod
    def random() -> Genome:
        leader = random.randint(60, 80)
        strong = random.randint(45, min(65, leader - 1))
        average = random.randint(25, min(45, strong - 1))
        weak = random.randint(10, min(25, average - 1))
        layer1 = Layer1Perception(
            rs_leader_cutoff_pct=leader,
            rs_strong_cutoff_pct=strong,
            rs_average_cutoff_pct=average,
            rs_weak_cutoff_pct=weak,
            rs_timeframe_weights=_random_weights(),
            regime_risk_on_breadth_pct=random.randint(50, 70),
            regime_constructive_breadth_pct=random.randint(35, 55),
            regime_cautious_breadth_pct=random.randint(20, 40),
            regime_risk_on_vix_ceiling=random.uniform(14.0, 22.0),
            momentum_accel_ema_ratio=random.uniform(1.010, 1.040),
            momentum_decel_ema_ratio=random.uniform(0.975, 0.995),
            vol_elevated_ratio=random.uniform(1.2, 1.8),
            vol_high_ratio=random.uniform(1.5, 2.5),
            state_velocity_lookback_days=random.randint(5, 20),
            synergy_weight=random.uniform(0.0, 0.3),
            penalty_weight=random.uniform(0.0, 0.3),
        )
        return Genome(
            genome_id=str(uuid.uuid4()),
            parent_ids=[],
            born_at=datetime.now(timezone.utc),
            generation=0,
            layer1=layer1,
            risk_on=_random_playbook(False, False, False),
            constructive=_random_playbook(False, True, True),
            cautious=_random_playbook(True, True, True),
        )

    @staticmethod
    def from_optuna_trial(trial: Any) -> Genome:
        """Build a Genome from an Optuna trial using suggest_* calls."""
        leader = trial.suggest_int("rs_leader_cutoff_pct", 60, 80)
        strong = trial.suggest_int("rs_strong_cutoff_pct", 45, min(65, leader - 1))
        average = trial.suggest_int("rs_average_cutoff_pct", 25, min(45, strong - 1))
        weak = trial.suggest_int("rs_weak_cutoff_pct", 10, min(25, average - 1))

        w1 = trial.suggest_float("rs_w1w", 0.10, 0.60)
        w2 = trial.suggest_float("rs_w1m", 0.10, 0.50)
        w3 = trial.suggest_float("rs_w3m", 0.05, 0.40)
        w4 = trial.suggest_float("rs_w6m", 0.02, 0.25)
        w5 = trial.suggest_float("rs_w12m", 0.01, 0.20)
        total = w1 + w2 + w3 + w4 + w5
        weights = {"1w": w1/total, "1m": w2/total, "3m": w3/total, "6m": w4/total, "12m": w5/total}

        layer1 = Layer1Perception(
            rs_leader_cutoff_pct=leader,
            rs_strong_cutoff_pct=strong,
            rs_average_cutoff_pct=average,
            rs_weak_cutoff_pct=weak,
            rs_timeframe_weights=weights,
            regime_risk_on_breadth_pct=trial.suggest_int("regime_risk_on_breadth_pct", 50, 70),
            regime_constructive_breadth_pct=trial.suggest_int("regime_constructive_breadth_pct", 35, 55),
            regime_cautious_breadth_pct=trial.suggest_int("regime_cautious_breadth_pct", 20, 40),
            regime_risk_on_vix_ceiling=trial.suggest_float("regime_risk_on_vix_ceiling", 14.0, 22.0),
            momentum_accel_ema_ratio=trial.suggest_float("momentum_accel_ema_ratio", 1.010, 1.040),
            momentum_decel_ema_ratio=trial.suggest_float("momentum_decel_ema_ratio", 0.975, 0.995),
            vol_elevated_ratio=trial.suggest_float("vol_elevated_ratio", 1.2, 1.8),
            vol_high_ratio=trial.suggest_float("vol_high_ratio", 1.5, 2.5),
            state_velocity_lookback_days=trial.suggest_int("state_velocity_lookback_days", 5, 20),
            synergy_weight=trial.suggest_float("synergy_weight", 0.0, 0.3),
            penalty_weight=trial.suggest_float("penalty_weight", 0.0, 0.3),
        )

        def _trial_playbook(prefix: str, has_profit: bool, has_time: bool, has_trail: bool) -> RegimePlaybook:
            return RegimePlaybook(
                min_conviction_to_enter=trial.suggest_float(f"{prefix}_min_conviction", 0.35, 0.80),
                base_position_pct=trial.suggest_float(f"{prefix}_base_position_pct", 2.0, 6.0),
                exit_rs_drop_tiers=trial.suggest_int(f"{prefix}_exit_rs_drop_tiers", 1, 3),
                exit_momentum_collapse=True,
                profit_target_pct=trial.suggest_float(f"{prefix}_profit_target_pct", 10.0, 30.0) if has_profit else None,
                time_stop_days=trial.suggest_int(f"{prefix}_time_stop_days", 10, 45) if has_time else None,
                trailing_stop_from_peak_pct=trial.suggest_float(f"{prefix}_trailing_stop_pct", 5.0, 20.0) if has_trail else None,
                min_hold_days=trial.suggest_int(f"{prefix}_min_hold_days", 3, 15),
                max_sector_concentration_pct=trial.suggest_int(f"{prefix}_max_sector_pct", 15, 35),
                dd_halt_entry_pct=trial.suggest_float(f"{prefix}_dd_halt_pct", 8.0, 15.0),
                dd_tighten_exit_pct=trial.suggest_float(f"{prefix}_dd_tighten_pct", 14.0, 22.0),
                dd_liquidate_pct=trial.suggest_float(f"{prefix}_dd_liquidate_pct", 19.0, 30.0),
            )

        return Genome(
            genome_id=str(uuid.uuid4()),
            parent_ids=[],
            born_at=datetime.now(timezone.utc),
            generation=0,
            layer1=layer1,
            risk_on=_trial_playbook("ro", False, False, False),
            constructive=_trial_playbook("co", False, True, True),
            cautious=_trial_playbook("ca", True, True, True),
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_genome.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/genome.py tests/trading/test_genome.py
git commit -m "feat(trading): genome schema + Optuna search space + GenomeFactory"
```

---

## Task 4: Point-in-Time Universe Loader

**Files:**
- Create: `atlas/trading/universe.py`
- Create: `tests/trading/test_universe.py`

- [ ] **Step 1: Write failing test**

`tests/trading/test_universe.py`:
```python
from datetime import date
import pytest
from unittest.mock import MagicMock, patch
from atlas.trading.universe import build_membership_set, filter_to_universe


def _mock_rows(pairs: list[tuple[int, date]]) -> list:
    return [{"instrument_id": iid, "date": d} for iid, d in pairs]


def test_membership_set_basic():
    rows = _mock_rows([(1, date(2024, 1, 1)), (1, date(2024, 1, 2)), (2, date(2024, 1, 1))])
    membership = build_membership_set(rows)
    assert date(2024, 1, 1) in membership[1]
    assert date(2024, 1, 2) in membership[1]
    assert date(2024, 1, 2) not in membership[2]


def test_filter_to_universe_respects_date():
    membership = {1: {date(2024, 1, 1)}, 2: {date(2024, 1, 1), date(2024, 1, 2)}}
    result = filter_to_universe([1, 2], date(2024, 1, 2), membership)
    assert 1 not in result
    assert 2 in result
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_universe.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading.universe'`

- [ ] **Step 3: Implement**

`atlas/trading/universe.py`:
```python
from __future__ import annotations

from collections import defaultdict
from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Connection

log = structlog.get_logger()


def build_membership_set(rows: list[dict]) -> dict[int, set[date]]:
    """Convert DB rows into {instrument_id: {date, ...}} for fast lookup."""
    result: dict[int, set[date]] = defaultdict(set)
    for row in rows:
        result[row["instrument_id"]].add(row["date"])
    return dict(result)


def filter_to_universe(
    instrument_ids: list[int],
    as_of_date: date,
    membership: dict[int, set[date]],
) -> list[int]:
    """Return only instrument_ids that were in the universe on as_of_date."""
    return [iid for iid in instrument_ids if as_of_date in membership.get(iid, set())]


def load_universe_membership(
    conn: Connection,
    universe: str,
    start_date: date,
    end_date: date,
) -> dict[int, set[date]]:
    """Load point-in-time membership from atlas_universe_membership_daily."""
    rows = conn.execute(
        text(
            "SELECT instrument_id, date FROM atlas_universe_membership_daily "
            "WHERE universe = :universe AND was_member = TRUE "
            "AND date BETWEEN :start AND :end"
        ),
        {"universe": universe, "start": start_date, "end": end_date},
    ).mappings().all()
    membership = build_membership_set([dict(r) for r in rows])
    log.info("universe_loaded", universe=universe, instruments=len(membership), rows=len(rows))
    return membership


def bootstrap_nifty500_membership(conn: Connection) -> int:
    """Seed atlas_universe_membership_daily from atlas_instruments for all available dates.

    This is an initial approximation — assumes each instrument was a member for
    all dates it has price data. Replace with NSE historical composition files
    for survivorship-bias-free simulation.
    """
    result = conn.execute(
        text(
            """
            INSERT INTO atlas_universe_membership_daily (instrument_id, date, universe, was_member)
            SELECT DISTINCT m.instrument_id, m.date, 'nifty500', TRUE
            FROM atlas_stock_metrics_daily m
            JOIN atlas_instruments i ON i.id = m.instrument_id
            WHERE i.index_member = 'nifty500'
            ON CONFLICT (instrument_id, date, universe) DO NOTHING
            """
        )
    )
    count = result.rowcount
    log.info("universe_bootstrapped", inserted=count)
    return count
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_universe.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/universe.py tests/trading/test_universe.py
git commit -m "feat(trading): point-in-time universe loader"
```

---

## Task 5: Layer 1 Perception Engine

**Files:**
- Create: `atlas/trading/perception.py`
- Create: `tests/trading/test_perception.py`

- [ ] **Step 1: Write failing tests**

`tests/trading/test_perception.py`:
```python
import numpy as np
import pytest
from datetime import date
from atlas.trading.perception import derive_rs_state, derive_regime_state, derive_vol_state
from atlas.trading.genome import GenomeFactory

# RS state constants
LAGGARD, WEAK, AVERAGE, STRONG, LEADER = 0, 1, 2, 3, 4
RISK_OFF, CAUTIOUS, CONSTRUCTIVE, RISK_ON = 0, 1, 2, 3
VOL_NORMAL, VOL_ELEVATED, VOL_HIGH = 0, 1, 2


def _genome():
    g = GenomeFactory.random()
    g.layer1.rs_leader_cutoff_pct = 70
    g.layer1.rs_strong_cutoff_pct = 55
    g.layer1.rs_average_cutoff_pct = 35
    g.layer1.rs_weak_cutoff_pct = 20
    return g


def test_rs_state_leader():
    genome = _genome()
    # rs_pctile_3m_rank = 85 → LEADER (>70)
    rs_pctile = np.array([[85.0]])
    state = derive_rs_state(rs_pctile, genome.layer1)
    assert state[0, 0] == LEADER


def test_rs_state_laggard():
    genome = _genome()
    rs_pctile = np.array([[10.0]])
    state = derive_rs_state(rs_pctile, genome.layer1)
    assert state[0, 0] == LAGGARD


def test_regime_risk_on():
    genome = _genome()
    genome.layer1.regime_risk_on_breadth_pct = 60
    genome.layer1.regime_risk_on_vix_ceiling = 18.0
    breadth = np.array([65.0])   # > 60 → qualifies
    vix = np.array([15.0])       # < 18 → qualifies
    regime = derive_regime_state(breadth, vix, genome.layer1)
    assert regime[0] == RISK_ON


def test_vol_elevated():
    genome = _genome()
    genome.layer1.vol_elevated_ratio = 1.4
    genome.layer1.vol_high_ratio = 1.75
    vol_ratio = np.array([[1.5]])
    state = derive_vol_state(vol_ratio, genome.layer1)
    assert state[0, 0] == VOL_ELEVATED
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_perception.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading.perception'`

- [ ] **Step 3: Implement**

`atlas/trading/perception.py`:
```python
"""Layer 1: convert raw metric arrays to state arrays using genome thresholds.

All inputs are numpy arrays. No DB calls. No pandas. Pure numpy operations
so vectorbt can batch thousands of genomes efficiently.

RS state:  0=Laggard, 1=Weak, 2=Average, 3=Strong, 4=Leader
Regime:    0=Risk-Off, 1=Cautious, 2=Constructive, 3=Risk-On
Vol state: 0=Normal, 1=Elevated, 2=High
Momentum:  0=Decelerating, 1=Neutral, 2=Accelerating
"""
from __future__ import annotations

import numpy as np

from atlas.trading.genome import Layer1Perception

# ---------------------------------------------------------------------------
# State integer constants (exported for callers)
# ---------------------------------------------------------------------------
RS_LAGGARD, RS_WEAK, RS_AVERAGE, RS_STRONG, RS_LEADER = 0, 1, 2, 3, 4
REGIME_RISK_OFF, REGIME_CAUTIOUS, REGIME_CONSTRUCTIVE, REGIME_RISK_ON = 0, 1, 2, 3
VOL_NORMAL, VOL_ELEVATED, VOL_HIGH = 0, 1, 2
MOM_DECELERATING, MOM_NEUTRAL, MOM_ACCELERATING = 0, 1, 2


def derive_rs_state(rs_pctile: np.ndarray, layer1: Layer1Perception) -> np.ndarray:
    """Map RS percentile array to RS state integers.

    Args:
        rs_pctile: shape (n_stocks, n_days) — blended RS percentile rank 0–100
        layer1: genome Layer1Perception with cutoff thresholds

    Returns:
        int8 array of same shape with RS state values 0–4
    """
    out = np.full(rs_pctile.shape, RS_LAGGARD, dtype=np.int8)
    out = np.where(rs_pctile >= layer1.rs_weak_cutoff_pct,   RS_WEAK,    out)
    out = np.where(rs_pctile >= layer1.rs_average_cutoff_pct, RS_AVERAGE, out)
    out = np.where(rs_pctile >= layer1.rs_strong_cutoff_pct,  RS_STRONG,  out)
    out = np.where(rs_pctile >= layer1.rs_leader_cutoff_pct,  RS_LEADER,  out)
    return out.astype(np.int8)


def derive_regime_state(breadth_pct: np.ndarray, vix: np.ndarray, layer1: Layer1Perception) -> np.ndarray:
    """Map market breadth + VIX to regime state integer per day.

    Args:
        breadth_pct: shape (n_days,) — % of universe above 50-day MA
        vix: shape (n_days,) — VIX value, NaN-safe

    Returns:
        int8 array shape (n_days,) with regime state 0–3
    """
    vix_valid = ~np.isnan(vix)
    vix_calm = vix_valid & (vix < layer1.regime_risk_on_vix_ceiling)

    out = np.full(breadth_pct.shape, REGIME_RISK_OFF, dtype=np.int8)
    out = np.where(breadth_pct >= layer1.regime_cautious_breadth_pct,     REGIME_CAUTIOUS,     out)
    out = np.where(breadth_pct >= layer1.regime_constructive_breadth_pct, REGIME_CONSTRUCTIVE, out)
    out = np.where(
        (breadth_pct >= layer1.regime_risk_on_breadth_pct) & (~vix_valid | vix_calm),
        REGIME_RISK_ON,
        out,
    )
    return out.astype(np.int8)


def derive_vol_state(vol_ratio: np.ndarray, layer1: Layer1Perception) -> np.ndarray:
    """Map vol_ratio_63 (10d vol / 63d vol) to vol state.

    Args:
        vol_ratio: shape (n_stocks, n_days)

    Returns:
        int8 array of same shape with vol state 0–2
    """
    out = np.full(vol_ratio.shape, VOL_NORMAL, dtype=np.int8)
    out = np.where(vol_ratio >= layer1.vol_elevated_ratio, VOL_ELEVATED, out)
    out = np.where(vol_ratio >= layer1.vol_high_ratio,      VOL_HIGH,     out)
    return out.astype(np.int8)


def derive_momentum_state(ema_ratio: np.ndarray, layer1: Layer1Perception) -> np.ndarray:
    """Map EMA ratio (short/long EMA) to momentum state.

    Args:
        ema_ratio: shape (n_stocks, n_days) — e.g. EMA21/EMA63

    Returns:
        int8 array of same shape with momentum state 0–2
    """
    out = np.full(ema_ratio.shape, MOM_NEUTRAL, dtype=np.int8)
    out = np.where(ema_ratio >= layer1.momentum_accel_ema_ratio, MOM_ACCELERATING,  out)
    out = np.where(ema_ratio <= layer1.momentum_decel_ema_ratio, MOM_DECELERATING,  out)
    return out.astype(np.int8)


def compute_blended_rs_pctile(
    rs_arrays: dict[str, np.ndarray],
    weights: dict[str, float],
) -> np.ndarray:
    """Weighted blend of multi-timeframe RS percentile arrays.

    Args:
        rs_arrays: {'1w': ndarray, '1m': ndarray, '3m': ndarray, '6m': ndarray, '12m': ndarray}
                   each shape (n_stocks, n_days)
        weights: genome rs_timeframe_weights, must sum to 1.0

    Returns:
        float32 array shape (n_stocks, n_days)
    """
    blended = np.zeros_like(next(iter(rs_arrays.values())), dtype=np.float32)
    for tf, arr in rs_arrays.items():
        blended += weights.get(tf, 0.0) * arr.astype(np.float32)
    return blended


def compute_rs_velocity(rs_state: np.ndarray, lookback: int) -> tuple[np.ndarray, np.ndarray]:
    """Compute days-in-current-state and improvement direction.

    Args:
        rs_state: int8 array shape (n_stocks, n_days)
        lookback: genome state_velocity_lookback_days

    Returns:
        days_in_state: int16 array shape (n_stocks, n_days)
        direction: int8 array (1=improving, 0=stable, -1=declining)
    """
    n_stocks, n_days = rs_state.shape
    days_in_state = np.ones((n_stocks, n_days), dtype=np.int16)
    direction = np.zeros((n_stocks, n_days), dtype=np.int8)

    for d in range(1, n_days):
        same = rs_state[:, d] == rs_state[:, d - 1]
        days_in_state[:, d] = np.where(same, days_in_state[:, d - 1] + 1, 1)

    # Direction: compare current state to state lookback days ago
    for d in range(lookback, n_days):
        past = rs_state[:, d - lookback]
        curr = rs_state[:, d]
        direction[:, d] = np.sign(curr.astype(np.int16) - past.astype(np.int16)).astype(np.int8)

    return days_in_state, direction
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_perception.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/perception.py tests/trading/test_perception.py
git commit -m "feat(trading): Layer 1 perception engine — numpy state matrices from genome thresholds"
```

---

## Task 6: Tax Engine

**Files:**
- Create: `atlas/trading/tax_engine.py`
- Create: `tests/trading/test_tax_engine.py`

- [ ] **Step 1: Write failing tests**

`tests/trading/test_tax_engine.py`:
```python
from decimal import Decimal
from datetime import date
import pytest
from atlas.trading.tax_engine import TaxLedger, compute_trade_net_pnl, accrue_liquidbees
from atlas.trading.config import PortfolioConfig


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
    brokerage = (Decimal("100") * Decimal("100") + Decimal("120") * Decimal("100")) * cfg.brokerage_rate
    stt = Decimal("120") * Decimal("100") * cfg.stt_rate_sell
    assert net < gross  # tax + costs reduce it
    assert net == gross - tax - brokerage - stt - (
        Decimal("100") * Decimal("100") + Decimal("120") * Decimal("100")
    ) * (cfg.exchange_charge_rate + cfg.sebi_charge_rate)


def test_ltcg_trade_with_exemption(cfg, ledger):
    ledger.ltcg_exemption_remaining = Decimal("125000")
    net = compute_trade_net_pnl(
        entry_price=Decimal("100"),
        exit_price=Decimal("150"),
        shares=Decimal("1000"),        # gross_pnl = 50,000
        entry_date=date(2023, 1, 1),
        exit_date=date(2024, 2, 1),   # 397 days ≥ 365 → LTCG
        config=cfg,
        ledger=ledger,
    )
    # gross_pnl = 50,000; exemption = 125,000 → taxable = 0 → no LTCG tax
    # exemption remaining after: 125,000 - 50,000 = 75,000
    assert ledger.ltcg_exemption_remaining == Decimal("75000")


def test_ltcg_trade_partial_exemption(cfg, ledger):
    ledger.ltcg_exemption_remaining = Decimal("50000")
    net = compute_trade_net_pnl(
        entry_price=Decimal("100"),
        exit_price=Decimal("200"),
        shares=Decimal("1000"),        # gross_pnl = 100,000
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
        shares=Decimal("100"),        # gross_pnl = -5000 (loss)
        entry_date=date(2023, 1, 1),
        exit_date=date(2024, 2, 1),
        config=cfg,
        ledger=ledger,
    )
    assert net < Decimal("0")  # net loss after costs


def test_liquidbees_accrual(cfg):
    idle = Decimal("1000000")  # ₹10L
    daily_net = accrue_liquidbees(idle, 1, cfg)
    # daily gross = 1,000,000 * 0.067 / 365 ≈ 183.56
    # daily net after 30% tax ≈ 183.56 * 0.70 ≈ 128.49
    assert Decimal("120") < daily_net < Decimal("140")
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_tax_engine.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading.tax_engine'`

- [ ] **Step 3: Implement**

`atlas/trading/tax_engine.py`:
```python
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
    financial_year: int                                     # starting year (e.g. 2024 for FY2024-25)
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
    exchange_fees = (entry_value + exit_value) * (config.exchange_charge_rate + config.sebi_charge_rate)
    total_costs = brokerage + stt + exchange_fees

    # Tax
    holding_days = (exit_date - entry_date).days

    # Ensure ledger is for the correct financial year
    exit_fy = _financial_year(exit_date)
    if exit_fy != ledger.financial_year:
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_tax_engine.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/tax_engine.py tests/trading/test_tax_engine.py
git commit -m "feat(trading): tax engine — STCG/LTCG/LiquidBees with Decimal arithmetic"
```

---

## Task 7: Layer 2 Decision Engine

**Files:**
- Create: `atlas/trading/decision.py`
- Create: `tests/trading/test_decision.py`

- [ ] **Step 1: Write failing tests**

`tests/trading/test_decision.py`:
```python
import numpy as np
import pytest
from atlas.trading.decision import compute_conviction, apply_entry_rules, apply_exit_rules
from atlas.trading.genome import GenomeFactory
from atlas.trading.perception import RS_LEADER, RS_STRONG, RS_AVERAGE, MOM_ACCELERATING, MOM_NEUTRAL, VOL_NORMAL, REGIME_RISK_ON


def _genome():
    g = GenomeFactory.random()
    g.layer1.synergy_weight = 0.2
    g.layer1.penalty_weight = 0.1
    g.risk_on.min_conviction_to_enter = 0.55
    g.risk_on.exit_rs_drop_tiers = 2
    return g


def test_conviction_high_rs_momentum_synergy():
    g = _genome()
    # High RS percentile + accelerating momentum → high conviction via synergy
    score = compute_conviction(
        rs_pctile_norm=0.90,       # 90th pctile → 0.90 normalized
        rs_state=RS_LEADER,
        momentum_state=MOM_ACCELERATING,
        vol_state=VOL_NORMAL,
        days_in_state=10,
        direction=1,
        layer1=g.layer1,
    )
    assert score > 0.5


def test_conviction_penalized_by_vol():
    g = _genome()
    g.layer1.penalty_weight = 0.3
    from atlas.trading.perception import VOL_HIGH
    score_normal_vol = compute_conviction(
        rs_pctile_norm=0.80,
        rs_state=RS_LEADER,
        momentum_state=MOM_NEUTRAL,
        vol_state=VOL_NORMAL,
        days_in_state=5,
        direction=0,
        layer1=g.layer1,
    )
    score_high_vol = compute_conviction(
        rs_pctile_norm=0.80,
        rs_state=RS_LEADER,
        momentum_state=MOM_NEUTRAL,
        vol_state=VOL_HIGH,
        days_in_state=5,
        direction=0,
        layer1=g.layer1,
    )
    assert score_high_vol < score_normal_vol


def test_entry_blocked_when_heat_cap_hit():
    g = _genome()
    conviction = np.array([0.8, 0.7])          # both above min_conviction
    heat = 0.21                                 # 21% > 20% max_portfolio_heat
    mask = apply_entry_rules(conviction, regime=REGIME_RISK_ON, portfolio_heat=heat, genome=g)
    assert not mask.any()                       # no entries when heat cap hit


def test_exit_on_rs_drop():
    g = _genome()
    g.risk_on.exit_rs_drop_tiers = 2
    # Stock was Strong (3), now Average (2) → dropped 1 tier
    prev_rs = np.array([RS_STRONG])
    curr_rs = np.array([RS_AVERAGE])
    mask = apply_exit_rules(
        prev_rs_state=prev_rs, curr_rs_state=curr_rs,
        holding_days=np.array([10]),
        min_hold_days=g.risk_on.min_hold_days,
        exit_rs_drop_tiers=g.risk_on.exit_rs_drop_tiers,
    )
    # Drop of 1 tier < required 2 tiers → no exit
    assert not mask[0]

    # Stock was Leader (4), now Weak (1) → dropped 3 tiers > threshold of 2
    prev_rs2 = np.array([RS_LEADER])
    curr_rs2 = np.array([1])   # WEAK
    mask2 = apply_exit_rules(
        prev_rs_state=prev_rs2, curr_rs_state=curr_rs2,
        holding_days=np.array([10]),
        min_hold_days=g.risk_on.min_hold_days,
        exit_rs_drop_tiers=g.risk_on.exit_rs_drop_tiers,
    )
    assert mask2[0]
```

- [ ] **Step 2: Confirm fail**

```bash
pytest tests/trading/test_decision.py -v
```

Expected: `ModuleNotFoundError: No module named 'atlas.trading.decision'`

- [ ] **Step 3: Implement**

`atlas/trading/decision.py`:
```python
"""Layer 2: conviction scoring and entry/exit signal generation.

Conviction formula (spec §6.2):
    base = weighted_sum(signals)
    synergy = rs_pctile_norm × momentum_state_norm   (RS × momentum interaction)
    penalty = vol_ratio_norm × rs_pctile_norm        (high vol discounts RS)
    conviction = base × (1 + synergy_weight × synergy) × (1 - penalty_weight × penalty)
"""
from __future__ import annotations

import numpy as np

from atlas.trading.genome import Genome, Layer1Perception, RegimePlaybook
from atlas.trading.perception import (
    RS_LAGGARD, RS_LEADER, RS_STRONG, RS_AVERAGE, RS_WEAK,
    MOM_ACCELERATING, MOM_NEUTRAL, MOM_DECELERATING,
    VOL_NORMAL, VOL_ELEVATED, VOL_HIGH,
    REGIME_RISK_OFF, REGIME_CAUTIOUS, REGIME_CONSTRUCTIVE, REGIME_RISK_ON,
)


# Normalize state integers to [0, 1] for scoring
_RS_NORM = {RS_LAGGARD: 0.0, RS_WEAK: 0.2, RS_AVERAGE: 0.4, RS_STRONG: 0.7, RS_LEADER: 1.0}
_MOM_NORM = {MOM_DECELERATING: 0.0, MOM_NEUTRAL: 0.5, MOM_ACCELERATING: 1.0}
_VOL_NORM = {VOL_NORMAL: 0.0, VOL_ELEVATED: 0.5, VOL_HIGH: 1.0}


def compute_conviction(
    rs_pctile_norm: float,   # 0–1 (raw percentile / 100)
    rs_state: int,
    momentum_state: int,
    vol_state: int,
    days_in_state: int,
    direction: int,          # -1, 0, 1
    layer1: Layer1Perception,
) -> float:
    """Compute conviction score 0–1 for a single stock on a single day."""
    rs_norm = rs_pctile_norm
    mom_norm = _MOM_NORM[momentum_state]
    vol_norm = _VOL_NORM[vol_state]
    rs_state_norm = _RS_NORM[rs_state]

    # Velocity bonus: fresh breakout (direction=1, few days in state) > mature leader
    velocity_bonus = 0.1 * direction * max(0.0, 1.0 - days_in_state / 30.0)

    # Base score: weighted blend of RS, momentum, velocity
    base = 0.60 * rs_norm + 0.25 * mom_norm + 0.10 * rs_state_norm + 0.05 * max(0.0, velocity_bonus)

    # Interaction terms (spec §6.2)
    synergy = rs_norm * mom_norm
    penalty = vol_norm * rs_norm

    conviction = (
        base
        * (1.0 + layer1.synergy_weight * synergy)
        * (1.0 - layer1.penalty_weight * penalty)
    )
    return float(np.clip(conviction, 0.0, 1.0))


def _get_playbook(genome: Genome, regime: int) -> RegimePlaybook:
    if regime == REGIME_RISK_ON:
        return genome.risk_on
    if regime == REGIME_CONSTRUCTIVE:
        return genome.constructive
    return genome.cautious  # CAUTIOUS or RISK_OFF handled upstream


def apply_entry_rules(
    conviction: np.ndarray,       # shape (n_stocks,) float
    regime: int,
    portfolio_heat: float,
    genome: Genome,
    portfolio_drawdown: float = 0.0,
) -> np.ndarray:
    """Return boolean mask of stocks eligible for entry today.

    Blocks all entries if:
    - regime is Risk-Off
    - portfolio heat cap exceeded
    - portfolio drawdown >= dd_halt_entry_pct
    """
    if regime == REGIME_RISK_OFF:
        return np.zeros(len(conviction), dtype=bool)

    from atlas.trading.config import PortfolioConfig  # avoid circular at import time
    playbook = _get_playbook(genome, regime)

    if portfolio_heat >= float(PortfolioConfig().max_portfolio_heat_pct):
        return np.zeros(len(conviction), dtype=bool)

    if portfolio_drawdown >= playbook.dd_halt_entry_pct / 100.0:
        return np.zeros(len(conviction), dtype=bool)

    return conviction >= playbook.min_conviction_to_enter


def apply_exit_rules(
    prev_rs_state: np.ndarray,    # shape (n_positions,) int8
    curr_rs_state: np.ndarray,
    holding_days: np.ndarray,     # shape (n_positions,) int
    min_hold_days: int,
    exit_rs_drop_tiers: int,
) -> np.ndarray:
    """Return boolean mask of positions that should be exited today.

    Exits when RS state drops by >= exit_rs_drop_tiers tiers,
    subject to min_hold_days constraint.
    """
    rs_drop = prev_rs_state.astype(np.int8) - curr_rs_state.astype(np.int8)
    held_long_enough = holding_days >= min_hold_days
    return (rs_drop >= exit_rs_drop_tiers) & held_long_enough


def compute_position_size(
    conviction: float,
    playbook: RegimePlaybook,
    max_position_pct: float = 0.05,
) -> float:
    """Return position size as fraction of portfolio.

    Base size = playbook.base_position_pct / 100.
    Scaled by conviction above entry threshold.
    Capped at max_position_pct.
    """
    base = playbook.base_position_pct / 100.0
    excess = conviction - playbook.min_conviction_to_enter
    scale = 1.0 + min(excess * 2.0, 1.0)   # up to 2× base at high conviction
    return min(base * scale, max_position_pct)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/trading/test_decision.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add atlas/trading/decision.py tests/trading/test_decision.py
git commit -m "feat(trading): Layer 2 decision engine — conviction score + entry/exit signals"
```

---

*[Tasks 8–19 continue in Part 2 of this plan — see same directory.]*
