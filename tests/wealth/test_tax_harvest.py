import os, sys


def test_headroom_and_candidates_real_client():
    sys.path.insert(0, "scripts/wealth")
    from build_tax_harvest import compute_client, current_fy_start
    import build_tax_harvest
    import engine_common
    conn = engine_common.connect()
    cur = conn.cursor()
    cur.execute("""select l.client_id from wealth.lots l join wealth.schemes s using (scheme_id)
                   where l.status='open' and s.asset_class='Equity' and l.tax_bucket='ltcg'
                     and l.unrealized_gain > 50000 limit 1""")
    result = cur.fetchone()
    if not result:
        import pytest
        pytest.skip("No client found with open equity LTCG lot with unrealized_gain > 50000")
    cid = result[0]
    r = compute_client(conn, cid)
    # EXEMPT is now initialized after first compute_client call
    assert 0 <= r["headroom"] <= float(build_tax_harvest.EXEMPT)
    assert r["gain_value"] <= r["headroom"] + 1  # never harvest past the exemption
    for c in r["gain_candidates"]:
        assert c["gain"] > 0 and c["bucket"] == "ltcg"
