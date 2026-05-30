"""One-shot: refresh v6 materialized views with per-MV CONCURRENTLY->plain fallback.
Usage: python3 _refresh_mvs.py [group]   group in {fresh,stale,all}
Run on EC2 (source .venv first). Reads ATLAS_DB_URL from .env."""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")
engine = create_engine(os.environ["ATLAS_DB_URL"])

# MVs whose source tables are already fresh at the latest close
FRESH = [
    "mv_market_regime_landing",
    "mv_stock_list_v6",
    "mv_stock_deepdive",
    "mv_markets_rs_grid",
    "mv_stock_landscape",
    "mv_markets_rs_detail_charts",
    "mv_india_pulse",
    "mv_sector_cards",
    "mv_sector_breadth",
    "mv_sector_rrg",
    "mv_sector_deepdive",
]
# MVs that depend on the 3 stale writers (fund/etf/signal scorecards)
STALE = [
    "mv_fund_list_v6",
    "mv_fund_deepdive",
    "mv_calls_performance",
    "mv_etf_list_v6",
    "mv_etf_deepdive",
]

group = sys.argv[1] if len(sys.argv) > 1 else "fresh"
targets = FRESH if group == "fresh" else STALE if group == "stale" else FRESH + STALE

for mv in targets:
    ok = False
    for concurrently in (True, False):
        try:
            with engine.connect() as c:
                c.execution_options(isolation_level="AUTOCOMMIT")
                kw = "CONCURRENTLY " if concurrently else ""
                c.execute(text("REFRESH MATERIALIZED VIEW " + kw + "atlas." + mv))
            tag = "" if concurrently else " [plain]"
            print("  OK  " + mv + tag)
            ok = True
            break
        except Exception as ex:
            if concurrently:
                continue
            print("  ERR " + mv + ": " + str(ex)[:90])
    if not ok:
        print("  FAIL " + mv)
