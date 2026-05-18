"""D4: NSE F&O ban list daily fetch + upsert.

Endpoint (daily current): https://archives.nseindia.com/content/fo/fo_secban.csv
For backfill, NSE maintains daily files under /content/fo/secban_<DDMMYYYY>.csv.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


@dataclass
class FnoBanFetcher:
    base_url: str = "https://archives.nseindia.com/content/fo"

    def fetch_for_date(self, ref_date: date) -> set[str]:
        if ref_date == date.today():
            url = f"{self.base_url}/fo_secban.csv"
        else:
            url = f"{self.base_url}/secban_{ref_date.strftime('%d%m%Y')}.csv"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            log.warning("fno_ban_fetch_failed", url=url, status=resp.status_code)
            return set()
        df = pd.read_csv(io.StringIO(resp.text))
        col = next(c for c in df.columns if "symbol" in c.lower())
        return set(df[col].str.strip().tolist())


@dataclass
class FnoBanUpserter:
    session: Session

    def _resolve_iids(self, symbols: set[str]) -> dict[str, str]:
        if not symbols:
            return {}
        rows = self.session.execute(
            text("""
            SELECT symbol, instrument_id
              FROM atlas.atlas_instrument_master
             WHERE symbol = ANY(:syms)
        """),
            {"syms": list(symbols)},
        ).fetchall()
        return {r.symbol: str(r.instrument_id) for r in rows}

    def upsert(self, ref_date: date, ban_symbols: set[str]) -> None:
        # Step 1: mark today's ban list as true
        if ban_symbols:
            iid_map = self._resolve_iids(ban_symbols)
            for _sym, iid in iid_map.items():
                self.session.execute(
                    text("""
                    INSERT INTO atlas.atlas_governance_daily
                        (instrument_id, date, in_fno_ban_list)
                    VALUES (:i, :d, true)
                    ON CONFLICT (instrument_id, date) DO UPDATE
                       SET in_fno_ban_list = true
                """),
                    {"i": iid, "d": ref_date},
                )
        # Step 2: clear flag on rows present but absent from today's list
        self.session.execute(
            text("""
            UPDATE atlas.atlas_governance_daily
               SET in_fno_ban_list = false
             WHERE date = :d
               AND in_fno_ban_list = true
               AND instrument_id NOT IN (
                   SELECT instrument_id FROM atlas.atlas_instrument_master
                    WHERE symbol = ANY(:syms)
               )
        """),
            {"d": ref_date, "syms": list(ban_symbols)},
        )
        self.session.commit()
        log.info("fno_ban_upserted", date=ref_date.isoformat(), ban_count=len(ban_symbols))
