#!/usr/bin/env python3
"""Approve/reject Atlas Desk pending orders (interim CLI until the board UI).

python desk_approve.py                     # list pending cards
python desk_approve.py --approve 12 14     # approve by id
python desk_approve.py --reject 13 --by nimish
Approved cards are booked by the next desk_run settlement (nightly 19:30 IST).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db

M = "atlas_foundation"


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas Desk approval queue")
    ap.add_argument("--approve", nargs="+", type=int, default=[])
    ap.add_argument("--reject", nargs="+", type=int, default=[])
    ap.add_argument("--by", default="cli", help="who decided (audit trail)")
    a = ap.parse_args()

    for ids, status in ((a.approve, "approved"), (a.reject, "rejected")):
        for i in ids:
            _db.exec_sql(
                f"""update {M}.desk_pending_orders
                    set status = :st, decided_at = now(), decided_by = :by
                    where id = :i and status = 'pending'""",
                {"st": status, "by": a.by, "i": i},
            )
            print(f"{status}: #{i}")

    df = _db.read_df(
        f"""select o.id, m.name, o.cycle_date, o.side, o.symbol, o.entry_ref,
                   o.stop, o.target, o.rr, o.status, o.thesis
            from {M}.desk_pending_orders o
            join {M}.portfolio_master m using (portfolio_id)
            where o.status = 'pending' order by o.cycle_date, o.id"""
    )
    print("\nPENDING:" if not df.empty else "\nno pending orders")
    if not df.empty:
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
