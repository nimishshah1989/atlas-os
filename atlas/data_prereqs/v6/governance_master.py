"""D6: Auditor + promoter group master.

One-time scrape from Screener.in (or NSE corporate filings); annual refresh.
Tags whether the auditor is in the top-10 list used for governance filtering.

TOP_10_AUDITORS is hand-curated and reviewed annually; treat as a constant.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()

TOP_10_AUDITORS: tuple[str, ...] = (
    "Deloitte Haskins & Sells",
    "Price Waterhouse",
    "PwC",
    "Ernst & Young",
    "EY",
    "KPMG",
    "BSR & Co",
    "Walker Chandiok & Co",
    "Grant Thornton",
    "RSM",
    "Crowe Horwath",
    "S R B C & Co",
    "S.R. Batliboi",
)


def is_top_10_auditor(auditor_name: str | None) -> bool:
    if not auditor_name:
        return False
    norm = auditor_name.replace("&", "and").lower()
    return any(a.replace("&", "and").lower().split()[0] in norm.split() for a in TOP_10_AUDITORS)


def parse_screener_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, str | None] = {"promoter_group": None, "auditor_name": None}
    for line in soup.select(".company-line"):
        text_ = line.get_text(" ", strip=True)
        if text_.startswith("Promoter Group:"):
            out["promoter_group"] = text_[len("Promoter Group:") :].strip()
        elif text_.startswith("Auditor:"):
            out["auditor_name"] = text_[len("Auditor:") :].strip()
    return out


@dataclass
class GovernanceMasterUpserter:
    session: Session

    def upsert(
        self,
        symbol: str,
        promoter_group: str | None,
        auditor_name: str | None,
    ) -> None:
        row = self.session.execute(
            text("SELECT instrument_id FROM atlas.atlas_instrument_master WHERE symbol = :s"),
            {"s": symbol},
        ).first()
        if row is None:
            log.warning("symbol_unresolved", symbol=symbol)
            return
        iid = str(row.instrument_id)
        self.session.execute(
            text("""
            INSERT INTO atlas.atlas_governance_master
                (instrument_id, promoter_group, auditor_name, auditor_is_top_10)
            VALUES (:i, :g, :a, :t)
            ON CONFLICT (instrument_id) DO UPDATE SET
                promoter_group = EXCLUDED.promoter_group,
                auditor_name = EXCLUDED.auditor_name,
                auditor_is_top_10 = EXCLUDED.auditor_is_top_10,
                updated_at = NOW()
        """),
            {
                "i": iid,
                "g": promoter_group,
                "a": auditor_name,
                "t": is_top_10_auditor(auditor_name),
            },
        )
        self.session.commit()
