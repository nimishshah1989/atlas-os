import sys

sys.path.insert(0, "/home/ubuntu/atlas-os")

import _db

from atlas.lenses.pipeline import run_pipeline

# trading days in the divergence window (MF from ~03-28, overlay from ~04-12) → cover from 03-01
days = [
    d.date() if hasattr(d, "date") else d
    for d in _db.read_df(
        "select distinct date from atlas_foundation.index_prices where index_code='NIFTY 50' and date between '2026-03-01' and '2026-06-24' order by date"
    )["date"]
]
print(f"re-scoring {len(days)} trading days 2026-03-01..06-24 via run_pipeline", flush=True)
for i, d in enumerate(days, 1):
    r = run_pipeline(as_of=d)
    if i % 10 == 0 or i == len(days):
        print(f"  {i}/{len(days)} {d} scored={r.get('instruments_scored')}", flush=True)
print("RECENT_RESCORE_DONE", flush=True)
