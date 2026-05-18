"""D1: Point-in-time Nifty 500 (and Nifty 100, etc.) membership ingester.

Each NSE index reconstitution event is a snapshot — the set of symbols valid
on a specific effective date. We diff consecutive snapshots to produce
(symbol, valid_from, valid_to) rows in atlas_index_membership.

For backfill, the operator manually downloads snapshots for each historical
reconstitution date and feeds them to MembershipIngester.ingest_snapshot.
For ongoing maintenance, schedules.py runs a fetch_latest_and_diff each
night around 19:00 IST.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


@dataclass(frozen=True)
class ReconstitutionSnapshot:
    index_name: str
    effective_date: date
    symbols: frozenset[str]


def parse_reconstitution_snapshot(payload: dict) -> ReconstitutionSnapshot:
    """Parse NSE reconstitution JSON -> typed snapshot."""
    return ReconstitutionSnapshot(
        index_name=payload["indexName"],
        effective_date=date.fromisoformat(payload["effectiveDate"]),
        symbols=frozenset(c["symbol"] for c in payload["constituents"]),
    )


def diff_snapshots(prior: set[str], curr: set[str]) -> tuple[set[str], set[str]]:
    """Return (adds, drops) — symbols entering vs exiting."""
    return curr - prior, prior - curr


@dataclass
class MembershipIngester:
    session: Session

    def _resolve_symbol_to_iid(self, symbol: str) -> uuid.UUID:
        row = self.session.execute(
            text(
                "SELECT instrument_id FROM atlas.atlas_instrument_master "
                "WHERE symbol = :s LIMIT 1"
            ),
            {"s": symbol},
        ).first()
        if row is None:
            raise LookupError(f"symbol {symbol} not in instrument master")
        return uuid.UUID(str(row.instrument_id))

    def apply_diff(
        self,
        index_name: str,
        effective_date: date,
        adds: set[str],
        drops: set[str],
    ) -> None:
        for sym in drops:
            iid = self._resolve_symbol_to_iid(sym)
            self.session.execute(
                text("""
                UPDATE atlas.atlas_index_membership
                   SET valid_to = :d
                 WHERE index_name = :idx
                   AND instrument_id = :iid
                   AND valid_to IS NULL
            """),
                {"d": effective_date, "idx": index_name, "iid": str(iid)},
            )
        for sym in adds:
            iid = self._resolve_symbol_to_iid(sym)
            self.session.execute(
                text("""
                INSERT INTO atlas.atlas_index_membership
                    (index_name, instrument_id, valid_from, valid_to)
                VALUES (:idx, :iid, :d, NULL)
                ON CONFLICT DO NOTHING
            """),
                {"idx": index_name, "iid": str(iid), "d": effective_date},
            )
        self.session.commit()
        log.info(
            "membership_diff_applied",
            index=index_name,
            date=effective_date.isoformat(),
            adds=len(adds),
            drops=len(drops),
        )

    def ingest_snapshot(self, snapshot: ReconstitutionSnapshot) -> None:
        """Compute diff vs current open-membership set and apply."""
        rows = self.session.execute(
            text("""
            SELECT i.symbol
              FROM atlas.atlas_index_membership m
              JOIN atlas.atlas_instrument_master i USING (instrument_id)
             WHERE m.index_name = :idx AND m.valid_to IS NULL
        """),
            {"idx": snapshot.index_name},
        ).fetchall()
        prior = {r.symbol for r in rows}
        adds, drops = diff_snapshots(prior, set(snapshot.symbols))
        self.apply_diff(
            index_name=snapshot.index_name,
            effective_date=snapshot.effective_date,
            adds=adds,
            drops=drops,
        )
