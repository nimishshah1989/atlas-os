"""Tier 4 cross-table consistency validation.

Per ``docs/03_VALIDATION_FRAMEWORK.md`` (M3 extension): cross-table checks
that confirm aggregate tables are reconcilable to their source data.

Two checks today:

* ``validate_bottomup_reconstruction`` — for N sampled (sector, date) pairs,
  recompute the bottom-up weighted-mean from the raw stock metrics and
  compare to what's stored in ``atlas_sector_metrics_daily``.
* ``validate_breadth_reconstruction`` — for N sampled (sector, date) pairs,
  recompute ``participation_50`` from raw stock data and compare to stored.

Both checks read from the DB via :func:`open_compute_session`, sample with
a fixed seed for reproducibility, and emit per-row mismatches into the
returned report. The overall return code follows the same pattern as
:mod:`atlas.validation.m1_data_quality`: 0 = ok, 1 = warnings, 2 = critical.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()


# Tolerance is relative to max(|stored|, 1). Loose enough to absorb numeric
# noise from float64 rolling/groupby reductions; tight enough to catch any
# real drift between bottom-up SQL aggregation and the in-memory computation.
TOLERANCE_REL = 5e-3


@dataclass
class Mismatch:
    sector_name: str
    date: str
    metric: str
    stored: float
    recomputed: float
    abs_diff: float


@dataclass
class Tier4Report:
    started_at: datetime = field(default_factory=datetime.now)
    sample_size: int = 0
    mismatches: list[Mismatch] = field(default_factory=list)
    note: str = ""

    def exit_code(self) -> int:
        if not self.mismatches:
            return 0
        # Treat any mismatch outside tolerance as a warning by default; the
        # caller may choose to escalate when sample_size is small.
        return 1


# --------------------------------------------------------------------------- #
# Sampling                                                                    #
# --------------------------------------------------------------------------- #


def _sample_sector_dates(
    engine: Engine,
    n: int = 30,
    seed: int = 42,
) -> pd.DataFrame:
    """Pick N (sector_name, date) tuples uniformly at random from the
    materialised sector metrics table. Returns an empty frame if the table
    is empty (typical pre-backfill state)."""
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT sector_name, date
            FROM atlas.atlas_sector_metrics_daily
            ORDER BY date DESC
            LIMIT 5000
            """,
            conn,
        )
    if df.empty:
        return df
    return df.sample(n=min(n, len(df)), random_state=seed).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Bottom-up reconstruction                                                    #
# --------------------------------------------------------------------------- #


def validate_bottomup_reconstruction(
    engine: Engine | None = None,
    n: int = 30,
    seed: int = 42,
) -> Tier4Report:
    """Recompute ``bottomup_ret_3m`` for N sampled (sector, date) pairs and
    compare to stored.

    Reads stock-level metrics for each sample, applies the same traded-value
    weighted mean (``avg_volume_20 * close_approx``), and reports any
    mismatch beyond ``TOLERANCE_REL``.
    """
    eng = engine or get_engine()
    samples = _sample_sector_dates(eng, n=n, seed=seed)
    report = Tier4Report(sample_size=len(samples))

    if samples.empty:
        report.note = "atlas_sector_metrics_daily empty — skipping reconstruction check"
        return report

    with open_compute_session(eng) as conn:
        for _, sample in samples.iterrows():
            sector = sample["sector_name"]
            d = sample["date"]

            stored_row = pd.read_sql(
                """
                SELECT bottomup_ret_3m
                FROM atlas.atlas_sector_metrics_daily
                WHERE sector_name = %(sector)s AND date = %(d)s
                """,
                conn,
                params={"sector": sector, "d": d},
            )
            if stored_row.empty:
                continue
            stored_val = float(stored_row.iloc[0]["bottomup_ret_3m"])

            stocks = pd.read_sql(
                """
                SELECT
                    m.instrument_id,
                    m.ema_200_stock,
                    m.extension_pct,
                    m.avg_volume_20,
                    m.ret_3m
                FROM atlas.atlas_stock_metrics_daily m
                JOIN atlas.atlas_universe_stocks u
                    ON u.instrument_id = m.instrument_id
                    AND u.effective_to IS NULL
                WHERE u.sector = %(sector)s AND m.date = %(d)s
                """,
                conn,
                params={"sector": sector, "d": d},
            )
            if stocks.empty:
                continue

            stocks["close_approx"] = stocks["ema_200_stock"].astype(float) * (
                1.0 + stocks["extension_pct"].astype(float)
            )
            stocks["weight"] = stocks["avg_volume_20"].astype(float) * stocks["close_approx"]

            # NaN-safe weighted mean.
            v = pd.to_numeric(stocks["ret_3m"], errors="coerce")
            w = stocks["weight"]
            mask = v.notna() & w.notna() & (w > 0)
            if not mask.any():
                continue
            recomputed = float(np.average(v[mask], weights=w[mask]))

            denom = max(abs(stored_val), 1.0)
            abs_diff = abs(recomputed - stored_val)
            if abs_diff / denom > TOLERANCE_REL:
                report.mismatches.append(
                    Mismatch(
                        sector_name=sector,
                        date=str(d),
                        metric="bottomup_ret_3m",
                        stored=stored_val,
                        recomputed=recomputed,
                        abs_diff=abs_diff,
                    )
                )

    log.info(
        "tier4_bottomup_reconstruction_complete",
        sampled=report.sample_size,
        mismatches=len(report.mismatches),
    )
    return report


