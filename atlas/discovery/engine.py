"""Walk-forward sweep engine — the matrix generator.

This module hosts :class:`WalkForwardSweep`, the v6 24-cell discovery engine
(CONTEXT.md §"24-framework discovery model"). Discovery is per cell:

    discover_cell(spec) -> CellDiscoveryResult

and the matrix sweep iterates all 24 ``(cap_tier × tenure × actionable_state)``
combinations:

    run_full_matrix() -> SweepResult

A single :meth:`WalkForwardSweep.persist` then writes the results to the
two v6 tables that already exist in migrations 080 + 081_z:

* ``atlas_cell_walkforward_runs`` — every attempt (audit row).
* ``atlas_cell_definitions``      — VALIDATED cells only.

Data-source modes
-----------------
* ``mode="synthetic"`` — fully implemented; generates a deterministic
  ~100-instrument synthetic universe spanning the walk-forward window
  with injected Pullback + Severely Broken signals for Mid-cap. Proves the
  pipeline end-to-end; other 22 cells produce ``no_conviction`` on noise.

* ``mode="cache"`` — reads ``/tmp/sde_ohlcv_cache.pkl`` if present.
  Raises NotImplementedError otherwise; the cache file is a per-session
  artifact, not a deliverable.

* ``mode="supabase"`` — reads from ``de_equity_ohlcv`` via Supabase MCP.
  Stubbed; raises NotImplementedError until the MCP client is wired.

* ``mode="ec2"`` — reads from EC2 via SSH (legacy v5 path). Stubbed.

Vectorised — no Python loops over instruments.
"""

# allow-large: single cohesive sweep-engine module — synthetic-data
# generator, per-cell discovery loop, persistence, friction adjustment,
# and the matrix runner form one indivisible compute unit. Splitting
# would force shared run-state plumbing across modules with no clean
# public seam (same shape as atlas/regime/cron.py + atlas/inference/daily.py).

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.decisions.rule_dsl import CellRule, FeaturePredicate

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Methodology constants
# ---------------------------------------------------------------------------

CAP_TIERS: tuple[Literal["Small", "Mid", "Large"], ...] = ("Small", "Mid", "Large")
TENURES: tuple[Literal["1m", "3m", "6m", "12m"], ...] = ("1m", "3m", "6m", "12m")
ACTIONS: tuple[Literal["POSITIVE", "NEGATIVE"], ...] = ("POSITIVE", "NEGATIVE")

# Per-tenure IC floors. Literature-backed defaults (CONTEXT.md
# §"Per-tenure IC floor"). The Phase 0.5g-pre null-distribution sweep
# (CONTEXT.md §"Null-distribution baseline for IC floors") replaces these
# with ``max(literature, 95th percentile of null)`` once it lands. For
# now we use the literature floors directly.
PER_TENURE_IC_FLOOR: dict[str, Decimal] = {
    "1m": Decimal("0.02"),
    "3m": Decimal("0.04"),
    "6m": Decimal("0.05"),
    "12m": Decimal("0.04"),
}

# Tenure -> forward-return horizon in trading days. 21d/63d/126d/252d are
# the standard approximations.
TENURE_TO_HORIZON_DAYS: dict[str, int] = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}

# Methodology lock SHA — the locking experiment identifier. Stamped into
# every walk-forward run row + cell definition row for SEBI audit.
METHODOLOGY_LOCK_REF = "methodology-lock-2026-05-23"

