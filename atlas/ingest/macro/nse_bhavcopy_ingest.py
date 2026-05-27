"""NSE FII/DII Daily Activity ingest.

**Historical backfill status: BLOCKED**

Source investigation (2026-05-27):
  - archives.nseindia.com/content/fo/all_foii_dii.csv: HTTP 404 (EC2 confirmed)
  - nseindia.com/api/historicalOR/foCash/historicalcontract: HTTP 404
  - nseindia.com/api/fiidiiTradeReact: HTTP 200 but returns today's 2 rows only;
    date params are ignored; NSE home page returns 403 (bot-block)
  - Moneycontrol pricefeed/fii_dii: empty response
  - BSE API: connection timeout
  - NSDL: connection error

All attempted historical data sources are unreachable from automated scripts.
NSE's anti-bot measures block server-side session establishment.

**Current behavior:**
  - Incremental mode (nightly): fetches today's FII/DII from fiidiiTradeReact API
  - Backfill mode: returns 0 (no historical source available)
  - fii_cash_equity_flow_cr and dii_flow will remain NULL for historical rows

Populates (incremental only):
  atlas.atlas_macro_daily.fii_cash_equity_flow_cr  — FII net (Buy - Sell), ₹ Crore
  atlas.atlas_macro_daily.dii_flow                 — DII net (Buy - Sell), ₹ Crore

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

# NSE FII/DII current-day API (returns today's 2 rows: FII and DII)
# No historical params honored. Used for incremental/nightly updates only.
_NSE_FII_DII_REACT_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/market-data/fii-dii-activity",
}

# Legacy URL — 404 as of 2026-05-27. Retained for reference only.
_NSE_FII_DII_LEGACY_URL = "https://archives.nseindia.com/content/fo/all_foii_dii.csv"


def fetch_fii_dii_today() -> pd.DataFrame:
    """Fetch today's FII and DII net flows from NSE React API.

    Returns current day's FII and DII data only. Historical data is not
    available via this endpoint.

    Returns:
        DataFrame with columns ["date", "fii_net_cr", "dii_net_cr"].
        Returns empty DataFrame if API fails or returns unexpected format.

    Response shape:
        [
          {"buyValue": "15536.74", "category": "DII", "date": "26-May-2026",
           "netValue": "1361.43", "sellValue": "14175.31"},
          {"buyValue": "13127.02", "category": "FII/FPI", "date": "26-May-2026",
           "netValue": "-2407.87", "sellValue": "15534.89"}
        ]
    """
    try:
        r = requests.get(_NSE_FII_DII_REACT_URL, headers=_NSE_HEADERS, timeout=30)
        r.raise_for_status()
        records = r.json()
    except Exception as exc:
        log.error("nse_fii_dii_fetch_error", error=str(exc))
        return pd.DataFrame(columns=["date", "fii_net_cr", "dii_net_cr"])

    if not isinstance(records, list) or len(records) == 0:
        log.warning("nse_fii_dii_unexpected_response", records=records)
        return pd.DataFrame(columns=["date", "fii_net_cr", "dii_net_cr"])

    fii_net: float | None = None
    dii_net: float | None = None
    date_str: str | None = None

    for rec in records:
        category = str(rec.get("category", "")).upper()
        raw_date = str(rec.get("date", "")).strip()
        net_val_str = str(rec.get("netValue", "")).replace(",", "")

        # Parse date (format: "26-May-2026")
        if date_str is None and raw_date:
            try:
                date_str = pd.to_datetime(raw_date, format="%d-%b-%Y").strftime("%Y-%m-%d")
            except Exception:
                pass

        try:
            net_val = float(net_val_str)
        except (ValueError, TypeError):
            continue

        if "FII" in category or "FPI" in category:
            fii_net = net_val
        elif "DII" in category:
            dii_net = net_val

    if date_str is None or fii_net is None or dii_net is None:
        log.warning(
            "nse_fii_dii_incomplete",
            date=date_str,
            fii_net=fii_net,
            dii_net=dii_net,
        )
        return pd.DataFrame(columns=["date", "fii_net_cr", "dii_net_cr"])

    df = pd.DataFrame([{"date": date_str, "fii_net_cr": fii_net, "dii_net_cr": dii_net}])
    log.info("nse_fii_dii_fetched", date=date_str, fii_net_cr=fii_net, dii_net_cr=dii_net)
    return df


def fetch_fii_dii_csv(
    url: str = _NSE_FII_DII_LEGACY_URL,
    dest_dir: str | None = None,
) -> str:
    """Download NSE FII/DII historical CSV to a local file.

    DEPRECATED: The legacy URL (all_foii_dii.csv) returns 404 as of 2026-05-27.
    This method is retained for backward compatibility with tests that use
    fixture CSV files by passing a local file URL.

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
    """Upsert FII/DII flows into atlas_macro_daily.

    Historical backfill: NOT AVAILABLE (all NSE archive URLs are 404).
    Incremental mode: fetches today's FII/DII from NSE React API.

    If csv_path is provided (test fixture): parses and upserts that CSV.
    Otherwise: fetches today's data only via fetch_fii_dii_today().

    Args:
        start:    Earliest date to keep (ISO "YYYY-MM-DD"). Earlier rows dropped.
                  Only relevant when using csv_path.
        engine:   Optional engine override.
        csv_path: Override: use local fixture CSV instead of NSE API.
                  Intended for tests only.

    Returns:
        Number of rows upserted (0 for backfill without csv_path).
    """
    if csv_path is not None:
        # Test / manual path: parse provided CSV
        df = parse_fii_dii_csv(csv_path)
        if not df.empty:
            df = df[df["date"] >= start]
            log.info("fii_dii_filtered", start=start, rows_after_filter=len(df))
        return upsert_fii_dii(df, engine=engine)

    # Production path: fetch today's data only
    log.info(
        "fii_dii_historical_unavailable",
        message=(
            "NSE archives all_foii_dii.csv is 404. Historical FII/DII backfill "
            "is BLOCKED. Fetching today's data only via NSE React API."
        ),
    )
    df_today = fetch_fii_dii_today()
    return upsert_fii_dii(df_today, engine=engine)
