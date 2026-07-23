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
    # a real held large-cap fund must classify majority-large
    cur = conn.cursor()
    cur.execute("""select s.mstar_id from wealth.schemes s
                   join wealth.holdings h using (scheme_id)
                   where s.display_name ilike '%large cap%' and s.display_name not ilike '%mid%'
                     and s.mstar_id is not null limit 1""")
    mid = cur.fetchone()[0]
    res = classify_fund(conn, mid, ranks)
    assert res["equity_pct"] > 60 and res["large_pct"] > 50

    # sanity check: average unclassified_pct < 50% across held equity-labelled funds
    cur.execute("""select avg(unclassified_pct) from wealth.fund_label_check
                   where category in ('Large Cap', 'Mid Cap', 'Small Cap', 'Multi Cap', 'Large & Mid Cap')""")
    avg_unclass = cur.fetchone()[0] or 0
    assert avg_unclass < 50, f"avg unclassified_pct {avg_unclass}% too high for equity funds"