# Per-tier friction placeholders (used when DB read fails or in dry-run).
# Matches the seed values in migration 081_z. Sum of (bid_ask + impact +
# brokerage + slippage) per tier, expressed as a one-way decimal fraction.
DEFAULT_FRICTION_BY_TIER: dict[str, Decimal] = {
    "Small": Decimal("0.006300"),  # 0.30 + 0.20 + 0.03 + 0.10 = 0.63%
    "Mid": Decimal("0.003300"),  # 0.15 + 0.10 + 0.03 + 0.05 = 0.33%
    "Large": Decimal("0.001300"),  # 0.05 + 0.03 + 0.03 + 0.02 = 0.13%
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WalkForwardWindow:
    """A single train/test window for walk-forward validation.

    Methodology lock §3: 60-month train / 12-month test, stepped 12 months.
    The test windows must not overlap; train_end must precede test_start.
    """

    train_start: date
    train_end: date
    test_start: date
    test_end: date

    def __post_init__(self) -> None:
        if self.train_end >= self.test_start:
            raise ValueError(
                f"window invariant: train_end ({self.train_end}) must be < "
                f"test_start ({self.test_start})"
            )
        if self.train_start >= self.train_end:
            raise ValueError("train_start must be < train_end")
        if self.test_start >= self.test_end:
            raise ValueError("test_start must be < test_end")


# Methodology lock §3: 60-month train / 12-month test, stepped 12 months.
# Three windows give 36 months of OOS coverage (2022-05 → 2025-04).
DEFAULT_WINDOWS: tuple[WalkForwardWindow, ...] = (
    WalkForwardWindow(date(2017, 5, 1), date(2022, 4, 30), date(2022, 5, 1), date(2023, 4, 30)),
    WalkForwardWindow(date(2018, 5, 1), date(2023, 4, 30), date(2023, 5, 1), date(2024, 4, 30)),
    WalkForwardWindow(date(2019, 5, 1), date(2024, 4, 30), date(2024, 5, 1), date(2025, 4, 30)),
)


@dataclass(frozen=True)
class CellSpec:
    """Specification for a cell to discover (or re-validate).

    Fields:
        cap_tier: Small / Mid / Large.
        tenure: 1m / 3m / 6m / 12m.
        action: POSITIVE or NEGATIVE. NEUTRAL is the residual and is NOT
            discovered as a separate cell (CONTEXT.md §"24-framework").
        rule_type_hint: one of the 9 v6 archetypes. Drives entry criteria
            derivation. Typical pairings:
              POSITIVE + 12m → "pullback"
              POSITIVE + 6m  → "pullback"
              POSITIVE + 3m  → "emerging"
              POSITIVE + 1m  → "emerging"
              NEGATIVE + 12m → "severely_broken"
              NEGATIVE + 6m  → "severely_broken"
              NEGATIVE + 3m  → "topping"
              NEGATIVE + 1m  → "topping"
    """

    cap_tier: Literal["Small", "Mid", "Large"]
    tenure: Literal["1m", "3m", "6m", "12m"]
    action: Literal["POSITIVE", "NEGATIVE"]
    rule_type_hint: str


@dataclass(frozen=True)
class CellDiscoveryResult:
    """The per-cell discovery outcome.

    Attributes:
        spec: the input :class:`CellSpec`.
        validated: True iff IC >= per-tenure floor AND
            friction-adjusted excess has the right sign for the action.
        ic: Spearman rank IC across pooled walk-forward observations.
        tp_rate: true-positive rate for POSITIVE cells; None for NEGATIVE.
        tn_rate: true-negative rate for NEGATIVE cells; None for POSITIVE.
        median_excess: median realized forward-return excess vs universe.
        friction_adjusted_excess: median_excess - per-tier friction.
        percentile_*: realized-excess distribution at 10/25/50/75/90.
        n_observations: pooled observation count across walk-forward
            test windows for this cell's eligibility set.
        stable_features: features whose contribution survived the
            stability check (placeholder list for v6 launch; real
            stability scoring lands in continuous-improvement workstream).
        rule_dsl: the JSONB-serialisable dict to INSERT into
            ``atlas_cell_definitions.rule_dsl`` when ``validated``;
            empty dict otherwise.
        walkforward_run_id: UUID of the audit row.
        notes: optional structured notes (e.g. why ``no_conviction``).
    """

    spec: CellSpec
    validated: bool
    ic: Decimal | None
    tp_rate: Decimal | None
    tn_rate: Decimal | None
    median_excess: Decimal | None
    friction_adjusted_excess: Decimal | None
    percentile_10: Decimal | None
    percentile_25: Decimal | None
    percentile_50: Decimal | None
    percentile_75: Decimal | None
    percentile_90: Decimal | None
    n_observations: int
    stable_features: list[str]
    rule_dsl: dict[str, Any]
    walkforward_run_id: uuid.UUID
    notes: str


@dataclass(frozen=True)
class SweepResult:
    """Aggregate result of a 24-cell matrix sweep.

    Attributes:
        results: per-cell results, length = 24 (3 caps × 4 tenures × 2 actions).
        run_started_at: sweep start timestamp.
        run_completed_at: sweep completion timestamp.
        mode: data-source mode used ('synthetic', 'cache', 'supabase', 'ec2').
        windows: walk-forward windows used.
    """

    results: tuple[CellDiscoveryResult, ...]
    run_started_at: datetime
    run_completed_at: datetime
    mode: str
    windows: tuple[WalkForwardWindow, ...]

    @property
    def validated_count(self) -> int:
        return sum(1 for r in self.results if r.validated)

    @property
    def no_conviction_count(self) -> int:
        return len(self.results) - self.validated_count


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------


_SYNTHETIC_SEED = 42
_SYNTHETIC_N_INSTRUMENTS = 100
# We give Mid-cap real signal at 12m so the pipeline validates end-to-end.
# Per CONTEXT.md the methodology-locked validated cells are precisely
# Mid Pullback @ 12m (POSITIVE) and Mid Severely Broken @ 12m (NEGATIVE).
_MID_CAP_SLICE_FRACTION = 0.4  # 40% of instruments tagged Mid


def _generate_synthetic_universe(
    n_instruments: int = _SYNTHETIC_N_INSTRUMENTS,
    start: date = date(2017, 1, 1),
    end: date = date(2025, 4, 30),
    seed: int = _SYNTHETIC_SEED,
) -> pd.DataFrame:
    """Generate a deterministic synthetic OHLCV universe.

    Designed so a SMALL number of cells genuinely validate — proves the
    engine works end-to-end without injecting universe-wide artifacts:

    * Mid-cap instruments at 12m horizon have a real Pullback signal
      injected (top-half RS + moderate drawdown → POSITIVE forward return).
    * Mid-cap instruments at 12m horizon have a real Severely Broken
      signal injected (bot-half RS + deep drawdown → NEGATIVE forward
      return).
    * Other 22 (cap × tenure × action) cells should produce
      ``no_conviction`` on this noise — proves the per-tenure floor works.

    Reproducible: uses ``np.random.default_rng(seed)``.

    Returns:
        DataFrame with columns:
        ``instrument_id`` (str), ``date`` (date), ``open``, ``high``,
        ``low``, ``close`` (Decimal-friendly floats), ``volume``,
        ``sector``, ``cap_tier``.
    """
    rng = np.random.default_rng(seed)

    # Trading-day calendar — Mon-Fri only, no holidays. Good enough for
    # synthetic; we just need ~252 days/year.
    all_days = pd.date_range(start, end, freq="B")  # business days
    n_days = len(all_days)

    # Cap tiers — fixed split so the matrix has cells in every row.
    cap_tier_choices = np.array(["Small", "Mid", "Large"])
    cap_tier_probs = np.array([0.3, _MID_CAP_SLICE_FRACTION, 0.3])
    cap_tier_probs = cap_tier_probs / cap_tier_probs.sum()
    cap_tiers = rng.choice(cap_tier_choices, size=n_instruments, p=cap_tier_probs)

    # Sectors — 10 buckets; uniform.
    sectors = rng.choice(
        np.array([f"sec_{i:02d}" for i in range(10)]),
        size=n_instruments,
    )

    # Generate per-instrument log-return paths.
    # Daily return: N(mu=0.0005, sigma=0.018) — annualised ~12% drift / 28% vol
    # That gives a realistic non-degenerate cross-section.
    base_mu = 0.0005
    base_sigma = 0.018
    log_rets = rng.normal(base_mu, base_sigma, size=(n_days, n_instruments))

    # Inject signal for Mid-cap @ 12m horizon.
    #
    # Mechanism: we assign each Mid-cap instrument a hidden "signal_kind"
    # label drawn at the START of each ~year-long block. For "pullback"
    # blocks, drift turns positive in the 252-day forward window iff
    # current state matches (top-half RS + moderate drawdown). For
    # "severely_broken" blocks the symmetric NEGATIVE injection runs.
    #
    # The signal is engineered to be DETECTABLE by walk-forward IC but
    # not so strong it leaks into 1m/3m/6m horizons in a tradable way —
    # other cells should still produce no_conviction.
    is_mid = cap_tiers == "Mid"
    mid_idx = np.flatnonzero(is_mid)

    # Compute rolling-126-day RS proxy (used to label top/bottom half)
    # and rolling drawdown later. We do it vectorised on the log-return
    # cumulative path.
    log_prices_no_signal = np.cumsum(log_rets, axis=0)

    # Per-instrument mean-of-window RS proxy = log_price[t] - log_price[t-126].
    rolling_window = 126
    rs_proxy = np.full_like(log_prices_no_signal, np.nan)
    rs_proxy[rolling_window:] = (
        log_prices_no_signal[rolling_window:] - log_prices_no_signal[:-rolling_window]
    )

    # Drawdown from running max of last 126 days.
    rolling_max = (
        pd.DataFrame(log_prices_no_signal)
        .rolling(window=rolling_window, min_periods=1)
        .max()
        .to_numpy()
    )
    drawdown = log_prices_no_signal - rolling_max  # always <= 0

    # Now inject. For each Mid-cap instrument, on day t we look at the
    # state on day t (rs_proxy[t], drawdown[t]) and decide whether to
    # add a slice of return to the next 252 days.
    #
    # Pullback POSITIVE @ 12m: top-half-RS + drawdown in [-0.15, -0.05]
    # → add +0.0006 to each of next 252 daily log-returns
    #   (+0.0006 * 252 = +15% additional 12m return — clearly detectable)
    # Severely Broken NEGATIVE @ 12m: bot-half-RS + drawdown < -0.25
    # → subtract 0.0006 from each of next 252 daily log-returns
    pullback_boost = 0.0006
    severe_drag = -0.0006
    horizon = 252

    # Cross-sectional RS rank per day (high RS = top half).
    rs_rank_df = pd.DataFrame(rs_proxy[:, mid_idx]).rank(axis=1, pct=True)
    rs_top_half = rs_rank_df.to_numpy() >= 0.5
    rs_bot_half = rs_rank_df.to_numpy() < 0.5

    # Pullback eligibility per day per mid-cap instrument.
    pullback_mask = rs_top_half & (drawdown[:, mid_idx] <= -0.05) & (drawdown[:, mid_idx] >= -0.15)
    severe_mask = rs_bot_half & (drawdown[:, mid_idx] <= -0.25)

    # Pre-allocate the boost array — for each (day, mid-cap-instrument),
    # the additional log-return *applied at this day*. We need to roll
    # the forward boost back so it's the signal that the *current state*
    # predicts. So if pullback_mask is True at day t, we add the boost
    # to days t+1 through t+horizon.
    boost_mid = np.zeros((n_days, len(mid_idx)))

    # Vectorise the forward fill: for each ON cell at day t in mask, we
    # need to add a constant to rows [t+1 : t+1+horizon]. We approximate
    # this efficiently by computing a one-shot "trigger density" — at
    # each day t the boost is the SUM of triggers in days [t-horizon, t-1]
    # times the per-trigger boost.
    #
    # This isn't quite the spec ("add to next 252 days"), but it's
    # equivalent in expectation and matters only for the signal-strength
    # we engineer — we want IC > floor on a 12m forward-return regression
    # against the entry-day state.
    pullback_density_df = pd.DataFrame(pullback_mask.astype(float))
    pullback_rolling = cast(
        pd.DataFrame,
        pullback_density_df.rolling(window=horizon, min_periods=1).sum(),
    )
    pullback_density = (
        pullback_rolling.shift(1).fillna(0).to_numpy()  # boost applies AFTER trigger
    )
    severe_density_df = pd.DataFrame(severe_mask.astype(float))
    severe_rolling = cast(
        pd.DataFrame,
        severe_density_df.rolling(window=horizon, min_periods=1).sum(),
    )
    severe_density = severe_rolling.shift(1).fillna(0).to_numpy()
    # Per-day boost is the trigger density * per-trigger boost, normalised
    # by horizon so the cumulative effect over the forward window matches.
    boost_mid += pullback_density * (pullback_boost / horizon)
    boost_mid += severe_density * (severe_drag / horizon)

    # Apply the boost to the raw log-returns of mid-cap instruments.
    log_rets[:, mid_idx] += boost_mid

    # Build OHLCV from log-returns. Start every instrument at price 100.
    log_prices = np.cumsum(log_rets, axis=0)
    close_prices = 100.0 * np.exp(log_prices)
    # Synthesize OHL around close with small intraday spread.
    intraday_spread = rng.uniform(0.005, 0.015, size=close_prices.shape)
    high_prices = close_prices * (1 + intraday_spread / 2)
    low_prices = close_prices * (1 - intraday_spread / 2)
    open_prices = close_prices * (1 + rng.normal(0, 0.003, size=close_prices.shape))
    # Volume: log-uniform between 10k and 10M per day.
    volumes = np.exp(rng.uniform(np.log(1e4), np.log(1e7), size=close_prices.shape))

    # Build instrument_ids — stable hex-ish string per instrument index.
    instrument_ids = np.array([f"synth_{i:04d}" for i in range(n_instruments)])

    # Long-form dataframe — vectorised tile of metadata across time.
    df = pd.DataFrame(
        {
            "instrument_id": np.tile(instrument_ids, n_days),
            "date": np.repeat(np.array([d.date() for d in all_days]), n_instruments),
            "open": open_prices.flatten(order="C"),
            "high": high_prices.flatten(order="C"),
            "low": low_prices.flatten(order="C"),
            "close": close_prices.flatten(order="C"),
            "volume": volumes.flatten(order="C"),
            "sector": np.tile(sectors, n_days),
            "cap_tier": np.tile(cap_tiers, n_days),
        }
    )
    return df


# ---------------------------------------------------------------------------
# Cache-mode loader (real OHLCV from EC2-scp'd pickles in /tmp)
# ---------------------------------------------------------------------------

# Default cache file locations. Overridable via WalkForwardSweep(cache_dir=...).
# /tmp is the agreed-upon scp target for EC2-pulled OHLCV pickles; not used
# at runtime in production (production reads from Supabase).
DEFAULT_CACHE_DIR = Path("/tmp")
OHLCV_CACHE_FILENAME = "sde_ohlcv_cache.pkl"
NIFTY500_CACHE_FILENAME = "nifty500_cache.pkl"
BLACKLIST_FILENAME = "iid_blacklist.json"

# Trailing window for cap_tier derivation (per CONTEXT.md
# "cap_tier (point-in-time semantics)").
CAP_TIER_LOOKBACK_DAYS = 60


def _load_cache_files(
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Load OHLCV + nifty500 + blacklist from the on-disk cache.

    Returns:
        ohlcv: DataFrame with columns (date, iid, close, volume).
            ``date`` is naive datetime; ``iid`` is the v6 instrument UUID.
        nifty500: Series indexed by date with the benchmark close.
        blacklist: list of iid strings to exclude from the universe.

    Raises:
        FileNotFoundError: if any cache file is missing, with an actionable
            "scp from ec2 first" message.
    """
    ohlcv_path = cache_dir / OHLCV_CACHE_FILENAME
    nifty500_path = cache_dir / NIFTY500_CACHE_FILENAME
    blacklist_path = cache_dir / BLACKLIST_FILENAME

    missing = [p for p in (ohlcv_path, nifty500_path, blacklist_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"missing cache files: {[str(p) for p in missing]}. "
            f"scp from ec2 first: "
            f"`scp jsl-wealth-server:/tmp/{OHLCV_CACHE_FILENAME} "
            f"{cache_dir}/` (and the nifty500/blacklist siblings). "
            "For pipeline validation use mode='synthetic'."
        )

    # pickles are dev-only cache artifacts scp'd from our own EC2 host;
    # never user input. CI never loads them (cache files absent there).
    ohlcv = cast(pd.DataFrame, pd.read_pickle(ohlcv_path))  # noqa: S301
    nifty500 = cast(pd.Series, pd.read_pickle(nifty500_path))  # noqa: S301
    with blacklist_path.open() as fh:
        blacklist_raw = json.load(fh)
    # Blacklist is a list of {"iid": "...", "symbol": "..."} dicts.
    blacklist = [str(row["iid"]) for row in blacklist_raw]
    return ohlcv, nifty500, blacklist


def _compute_cap_tier_panel(
    ohlcv: pd.DataFrame,
    *,
    lookback_days: int = CAP_TIER_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """Compute point-in-time cap_tier per (date, iid) from trailing-60d traded value.

    Per CONTEXT.md "cap_tier (point-in-time semantics)": at each date,
    rank iids by trailing-60d median (close × volume), then qcut into 3
    terciles (Small bottom, Mid middle, Large top).

    Vectorised — no Python loops over instruments. Uses pandas groupby +
    rolling per-instrument; ranks cross-sectionally per date.

    Args:
        ohlcv: long-form DataFrame with (date, iid, close, volume).
        lookback_days: trailing window for median traded value.

    Returns:
        DataFrame with columns (date, iid, cap_tier). cap_tier is NaN for
        dates where insufficient history exists (< lookback_days) — caller
        should drop or treat as "unclassified".
    """
    df = cast(pd.DataFrame, ohlcv[["date", "iid", "close", "volume"]].copy())
    df = cast(pd.DataFrame, df.sort_values(["iid", "date"]).reset_index(drop=True))
    df["tv"] = df["close"].astype(float) * df["volume"].astype(float)
    # Per-iid rolling median traded value over 60 sessions.
    df["med_tv_60d"] = df.groupby("iid", group_keys=False)["tv"].transform(
        lambda s: s.rolling(window=lookback_days, min_periods=lookback_days).median()
    )

    # Cross-sectional tercile per date. qcut with duplicates='drop' for
    # the edge case where many ties exist; fall back to rank-based bucket.
    def _bucket(s: pd.Series) -> pd.Series:
        valid = s.dropna()
        if len(valid) < 3:
            return pd.Series(np.nan, index=s.index, dtype=object)
        ranks = valid.rank(pct=True)
        # bottom third Small, middle Mid, top third Large.
        out = pd.Series(np.nan, index=s.index, dtype=object)
        out.loc[ranks.index] = np.where(
            ranks <= (1.0 / 3),
            "Small",
            np.where(ranks <= (2.0 / 3), "Mid", "Large"),
        )
        return out

    df["cap_tier"] = df.groupby("date", group_keys=False)["med_tv_60d"].transform(_bucket)
    return cast(pd.DataFrame, df[["date", "iid", "cap_tier"]])


def _build_cache_universe(
    ohlcv: pd.DataFrame,
    blacklist: list[str],
    *,
    lookback_days: int = CAP_TIER_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """Build the engine-shaped universe DataFrame from cache OHLCV.

    Pipeline:
      1. Drop blacklisted iids.
      2. Compute cap_tier panel (point-in-time, trailing-60d traded value).
      3. Merge cap_tier back; drop rows where cap_tier is NaN (early history).
      4. Synthesize open/high/low = close (engine never reads them; we only
         use close for log-returns + drawdown).
      5. Rename ``iid`` → ``instrument_id`` to match the engine's schema.
      6. Add a placeholder ``sector`` column (engine archetypes don't use
         sector — Pullback + Severely Broken work on RS + drawdown only).

    Returns:
        DataFrame with columns (instrument_id, date, open, high, low, close,
        volume, sector, cap_tier) — the same shape the synthetic generator
        produces, so the rest of the engine flows through unchanged.
    """
    if blacklist:
        ohlcv = cast(pd.DataFrame, ohlcv[~ohlcv["iid"].isin(list(blacklist))].copy())

    cap_panel = _compute_cap_tier_panel(ohlcv, lookback_days=lookback_days)
    df = ohlcv.merge(cap_panel, on=["date", "iid"], how="left")
    df = cast(pd.DataFrame, df.dropna(subset=["cap_tier"]).reset_index(drop=True))

    # Normalize date column to python date for downstream comparisons
    # against WalkForwardWindow's date fields.
    if pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = df["date"].dt.date

    close = df["close"].astype(float)
    df["open"] = close
    df["high"] = close
    df["low"] = close
    df["close"] = close
    df["volume"] = df["volume"].astype(float)
    df["sector"] = "unknown"  # cache lacks sector; archetypes here don't need it
    df = df.rename(columns={"iid": "instrument_id"})

    return cast(
        pd.DataFrame,
        df[
            [
                "instrument_id",
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "sector",
                "cap_tier",
            ]
        ].reset_index(drop=True),
    )


# ---------------------------------------------------------------------------
# Walk-forward computation helpers
# ---------------------------------------------------------------------------


def _filter_universe_by_cap(universe: pd.DataFrame, cap_tier: str) -> pd.DataFrame:
    mask = universe["cap_tier"] == cap_tier
    filtered = universe.loc[mask].copy()
    return filtered


def _compute_state_features(universe_subset: pd.DataFrame) -> pd.DataFrame:
    """Compute per-row state features needed for entry conditions.

    Adds columns: rs_proxy_126 (relative-strength proxy), drawdown_126,
    rs_rank_pct (cross-sectional rank in [0,1] within cap_tier per date).

    Vectorised. No Python loop over instruments.
    """
    df = universe_subset.copy()
    df = df.sort_values(["instrument_id", "date"]).reset_index(drop=True)
    df["log_close"] = np.log(df["close"].clip(lower=1e-9))

    # Per-instrument rolling features.
    g = df.groupby("instrument_id", group_keys=False)
    df["log_close_lag_126"] = g["log_close"].shift(126)
    df["rs_proxy_126"] = df["log_close"] - df["log_close_lag_126"]
    df["running_max_126"] = g["log_close"].transform(
        lambda s: s.rolling(window=126, min_periods=1).max()
    )
    df["drawdown_126"] = df["log_close"] - df["running_max_126"]

    # Cross-sectional rank per date.
    df["rs_rank_pct"] = df.groupby("date")["rs_proxy_126"].rank(pct=True)
    return df


def _derive_entry_mask(state_df: pd.DataFrame, rule_type_hint: str, action: str) -> pd.Series:
    """Build a boolean entry mask from rule_type_hint.

    The mappings encode the v6 archetypes per CONTEXT.md:
      * pullback: top-half RS, drawdown in [-15%, -5%].
      * severely_broken: bot-half RS, drawdown < -25%.
      * emerging: bot-half RS, drawdown in [-10%, 0%], early bottoming.
      * topping: top-half RS, drawdown > -3% (near highs).
    """
    rs = state_df["rs_rank_pct"]
    dd = state_df["drawdown_126"]

    if rule_type_hint == "pullback":
        mask = (rs >= 0.5) & (dd <= -0.05) & (dd >= -0.15)
    elif rule_type_hint == "severely_broken":
        mask = (rs < 0.5) & (dd <= -0.25)
    elif rule_type_hint == "emerging":
        mask = (rs < 0.5) & (dd >= -0.10) & (dd <= 0.0)
    elif rule_type_hint == "topping":
        mask = (rs >= 0.5) & (dd >= -0.03)
    else:
        # Fallback: never matches.
        mask = pd.Series(False, index=state_df.index)

    # Drop rows where features are NaN (early history).
    mask = mask & state_df["rs_proxy_126"].notna() & state_df["drawdown_126"].notna()
    return mask


def _compute_forward_returns(state_df: pd.DataFrame, horizon_days: int) -> pd.Series:
    """Per-row forward log-return over ``horizon_days``.

    Computed as ``log_close[t + horizon] - log_close[t]`` per instrument.
    """
    g = state_df.sort_values(["instrument_id", "date"]).groupby("instrument_id", group_keys=False)
    forward_log_close = g["log_close"].shift(-horizon_days)
    return forward_log_close - state_df.sort_values(["instrument_id", "date"])["log_close"]


def _compute_universe_forward_returns(state_df: pd.DataFrame, horizon_days: int) -> pd.Series:
    """Per-date cross-sectional mean forward return — the benchmark."""
    fwd = _compute_forward_returns(state_df, horizon_days)
    state_df = state_df.assign(_fwd=fwd.values)
    daily_mean = cast(pd.Series, state_df.groupby("date")["_fwd"].transform("mean"))
    return daily_mean


def _compute_ic(
    state_df: pd.DataFrame,
    score: pd.Series,
    forward_return: pd.Series,
) -> Decimal | None:
    """Spearman rank IC between ``score`` and ``forward_return``.

    Computed pool-of-observations (not per-date IC averaged) — methodology
    lock §3 documents pooled IC as the headline number.

    Returns None if there are fewer than 30 valid (score, return) pairs.
    """
    aligned = pd.DataFrame({"score": score.values, "fwd": forward_return.values})
    aligned = aligned.dropna()
    if len(aligned) < 30:
        return None
    # Spearman = pearson on ranks.
    score_ranks = cast(pd.Series, aligned["score"].rank())
    fwd_ranks = cast(pd.Series, aligned["fwd"].rank())
    score_std = float(cast(float, score_ranks.std()))
    fwd_std = float(cast(float, fwd_ranks.std()))
    if score_std == 0 or fwd_std == 0:
        return None
    corr_value = float(cast(float, score_ranks.corr(fwd_ranks)))
    if np.isnan(corr_value):
        return None
    return Decimal(str(round(corr_value, 6)))


def _build_rule_dsl(spec: CellSpec) -> dict[str, Any]:
    """Construct the flat-AND ``rule_dsl`` for a validated cell.

    Returns a JSONB-serialisable dict. Pydantic validates the shape via
    :class:`atlas.decisions.rule_dsl.CellRule` — we round-trip through
    ``CellRule.model_dump`` so the shape is canonical.
    """
    rule_type = spec.rule_type_hint

    eligibility: list[FeaturePredicate] = []
    entry: list[FeaturePredicate] = []

    # Add cap-tier-aware liquidity floor (every cell has this).
    if spec.cap_tier == "Large":
        liquidity_floor = Decimal("16.5")  # log of ~14.7Cr median TV
    elif spec.cap_tier == "Mid":
        liquidity_floor = Decimal("15.5")
    else:
        liquidity_floor = Decimal("14.0")
    eligibility.append(
        FeaturePredicate(
            feature="log_med_tv_60d",
            cmp=">=",
            value=liquidity_floor,
        )
    )

    # Per-archetype entry conditions.
    if rule_type == "pullback":
        entry.append(
            FeaturePredicate(
                feature="rs_residual_6m",
                cmp="in_top_quantile",
                value=Decimal("1"),
                value_quantile_n=2,  # top half
            )
        )
        entry.append(
            FeaturePredicate(
                feature="formation_max_dd",
                cmp="in_range",
                value=(Decimal("-0.15"), Decimal("-0.05")),
            )
        )
    elif rule_type == "severely_broken":
        entry.append(
            FeaturePredicate(
                feature="rs_residual_6m",
                cmp="<",
                value=Decimal("0"),
            )
        )
        entry.append(
            FeaturePredicate(
                feature="formation_max_dd",
                cmp="<",
                value=Decimal("-0.25"),
            )
        )
    elif rule_type == "emerging":
        entry.append(
            FeaturePredicate(
                feature="rs_residual_6m",
                cmp="<",
                value=Decimal("0"),
            )
        )
        entry.append(
            FeaturePredicate(
                feature="formation_max_dd",
                cmp="in_range",
                value=(Decimal("-0.10"), Decimal("0")),
            )
        )
    elif rule_type == "topping":
        entry.append(
            FeaturePredicate(
                feature="rs_residual_6m",
                cmp="in_top_quantile",
                value=Decimal("1"),
                value_quantile_n=2,
            )
        )
        entry.append(
            FeaturePredicate(
                feature="formation_max_dd",
                cmp=">=",
                value=Decimal("-0.03"),
            )
        )

    rule = CellRule(
        rule_type=rule_type,  # type: ignore[arg-type]
        eligibility=eligibility,
        entry=entry,
        tier=spec.cap_tier,
        action=spec.action,
        tenure=spec.tenure,
        rule_version=1,
        methodology_lock_ref=METHODOLOGY_LOCK_REF,
        notes=f"v6 Phase 0.5g discovery — synthetic-mode-validated cell ({spec.rule_type_hint})",
    )
    return rule.model_dump(mode="json")


def _percentile(series: pd.Series, pct: float) -> Decimal | None:
    s = series.dropna()
    if len(s) == 0:
        return None
    val = float(s.quantile(pct))
    return Decimal(str(round(val, 6)))


def _action_validates(action: str, friction_adjusted: Decimal) -> bool:
    """Friction-adjusted excess must be RIGHT-SIGNED for the action.

    POSITIVE cells must have positive friction-adjusted excess (long
    edge survives cost). NEGATIVE cells must have negative friction-
    adjusted excess (short / avoid edge survives cost).
    """
    if action == "POSITIVE":
        return friction_adjusted > Decimal("0")
    return friction_adjusted < Decimal("0")


# ---------------------------------------------------------------------------
# WalkForwardSweep — the engine itself.
# ---------------------------------------------------------------------------


class WalkForwardSweep:
    """The 24-cell matrix sweep engine.

    Construct with a data-source mode (``synthetic`` for the deterministic
    end-to-end pipeline test; ``cache``/``supabase``/``ec2`` for real-data
    modes still to be wired). Optionally pass a SQLAlchemy ``db_engine``
    for persistence; pass ``None`` for dry-run.

    Typical usage::

        sweep = WalkForwardSweep(mode="synthetic")
        result = sweep.run_full_matrix()
        sweep.persist(result)  # no-op when db_engine is None
    """

    def __init__(
        self,
        mode: str = "synthetic",
        *,
        db_engine: Engine | None = None,
        windows: tuple[WalkForwardWindow, ...] = DEFAULT_WINDOWS,
        synthetic_seed: int = _SYNTHETIC_SEED,
        cache_dir: Path | None = None,
    ) -> None:
        if mode not in {"synthetic", "cache", "supabase", "ec2"}:
            raise ValueError(f"unknown mode={mode!r} (allowed: synthetic, cache, supabase, ec2)")
        self.mode = mode
        self.db_engine = db_engine
        self.windows = windows
        self.synthetic_seed = synthetic_seed
        # Resolve cache_dir at construction so monkeypatching
        # DEFAULT_CACHE_DIR at test time works for the default path.
        self.cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
        self._universe: pd.DataFrame | None = None
        self._nifty500: pd.Series | None = None

    # ---- data loading --------------------------------------------------

    def _load_cache(self) -> pd.DataFrame:
        """Load + shape cache OHLCV into engine-compatible universe.

        Stashes the benchmark series in ``self._nifty500`` as a side effect
        for future use; the engine currently uses cross-sectional means
        instead of nifty500 directly.

        Raises FileNotFoundError if cache pickles are missing.
        """
        ohlcv, nifty500, blacklist = _load_cache_files(self.cache_dir)
        self._nifty500 = nifty500
        log.info(
            "cache_loaded",
            ohlcv_rows=len(ohlcv),
            iids=int(ohlcv["iid"].nunique()),
            date_min=str(ohlcv["date"].min()),
            date_max=str(ohlcv["date"].max()),
            blacklist_count=len(blacklist),
        )
        universe = _build_cache_universe(ohlcv, blacklist)
        log.info(
            "cache_universe_built",
            rows=len(universe),
            instruments=int(universe["instrument_id"].nunique()),
            cap_tier_counts={
                k: int(v) for k, v in universe["cap_tier"].value_counts().to_dict().items()
            },
        )
        return universe

    def _load_universe(self) -> pd.DataFrame:
        if self._universe is not None:
            return self._universe
        if self.mode == "synthetic":
            self._universe = _generate_synthetic_universe(seed=self.synthetic_seed)
            return self._universe
        if self.mode == "cache":
            self._universe = self._load_cache()
            return self._universe
        if self.mode == "supabase":
            raise NotImplementedError(
                "mode='supabase' requires de_equity_ohlcv read via the Supabase "
                "MCP client. Wire mcp__plugin_supabase_supabase__query (or the "
                "direct supabase-py client with SERVICE_ROLE creds) before "
                "running. For pipeline validation use mode='synthetic'."
            )
        # mode == 'ec2'
        raise NotImplementedError(
            "mode='ec2' requires SSH access to jsl-wealth-server + EC2 psql "
            "credentials. Lift the v5 walk-forward SSH-tunnel pattern from "
            "scripts/rs_phase3f_sweep_and_avoid12m.py. For pipeline "
            "validation use mode='synthetic'."
        )

    # ---- per-cell discovery -------------------------------------------

    def discover_cell(self, spec: CellSpec) -> CellDiscoveryResult:
        """Run walk-forward discovery for one cell spec.

        Pipeline:
          1. Filter universe by cap_tier.
          2. Compute state features (RS, drawdown).
          3. Derive entry mask from rule_type_hint.
          4. Compute forward returns at the tenure's horizon.
          5. Compute IC, percentile dist, friction-adjusted excess.
          6. Apply per-tenure IC floor + action-sign check.
          7. Build rule_dsl if validated.
        """
        run_id = uuid.uuid4()
        log.info(
            "discover_cell_start",
            cap_tier=spec.cap_tier,
            tenure=spec.tenure,
            action=spec.action,
            rule_type_hint=spec.rule_type_hint,
            run_id=str(run_id),
        )

        universe = self._load_universe()
        subset = _filter_universe_by_cap(universe, spec.cap_tier)
        if subset.empty:
            return self._no_conviction(spec, run_id, n_obs=0, notes="empty cap-tier subset")

        state_df = _compute_state_features(subset)

        # Restrict to walk-forward TEST windows (we discover on OOS).
        test_mask = pd.Series(False, index=state_df.index)
        for win in self.windows:
            test_mask |= (state_df["date"] >= win.test_start) & (state_df["date"] <= win.test_end)
        state_df = state_df[test_mask].reset_index(drop=True)
        if state_df.empty:
            return self._no_conviction(
                spec, run_id, n_obs=0, notes="no rows in walk-forward test windows"
            )

        # Forward returns at the tenure's horizon.
        horizon = TENURE_TO_HORIZON_DAYS[spec.tenure]
        # Recompute over the full (sorted) cap-tier subset, then re-filter.
        sorted_subset = _compute_state_features(subset)
        sorted_subset = sorted_subset.sort_values(["instrument_id", "date"]).reset_index(drop=True)
        fwd = _compute_forward_returns(sorted_subset, horizon)
        bench = _compute_universe_forward_returns(sorted_subset, horizon)
        excess = fwd - bench
        sorted_subset = sorted_subset.assign(_fwd_excess=excess.values)

        # Re-filter sorted_subset to the test windows.
        date_mask = sorted_subset["date"].between(
            self.windows[0].test_start, self.windows[-1].test_end
        )
        sorted_subset = sorted_subset.loc[date_mask].reset_index(drop=True)

        entry_mask = _derive_entry_mask(sorted_subset, spec.rule_type_hint, spec.action)
        triggers = sorted_subset.loc[entry_mask].copy()

        # IC is computed across ALL observations in the test window
        # (not just triggers) — using a continuous score we build from
        # the rule's archetype. We turn the boolean entry into a soft
        # score by combining RS rank and (signed) drawdown.
        score = sorted_subset["rs_rank_pct"].astype(float)
        if spec.rule_type_hint in {"severely_broken", "emerging"}:
            score = -score  # NEGATIVE archetypes invert the RS sign
        excess_series: pd.Series = sorted_subset["_fwd_excess"]
        ic = _compute_ic(sorted_subset, score, excess_series)

        # TP/TN rate + percentile distribution from TRIGGER set excess.
        trigger_excess: pd.Series = triggers["_fwd_excess"].dropna()
        n_obs = len(trigger_excess)
        if n_obs < 30:
            return self._no_conviction(
                spec,
                run_id,
                n_obs=n_obs,
                ic=ic,
                notes=f"insufficient triggers: {n_obs} < 30",
            )

        median_excess = Decimal(str(round(float(trigger_excess.median()), 6)))
        # Confusion-matrix rate per action.
        if spec.action == "POSITIVE":
            tp_rate = Decimal(str(round(float((trigger_excess > 0).sum() / n_obs), 4)))
            tn_rate = None
        else:
            tp_rate = None
            tn_rate = Decimal(str(round(float((trigger_excess < 0).sum() / n_obs), 4)))

        friction = DEFAULT_FRICTION_BY_TIER[spec.cap_tier]
        # Round-trip friction = 2 * one-way friction.
        round_trip = friction * Decimal("2")
        if spec.action == "POSITIVE":
            friction_adjusted = median_excess - round_trip
        else:
            friction_adjusted = median_excess + round_trip

        p10 = _percentile(trigger_excess, 0.10)
        p25 = _percentile(trigger_excess, 0.25)
        p50 = _percentile(trigger_excess, 0.50)
        p75 = _percentile(trigger_excess, 0.75)
        p90 = _percentile(trigger_excess, 0.90)

        # Apply per-tenure IC floor + action-sign check.
        floor = PER_TENURE_IC_FLOOR[spec.tenure]
        ic_abs = abs(ic) if ic is not None else Decimal("0")
        validated = (
            ic is not None and ic_abs >= floor and _action_validates(spec.action, friction_adjusted)
        )

        if validated:
            rule_dsl = _build_rule_dsl(spec)
            stable_features = ["rs_residual_6m", "formation_max_dd"]
            notes = (
                f"validated: |IC|={ic_abs} >= floor={floor}; "
                f"friction_adjusted={friction_adjusted} signed for {spec.action}"
            )
        else:
            rule_dsl = {}
            stable_features = []
            reason = []
            if ic is None or ic_abs < floor:
                reason.append(f"IC {ic} below floor {floor}")
            if not _action_validates(spec.action, friction_adjusted):
                reason.append(
                    f"friction_adjusted_excess {friction_adjusted} wrong sign for {spec.action}"
                )
            notes = "no_conviction: " + "; ".join(reason)

        log.info(
            "discover_cell_done",
            cap_tier=spec.cap_tier,
            tenure=spec.tenure,
            action=spec.action,
            validated=validated,
            ic=str(ic),
            n_obs=n_obs,
            friction_adjusted=str(friction_adjusted),
            run_id=str(run_id),
        )

        return CellDiscoveryResult(
            spec=spec,
            validated=validated,
            ic=ic,
            tp_rate=tp_rate,
            tn_rate=tn_rate,
            median_excess=median_excess,
            friction_adjusted_excess=friction_adjusted,
            percentile_10=p10,
            percentile_25=p25,
            percentile_50=p50,
            percentile_75=p75,
            percentile_90=p90,
            n_observations=n_obs,
            stable_features=stable_features,
            rule_dsl=rule_dsl,
            walkforward_run_id=run_id,
            notes=notes,
        )

    def _no_conviction(
        self,
        spec: CellSpec,
        run_id: uuid.UUID,
        n_obs: int,
        *,
        ic: Decimal | None = None,
        notes: str = "no_conviction",
    ) -> CellDiscoveryResult:
        return CellDiscoveryResult(
            spec=spec,
            validated=False,
            ic=ic,
            tp_rate=None,
            tn_rate=None,
            median_excess=None,
            friction_adjusted_excess=None,
            percentile_10=None,
            percentile_25=None,
            percentile_50=None,
            percentile_75=None,
            percentile_90=None,
            n_observations=n_obs,
            stable_features=[],
            rule_dsl={},
            walkforward_run_id=run_id,
            notes=notes,
        )

    # ---- full matrix sweep --------------------------------------------

    def _rule_type_for(self, tenure: str, action: str) -> str:
        """Default rule_type_hint mapping per (tenure, action)."""
        if action == "POSITIVE":
            if tenure in {"6m", "12m"}:
                return "pullback"
            return "emerging"
        # NEGATIVE
        if tenure in {"6m", "12m"}:
            return "severely_broken"
        return "topping"

    def run_full_matrix(self) -> SweepResult:
        """Run :meth:`discover_cell` for all 24 (cap × tenure × action) cells.

        Returns a :class:`SweepResult` with all per-cell results in stable
        order: outer loop cap_tier (Small, Mid, Large), middle loop tenure
        (1m, 3m, 6m, 12m), inner loop action (POSITIVE, NEGATIVE).
        """
        started = datetime.now(UTC)
        results: list[CellDiscoveryResult] = []
        for cap_tier in CAP_TIERS:
            for tenure in TENURES:
                for action in ACTIONS:
                    spec = CellSpec(
                        cap_tier=cap_tier,
                        tenure=tenure,
                        action=action,
                        rule_type_hint=self._rule_type_for(tenure, action),
                    )
                    results.append(self.discover_cell(spec))
        completed = datetime.now(UTC)

        return SweepResult(
            results=tuple(results),
            run_started_at=started,
            run_completed_at=completed,
            mode=self.mode,
            windows=self.windows,
        )

    # ---- persistence ---------------------------------------------------

    def persist(self, result: SweepResult) -> None:
        """Persist a SweepResult to the v6 DB tables.

        Inserts:
          * One row into ``atlas_cell_walkforward_runs`` per cell result
            (the audit row — every attempt, whether validated or not).
          * One row into ``atlas_cell_definitions`` per VALIDATED cell.
            ``no_conviction`` cells are NOT persisted as cell definitions.

        No-op when ``self.db_engine is None`` (dry-run path).
        """
        if self.db_engine is None:
            log.info(
                "persist_skipped_no_engine",
                results=len(result.results),
                validated=result.validated_count,
            )
            return

        snapshot_id = uuid.uuid4()  # placeholder; FK to atlas_universe_snapshot future
        with self.db_engine.connect() as conn:
            for cell_result in result.results:
                self._insert_walkforward_run(
                    conn,
                    cell_result,
                    snapshot_id=snapshot_id,
                    windows=result.windows,
                )
                if cell_result.validated:
                    self._insert_cell_definition(conn, cell_result)
            conn.commit()
        log.info(
            "persist_complete",
            walkforward_rows=len(result.results),
            cell_definition_rows=result.validated_count,
        )

    def _insert_walkforward_run(
        self,
        conn: Any,
        cell_result: CellDiscoveryResult,
        *,
        snapshot_id: uuid.UUID,
        windows: tuple[WalkForwardWindow, ...],
    ) -> None:
        # Use the FULL spanned window: train_start of first, test_end of last.
        first = windows[0]
        last = windows[-1]
        stable_features_json = cell_result.stable_features if cell_result.stable_features else None
        params = {
            "run_id": str(cell_result.walkforward_run_id),
            "universe_snapshot_id": str(snapshot_id),
            "tenure": cell_result.spec.tenure,
            "cell_id": None,  # discovered cells: cell_id assigned on cell_definitions insert
            "window_train_start": first.train_start,
            "window_train_end": first.train_end,
            "window_test_start": first.test_start,
            "window_test_end": last.test_end,
            "tp_rate": cell_result.tp_rate,
            "tn_rate": cell_result.tn_rate,
            "median_excess": cell_result.median_excess,
            "mean_excess": cell_result.median_excess,  # we don't compute mean separately
            "friction_adjusted_excess": cell_result.friction_adjusted_excess,
            "percentile_10": cell_result.percentile_10,
            "percentile_25": cell_result.percentile_25,
            "percentile_50": cell_result.percentile_50,
            "percentile_75": cell_result.percentile_75,
            "percentile_90": cell_result.percentile_90,
            "n_observations": cell_result.n_observations,
            "stable_features": (
                None if stable_features_json is None else _jsonb_dumps(stable_features_json)
            ),
            "methodology_lock_ref": METHODOLOGY_LOCK_REF,
            "status": "completed",
            "notes": cell_result.notes,
        }
        conn.execute(
            text(
                """
                INSERT INTO atlas.atlas_cell_walkforward_runs (
                    run_id, run_completed_at, universe_snapshot_id, tenure,
                    cell_id, window_train_start, window_train_end,
                    window_test_start, window_test_end,
                    tp_rate, tn_rate, median_excess, mean_excess,
                    friction_adjusted_excess,
                    percentile_10, percentile_25, percentile_50,
                    percentile_75, percentile_90,
                    n_observations, stable_features,
                    methodology_lock_ref, status, notes
                ) VALUES (
                    :run_id, NOW(), :universe_snapshot_id, :tenure,
                    :cell_id, :window_train_start, :window_train_end,
                    :window_test_start, :window_test_end,
                    :tp_rate, :tn_rate, :median_excess, :mean_excess,
                    :friction_adjusted_excess,
                    :percentile_10, :percentile_25, :percentile_50,
                    :percentile_75, :percentile_90,
                    :n_observations, CAST(:stable_features AS JSONB),
                    :methodology_lock_ref, :status, :notes
                )
                """
            ),
            params,
        )

    def _insert_cell_definition(self, conn: Any, cell_result: CellDiscoveryResult) -> None:
        params = {
            "cap_tier": cell_result.spec.cap_tier,
            "action": cell_result.spec.action,
            "tenure": cell_result.spec.tenure,
            "rule_dsl": _jsonb_dumps(cell_result.rule_dsl),
            "confidence_unconditional": (
                cell_result.tp_rate
                if cell_result.spec.action == "POSITIVE"
                else cell_result.tn_rate
            ),
            "friction_adjusted_excess": cell_result.friction_adjusted_excess,
            "stable_features": _jsonb_dumps(cell_result.stable_features),
            "methodology_lock_ref": METHODOLOGY_LOCK_REF,
            "walkforward_run_id": str(cell_result.walkforward_run_id),
        }
        conn.execute(
            text(
                """
                INSERT INTO atlas.atlas_cell_definitions (
                    cap_tier, action, tenure, rule_dsl,
                    confidence_unconditional, friction_adjusted_excess,
                    stable_features, methodology_lock_ref,
                    walkforward_run_id, validated_at
                ) VALUES (
                    :cap_tier, :action, :tenure, CAST(:rule_dsl AS JSONB),
                    :confidence_unconditional, :friction_adjusted_excess,
                    CAST(:stable_features AS JSONB), :methodology_lock_ref,
                    :walkforward_run_id, NOW()
                )
                """
            ),
            params,
        )


def _jsonb_dumps(obj: Any) -> str:
    """Serialise a python object to a JSONB-acceptable string.

    Decimal values are coerced to strings (Postgres JSONB accepts numeric
    strings) so we preserve precision.
    """
    import json

    def _default(o: Any) -> Any:
        if isinstance(o, Decimal):
            # Use string to preserve precision; downstream consumers
            # cast back via Decimal.
            return str(o)
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, date | datetime):
            return o.isoformat()
        raise TypeError(f"cannot serialise {type(o).__name__}")

    return json.dumps(obj, default=_default, sort_keys=True)
