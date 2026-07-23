import os, subprocess, psycopg2, pytest

DSN = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")

def q(sql, args=()):
    with psycopg2.connect(DSN) as c, c.cursor() as cur:
        cur.execute(sql, args); return cur.fetchall()

def test_pairwise_overlap_symmetric_and_bounded():
    import sys; sys.path.insert(0, "scripts/wealth")
    from build_overlap import latest_fund_weights, pairwise_overlap
    import engine_common
    conn = engine_common.connect()
    fw = latest_fund_weights(conn)
    # two real, populated funds
    mids = [m for m, w in fw.items() if len(w) >= 20][:2]
    assert len(mids) == 2, "need two real funds with >=20 holdings"
    a, b = mids
    oab, oba = pairwise_overlap(fw[a], fw[b]), pairwise_overlap(fw[b], fw[a])
    assert oab == oba and 0 <= oab <= 100
    assert pairwise_overlap(fw[a], fw[a]) > 60  # self-overlap ~= sum of mapped weights
