"""D5: Promoter pledge quarterly ingester.

For each filing, computes pledge_ratio = pledged_shares / total_promoter_shares × 100.
Forward-fills the value into atlas_governance_daily from the filing's effective
date through the day before the next quarter ends.

NSE/BSE source: https://www.nseindia.com/companies-listing/corporate-filings
Operator runs the ingester once per quarter via CLI:
    python -m atlas.data_prereqs.v6.cli ingest-pledge --filing-json path/to/q3_2024.json
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


def compute_pledge_ratio(total: int, pledged: int) -> float | None:
    if total <= 0:
        return None
    return round(100.0 * pledged / total, 2)


def parse_pledge_filing(payload: dict) -> list[dict]:
    eff = date.fromisoformat(payload["asOfDate"])
    rows = []
    for f in payload["filings"]:
        ratio = compute_pledge_ratio(f["promoter_total_shares"], f["promoter_pledged_shares"])
        if ratio is None:
            continue
        rows.append(
            {
                "symbol": f["symbol"],
                "effective_date": eff,
                "pledge_ratio_pct": ratio,
            }
        )
    return rows


def _next_quarter_end(d: date) -> date:
    year, month = d.year, d.month
    if month <= 3:
        return date(year, 6, 30)
    if month <= 6:
        return date(year, 9, 30)
    if month <= 9:
        return date(year, 12, 31)
    return date(year + 1, 3, 31)


@dataclass
class PledgeQuarterIngester:
    session: Session

    def _resolve_iid(self, symbol: str) -> uuid.UUID | None:
        row = self.session.execute(
            text("SELECT instrument_id FROM atlas.atlas_instrument_master WHERE symbol = :s"),
            {"s": symbol},
        ).first()
        return uuid.UUID(str(row.instrument_id)) if row else None

    def ingest_filing(self, payload: dict) -> None:
        rows = parse_pledge_filing(payload)
        if not rows:
            log.info("pledge_filing_empty")
            return
        eff = rows[0]["effective_date"]
        fill_until = _next_quarter_end(eff) - timedelta(days=1)
        n_days = (fill_until - eff).days + 1
        for r in rows:
            iid = self._resolve_iid(r["symbol"])
            if iid is None:
                log.warning("pledge_symbol_not_resolved", symbol=r["symbol"])
                continue
            for offset in range(n_days):
                d = eff + timedelta(days=offset)
                self.session.execute(
                    text("""
                    INSERT INTO atlas.atlas_governance_daily
                        (instrument_id, date, pledge_ratio_pct)
                    VALUES (:i, :d, :p)
                    ON CONFLICT (instrument_id, date) DO UPDATE
                       SET pledge_ratio_pct = EXCLUDED.pledge_ratio_pct
                """),
                    {"i": str(iid), "d": d, "p": r["pledge_ratio_pct"]},
                )
        self.session.commit()
        log.info(
            "pledge_filing_ingested",
            effective_date=eff.isoformat(),
            symbols=len(rows),
            days_filled=n_days,
        )