# --------------------------------------------------------------------------- #
# Breadth reconstruction                                                      #
# --------------------------------------------------------------------------- #


def validate_breadth_reconstruction(
    engine: Engine | None = None,
    n: int = 30,
    seed: int = 42,
) -> Tier4Report:
    """Recompute ``participation_50`` for N sampled (sector, date) pairs.

    For each sample, count stocks in the sector where
    ``close_approx > ema_50_stock`` (NULL-safe) and compare to the stored
    fraction.
    """
    eng = engine or get_engine()
    samples = _sample_sector_dates(eng, n=n, seed=seed)
    report = Tier4Report(sample_size=len(samples))

    if samples.empty:
        report.note = "atlas_sector_metrics_daily empty — skipping breadth check"
        return report

    with open_compute_session(eng) as conn:
        for _, sample in samples.iterrows():
            sector = sample["sector_name"]
            d = sample["date"]

            stored_row = pd.read_sql(
                """
                SELECT participation_50
                FROM atlas.atlas_sector_metrics_daily
                WHERE sector_name = %(sector)s AND date = %(d)s
                """,
                conn,
                params={"sector": sector, "d": d},
            )
            if stored_row.empty or stored_row.iloc[0]["participation_50"] is None:
                continue
            stored_val = float(stored_row.iloc[0]["participation_50"])

            stocks = pd.read_sql(
                """
                SELECT
                    m.ema_200_stock,
                    m.extension_pct,
                    m.ema_50_stock
                FROM atlas.atlas_stock_metrics_daily m
                JOIN atlas.atlas_universe_stocks u
                    ON u.instrument_id = m.instrument_id
                    AND u.effective_to IS NULL
                WHERE u.sector = %(sector)s AND m.date = %(d)s
                """,
                conn,
                params={"sector": sector, "d": d},
            )
            if stocks.empty:
                continue
            stocks["close_approx"] = stocks["ema_200_stock"].astype(float) * (
                1.0 + stocks["extension_pct"].astype(float)
            )
            valid = stocks.dropna(subset=["close_approx", "ema_50_stock"])
            if valid.empty:
                continue
            recomputed = float((valid["close_approx"] > valid["ema_50_stock"]).mean())

            denom = max(abs(stored_val), 1.0)
            abs_diff = abs(recomputed - stored_val)
            if abs_diff / denom > TOLERANCE_REL:
                report.mismatches.append(
                    Mismatch(
                        sector_name=sector,
                        date=str(d),
                        metric="participation_50",
                        stored=stored_val,
                        recomputed=recomputed,
                        abs_diff=abs_diff,
                    )
                )

    log.info(
        "tier4_breadth_reconstruction_complete",
        sampled=report.sample_size,
        mismatches=len(report.mismatches),
    )
    return report


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tier 4 cross-table consistency checks for M3 sector outputs."
    )
    parser.add_argument("--n", type=int, default=30, help="Sample size per check")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    bu_report = validate_bottomup_reconstruction(n=args.n, seed=args.seed)
    breadth_report = validate_breadth_reconstruction(n=args.n, seed=args.seed)

    print(
        f"[bottomup_reconstruction] sampled={bu_report.sample_size} "
        f"mismatches={len(bu_report.mismatches)}"
    )
    print(
        f"[breadth_reconstruction]  sampled={breadth_report.sample_size} "
        f"mismatches={len(breadth_report.mismatches)}"
    )
    for m in bu_report.mismatches + breadth_report.mismatches:
        print(
            f"  ! {m.sector_name} {m.date} {m.metric}: "
            f"stored={m.stored:.6f} recomputed={m.recomputed:.6f} "
            f"diff={m.abs_diff:.6f}"
        )

    return max(bu_report.exit_code(), breadth_report.exit_code())


if __name__ == "__main__":
    raise SystemExit(main())
