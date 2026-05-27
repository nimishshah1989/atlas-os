#!/usr/bin/env python3
"""Export daily OHLCV for all benchmark + sector/thematic indices to CSV.

Categories included: broad (benchmarks), sectoral, thematic.
Category excluded: strategy (factor/smart-beta indices).

Output columns: date, index_code, index_name, category, open, high, low, close, volume

Usage:
    python3 scripts/export_index_ohlcv.py
    python3 scripts/export_index_ohlcv.py --out /tmp/index_ohlcv.csv
    python3 scripts/export_index_ohlcv.py --categories broad sectoral
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CATEGORIES = ("broad", "sectoral", "thematic")
DEFAULT_OUT = ROOT / "output" / "index_ohlcv.csv"


def get_engine() -> sa.Engine:
    try:
        from atlas.config import Config

        return sa.create_engine(Config.assert_db_url(), pool_pre_ping=True)
    except Exception:
        url = os.environ.get("DATABASE_URL")
        if not url:
            sys.exit("DATABASE_URL not set and atlas.config unavailable")
        return sa.create_engine(url, pool_pre_ping=True)


def export(categories: tuple[str, ...], out: Path) -> None:
    engine = get_engine()

    placeholders = ", ".join(f"'{c}'" for c in categories)

    query = sa.text(f"""
        SELECT
            p.date,
            p.index_code,
            m.index_name,
            m.category,
            p.open,
            p.high,
            p.low,
            p.close,
            p.volume
        FROM public.de_index_prices p
        JOIN public.de_index_master m ON m.index_code = p.index_code
        WHERE m.category IN ({placeholders})
        ORDER BY m.category, p.index_code, p.date
    """)

    print(f"Querying categories: {list(categories)} ...")
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    rows = len(df)
    indices = df["index_code"].nunique()
    min_date = df["date"].min()
    max_date = df["date"].max()

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    print(f"Exported {rows:,} rows | {indices} indices | {min_date} → {max_date}")
    print(f"Saved to: {out}")

    # Print summary by category
    summary = df.groupby("category")["index_code"].nunique()
    print("\nIndices by category:")
    for cat, count in summary.items():
        print(f"  {cat:<12} {count:>3} indices")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--categories",
        nargs="+",
        default=list(DEFAULT_CATEGORIES),
        help="Categories to include (default: broad sectoral thematic)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output CSV path (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args()
    export(tuple(args.categories), args.out)


if __name__ == "__main__":
    main()
