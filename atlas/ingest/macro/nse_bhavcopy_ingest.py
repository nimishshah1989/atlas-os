"""NSE FII/DII Historical Activity ingest.

Source:
  NSE archives FII/DII CSV — Historical Activity summary.
  URL: https://archives.nseindia.com/content/fo/all_foii_dii.csv
  (Single file with full history from ~2007; no auth required but NSE
   requires a User-Agent and Referer header to avoid bot-blocks.)

Populates:
  atlas.atlas_macro_daily.fii_cash_equity_flow_cr  — FII net (Buy - Sell), ₹ Crore
  atlas.atlas_macro_daily.dii_flow                 — DII net (Buy - Sell), ₹ Crore

CSV format (NSE archive):
  Columns: Date, Buy Value (FII), Sell Value (FII), Net Value (FII),
           Buy Value (DII), Sell Value (DII), Net Value (DII)
  Date format: DD-Mon-YYYY (e.g. "01-Jan-2024")
  Values: ₹ Crore (no further conversion needed)

Note on historical depth:
  NSE all_foii_dii.csv typically starts from 2007. However the atlas scope is
  2016-01-01. Rows before that date are silently ignored during backfill.

All values stored as Decimal. Idempotent upsert on date PK.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pandas as pd
import requests
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

_NSE_FII_DII_URL = "https://archives.nseindia.com/content/fo/all_foii_dii.csv"
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com/",
    "Accept-Encoding": "gzip, deflate, br",
}


def fetch_fii_dii_csv(
    url: str = _NSE_FII_DII_URL,
    dest_dir: str | None = None,
) -> str:
    """Download NSE FII/DII historical CSV to a local file.

    Args:
        url:      Source URL (overridable for tests).
        dest_dir: Directory to write the file. Uses system temp dir if None.

    Returns:
        Absolute path to downloaded CSV file.

    Raises:
        requests.HTTPError: on non-2xx response.
    """
    dest = dest_dir or tempfile.mkdtemp()
    dest_path = os.path.join(dest, "fii_dii_historical.csv")

    with requests.Session() as session:
        resp = session.get(url, headers=_NSE_HEADERS, timeout=60)
        resp.raise_for_status()

        with open(dest_path, "wb") as f:
            f.write(resp.content)

    log.info("fii_dii_csv_downloaded", path=dest_path, size_bytes=len(resp.content))
    return dest_path


def parse_fii_dii_csv(csv_path: str) -> pd.DataFrame:
    """Parse NSE FII/DII CSV into a clean DataFrame.

    Expected columns in source CSV:
      Date | Buy Value | Sell Value | Net Value | Buy Value.1 | Sell Value.1 | Net Value.1
      (first 3 are FII, last 3 are DII — the "Net Value" column is pre-computed
       by NSE but we recompute from Buy/Sell for auditability.)

    Args:
        csv_path: Path to the downloaded CSV file.

    Returns:
        DataFrame with columns: ["date", "fii_net_cr", "dii_net_cr"].
        date is ISO string "YYYY-MM-DD".
        Rows with unparseable dates or values are silently dropped.
    """
    row_count_before = 0
    try:
        df_raw = pd.read_csv(
            csv_path,
            skip_blank_lines=True,
            na_values=["", "-", "N/A"],
        )
        row_count_before = len(df_raw)
    except Exception as exc:
        log.error("fii_dii_csv_parse_error", path=csv_path, error=str(exc))
        return pd.DataFrame(columns=["date", "fii_net_cr", "dii_net_cr"])

    # Drop fully empty rows
    df_raw = df_raw.dropna(how="all")

    # Identify columns by position (NSE format is positional)
    cols = list(df_raw.columns)
    if len(cols) < 7:
        log.warning("fii_dii_unexpected_columns", columns=cols)
        return pd.DataFrame(columns=["date", "fii_net_cr", "dii_net_cr"])

    date_col = cols[0]
    fii_buy_col = cols[1]
    fii_sell_col = cols[2]
    dii_buy_col = cols[4]
    dii_sell_col = cols[5]

    # Parse dates: NSE uses DD-Mon-YYYY (e.g. "01-Jan-2024")
    def _parse_date(raw: str) -> str | None:
        try:
            return pd.to_datetime(str(raw).strip(), format="%d-%b-%Y").strftime("%Y-%m-%d")
        except Exception:
            try:
                return pd.to_datetime(str(raw).strip()).strftime("%Y-%m-%d")
            except Exception:
                return None

    rows = []
    for _, row in df_raw.iterrows():
        date_str = _parse_date(row[date_col])
        if date_str is None:
            continue
        try:
            fii_buy = float(str(row[fii_buy_col]).replace(",", ""))
            fii_sell = float(str(row[fii_sell_col]).replace(",", ""))
            dii_buy = float(str(row[dii_buy_col]).replace(",", ""))
            dii_sell = float(str(row[dii_sell_col]).replace(",", ""))
        except (ValueError, TypeError):
            continue
        rows.append(
            {
                "date": date_str,
                "fii_net_cr": fii_buy - fii_sell,
                "dii_net_cr": dii_buy - dii_sell,
            }
        )

    df = pd.DataFrame(rows)
    log.info(
        "fii_dii_csv_parsed",
        path=csv_path,
        rows_in=row_count_before,
        rows_out=len(df),
    )
    return df


def upsert_fii_dii(
    df: pd.DataFrame,
    engine: Engine | None = None,
) -> int:
    """UPSERT FII + DII flows into atlas_macro_daily.

    Args:
        df:     DataFrame with columns ["date", "fii_net_cr", "dii_net_cr"].
        engine: Optional engine override.

    Returns:
        Number of rows upserted.
    """
    if df.empty:
        log.info("upsert_fii_dii_skipped", reason="empty_dataframe")
        return 0

    eng = engine or get_engine()
    row_count_before = len(df)
    upserted = 0

    with eng.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(
                text(
                    "INSERT INTO atlas.atlas_macro_daily"
                    " (date, fii_cash_equity_flow_cr, dii_flow)"
                    " VALUES (:d, :fii, :dii)"
                    " ON CONFLICT (date) DO UPDATE"
                    " SET fii_cash_equity_flow_cr = EXCLUDED.fii_cash_equity_flow_cr,"
                    "     dii_flow = EXCLUDED.dii_flow"
                ),
                {
                    "d": row["date"],
                    "fii": Decimal(str(round(row["fii_net_cr"], 4))),
                    "dii": Decimal(str(round(row["dii_net_cr"], 4))),
                },
            )
            upserted += 1

    log.info(
        "upsert_fii_dii_done",
        rows_in=row_count_before,
        rows_upserted=upserted,
    )
    return upserted


def run_all(
    start: str = "2016-01-01",
    engine: Engine | None = None,
    csv_path: str | None = None,
) -> int:
    """Download and upsert FII/DII history from NSE.

    Args:
        start:    Earliest date to keep (ISO "YYYY-MM-DD"). Earlier rows dropped.
        engine:   Optional engine override.
        csv_path: Override download path (for testing with local fixture).

    Returns:
        Number of rows upserted.
    """
    path = csv_path or fetch_fii_dii_csv()
    df = parse_fii_dii_csv(path)

    if not df.empty:
        df = df[df["date"] >= start]
        log.info("fii_dii_filtered", start=start, rows_after_filter=len(df))

    return upsert_fii_dii(df, engine=engine)
