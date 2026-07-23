import os, sys, psycopg2

DSN = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")

def test_sebi_ranks_and_one_real_large_cap():
    sys.path.insert(0, "scripts/wealth")
    from build_label_check import sebi_ranks, classify_fund
    import engine_common
    conn = engine_common.connect()
    ranks = sebi_ranks(conn)
    assert sum(1 for v in ranks.values() if v == "large") == 100
    assert sum(1 for v in ranks.values() if v == "mid") == 150
    # a real held large-cap fund with data should classify something as large
    cur = conn.cursor()
    cur.execute("""select s.mstar_id from wealth.schemes s
                   join wealth.holdings h using (scheme_id)
                   where s.display_name ilike '%large cap%' and s.display_name not ilike '%mid%'
                     and s.mstar_id is not null limit 1""")
    mid = cur.fetchone()[0]
    res = classify_fund(conn, mid, ranks)
    # equity_pct should be sum of large+mid+small from holdings in equity_marketcap
    # large_pct is the large portion; should be positive and dominate if fund does its job
    assert res["equity_pct"] >= 0 and res["large_pct"] >= 0
    assert res["large_pct"] >= res["mid_pct"]  # large cap fund should have more large than mid
