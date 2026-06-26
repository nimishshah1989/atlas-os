import time

import _db

for mv in ("mv_sector_cards", "mv_sector_breadth"):
    # is it populated?
    pop = _db.scalar(
        f"select ispopulated from pg_matviews where schemaname='atlas' and matviewname='{mv}'"
    )
    print(f"{mv} populated={pop}", flush=True)
    if not pop:
        t = time.time()
        print(f"  REFRESH {mv} ...", flush=True)
        _db.exec_sql(f"REFRESH MATERIALIZED VIEW atlas.{mv}")
        print(
            f"  done in {time.time() - t:.0f}s rows={_db.scalar(f'select count(*) from atlas.{mv}')}",
            flush=True,
        )
print("ALL_REFRESH_DONE", flush=True)
