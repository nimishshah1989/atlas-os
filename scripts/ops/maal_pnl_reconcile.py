#!/usr/bin/env python3
"""Prove the MaaL realized-P&L numbers against the real trade history.

Unit tests prove the FIFO algorithm on a handful of hand-checked cases. This proves
the DATA: every sell Atlas has stored for the three books, every night. Money figures
that disagree with the client statement destroy trust in everything else on the board,
so they get a gate of their own rather than a spot check.

Scoped by the join to maal_trade_link — engine-written trades have no link row and
are none of this gate's business.

    python scripts/ops/maal_pnl_reconcile.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "foundation"))
import _db  # pyright: ignore[reportMissingImports]

M = "atlas_foundation"

# A sell whose buys predate what CPP holds cannot be matched, and inventing a cost
# basis for it would fabricate profit. The sync already refuses to guess; this gate
# only insists the count stays where we last verified it, so a NEW unmatched sell
# (a real regression) is not lost in the noise of the known ones.
_KNOWN_UNMATCHED = 0


def main() -> int:
    rows = _db.read_df(f"""
        SELECT m.name,
               count(*)                                        AS sells,
               count(t.realized_pnl)                           AS with_pnl,
               count(*) - count(t.realized_pnl)                AS unmatched,
               coalesce(sum(t.realized_pnl), 0)                AS realized,
               -- Compare against GROSS proceeds (qty * price), not `value`, which is
               -- CPP's amount NET of transaction costs. Zero-cost bonus shares book
               -- their whole gross price as gain and legitimately exceed the net
               -- figure: three real CDSL sells on 2024-09-27 do exactly that. Only a
               -- gain above GROSS proves the cost basis went negative.
               count(*) FILTER (WHERE t.realized_pnl > t.qty * t.price) AS pnl_exceeds_proceeds,
               count(*) FILTER (WHERE t.holding_days < 0)       AS negative_holding,
               count(*) FILTER (
                   WHERE t.tax_bucket IS NOT NULL AND t.holding_days IS NOT NULL
                     AND ((t.holding_days <= 365) <> (t.tax_bucket = 'STCG'))
               )                                                AS tax_bucket_mismatch
        FROM {M}.portfolio_trades t
        JOIN {M}.maal_trade_link l USING (trade_id)
        JOIN {M}.portfolio_master m USING (portfolio_id)
        WHERE t.side = 'sell'
        GROUP BY m.name
        ORDER BY m.name
    """)

    if rows.empty:
        print("[maal_pnl_reconcile] FAIL — no linked MaaL sells at all; has the sync run?")
        return 1

    problems: list[str] = []
    total_sells = total_unmatched = 0
    total_realized = 0.0

    for r in rows.to_dict("records"):
        name = r["name"]
        total_sells += int(r["sells"])
        total_unmatched += int(r["unmatched"])
        total_realized += float(r["realized"])
        print(
            f"    {name:14s} sells={int(r['sells']):5d} matched={int(r['with_pnl']):5d} "
            f"unmatched={int(r['unmatched']):3d} realized=Rs {float(r['realized']) / 100000:>10,.2f} lakh"
        )
        # A gain larger than the sale proceeds means the cost basis went negative —
        # the classic FIFO bug, and the one that would look plausible on a report.
        if int(r["pnl_exceeds_proceeds"]):
            problems.append(
                f"{name}: {int(r['pnl_exceeds_proceeds'])} sell(s) book a gain larger than "
                f"their own proceeds — cost basis went negative"
            )
        if int(r["negative_holding"]):
            problems.append(
                f"{name}: {int(r['negative_holding'])} sell(s) have a negative holding "
                f"period — a lot was matched to a buy dated after the sell"
            )
        if int(r["tax_bucket_mismatch"]):
            problems.append(
                f"{name}: {int(r['tax_bucket_mismatch'])} sell(s) have a tax_bucket that "
                f"disagrees with their own holding_days"
            )

    print(
        f"    TOTAL sells={total_sells} unmatched={total_unmatched} "
        f"realized=Rs {total_realized / 100000:,.2f} lakh"
    )

    if total_unmatched > _KNOWN_UNMATCHED:
        problems.append(
            f"{total_unmatched} unmatched sell(s), above the {_KNOWN_UNMATCHED} known. "
            f"A sell with no matching buy books NO P&L, so the book understates its "
            f"realized gains. Check for a new instrument whose buys predate CPP's history."
        )

    if problems:
        print(f"[maal_pnl_reconcile] FAIL — {len(problems)} problem(s):")
        for p in problems:
            print(f"    - {p}")
        return 1

    print("[maal_pnl_reconcile] PASS — every MaaL sell reconciles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
