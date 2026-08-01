#!/usr/bin/env python3
"""Quote the three MaaL books and write today's live marks.

Called every 5 min during market hours by scripts/ops/atlas_intraday.sh — the cron
that already exists. No new schedule, no second Kite session: it reuses the client
build_sector_rs_intraday.py uses.

Non-fatal by design. A missed tick is cosmetic; the EOD sync is the source of record.
"""

from __future__ import annotations

import logging
import sys

import _db  # pyright: ignore[reportMissingImports]
import ingest_kite as ik  # pyright: ignore[reportMissingImports]
import pandas as pd

log = logging.getLogger("maal_live_mark")


def _latest_positions() -> pd.DataFrame:
    """Every position in the newest snapshot of each book, with its Kite token.

    CASH-class rows (the liquid-ETF sleeve) are excluded: they are cash, not a
    position to mark. Rows whose ISIN is unknown to instrument_master are excluded
    here and counted by the caller — the sync already fails loudly on those.
    """
    return _db.read_df("""
        WITH latest AS (
            SELECT maal_code, max(as_of) AS as_of
            FROM atlas_foundation.maal_holding_snapshot
            GROUP BY maal_code
        )
        SELECT s.maal_code, s.isin, im.symbol, im.kite_token
        FROM atlas_foundation.maal_holding_snapshot s
        JOIN latest l ON l.maal_code = s.maal_code AND l.as_of = s.as_of
        JOIN atlas_foundation.instrument_master im ON im.isin = s.isin
        WHERE s.asset_class <> 'CASH'
          AND im.kite_token IS NOT NULL
    """)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pos = _latest_positions()
    if pos.empty:
        log.warning("no MaaL positions with a Kite token — nothing to mark")
        return 0

    tokens = sorted({int(t) for t in pos["kite_token"]})
    quotes = ik.kite_client().quote(tokens)

    # Kite returns keys as str(token); a quote can come back as something other than a
    # dict when the instrument is halted, so guard rather than assume.
    ltp_by_token: dict[int, float] = {}
    for key, q in quotes.items():
        if isinstance(q, dict) and q.get("last_price"):
            ltp_by_token[int(str(key).split(":")[-1])] = float(q["last_price"])

    held = list(zip(pos["maal_code"], pos["isin"], pos["symbol"], pos["kite_token"], strict=False))
    rows = [
        {"maal_code": str(code), "isin": str(isin), "ltp": ltp_by_token[int(tok)]}
        for code, isin, _sym, tok in held
        if int(tok) in ltp_by_token and ltp_by_token[int(tok)] > 0
    ]
    unquoted = sorted({str(sym) for _c, _i, sym, tok in held if int(tok) not in ltp_by_token})

    if rows:
        _db.upsert_df("atlas_foundation.maal_live_mark", pd.DataFrame(rows), ["maal_code", "isin"])
    log.info("marked %d position(s); %d unquoted", len(rows), len(unquoted))
    if unquoted:
        # Named, never silently dropped — the board shows the gap rather than a
        # quietly understated book.
        log.warning("no live quote for: %s", ", ".join(unquoted))
    return 0


if __name__ == "__main__":
    sys.exit(main())
