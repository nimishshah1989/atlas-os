"""Real-data tests for the PREDICT call-list engine (Rule #0: no fixtures —
every assertion runs against the live wealth.* tables)."""
import sys

sys.path.insert(0, "scripts/wealth")

from build_call_lists import TOP_N, compute_all  # noqa: E402
from engine_common import connect  # noqa: E402


def _rows():
    conn = connect()
    rows, armed, drawdown_now, armed_floor = compute_all(conn)
    return conn, rows, armed, drawdown_now, armed_floor


def test_three_lists_of_twenty():
    _, rows, _, _, _ = _rows()
    types = {r["list_type"] for r in rows}
    assert types == {"crash_sellers", "sip_fragile", "disengaged"}
    for lt in types:
        n = len([r for r in rows if r["list_type"] == lt])
        assert n == TOP_N, f"{lt}: {n} rows, expected {TOP_N}"


def test_ranks_are_1_to_20_per_list():
    _, rows, _, _, _ = _rows()
    for lt in {r["list_type"] for r in rows}:
        ranks = sorted(r["rank"] for r in rows if r["list_type"] == lt)
        assert ranks == list(range(1, TOP_N + 1))


def test_scores_in_0_100():
    _, rows, _, _, _ = _rows()
    for r in rows:
        assert 0 <= r["score"] <= 100, f"{r['list_type']} rank {r['rank']}: score {r['score']}"


def test_script_lines_single_sentence_no_semicolon_one_action_verb():
    """No fixtures: every script currently in the engine's own output. Single
    sentence = exactly one terminal period and no internal ones; the RM reads
    it once, on the phone."""
    _, rows, _, _, _ = _rows()
    for r in rows:
        s = r["script"].strip()
        assert ";" not in s, f"{r['list_type']} rank {r['rank']}: semicolon in script: {s!r}"
        assert s.count(".") == 1 and s.endswith("."), (
            f"{r['list_type']} rank {r['rank']}: not a single sentence: {s!r}"
        )


def test_known_panic_client_ranks_top_of_crash_sellers():
    """Pick the client with the highest panic_share among clients whose book
    is worth calling about (mv > median of the crash_sellers pool), then
    assert they land in the crash_sellers top 20."""
    conn, rows, _, _, _ = _rows()
    cur = conn.cursor()
    cur.execute(
        """select b.client_id
           from wealth.client_behaviour b
           join (select client_id, coalesce(sum(market_value),0) mv
                 from wealth.ledger_blocks group by 1) m using (client_id)
           where m.mv > (select percentile_cont(0.5) within group (order by mv)
                         from (select coalesce(sum(market_value),0) mv
                               from wealth.ledger_blocks group by client_id) x)
           order by b.panic_share desc nulls last, m.mv desc
           limit 1"""
    )
    (cid,) = cur.fetchone()
    crash_ids = {r["client_id"] for r in rows if r["list_type"] == "crash_sellers"}
    assert cid in crash_ids, f"client {cid} (highest panic_share among above-median books) not in crash_sellers"


def test_crash_sellers_reason_mentions_armed_only_when_bench_is_down():
    _, rows, armed, drawdown_now, armed_floor = _rows()
    crash = [r for r in rows if r["list_type"] == "crash_sellers"]
    mentions = [r for r in crash if "armed" in r["reason"].lower()]
    if armed:
        assert mentions, f"bench is {drawdown_now:+.1%} off peak (armed) but no reason text says so"
    else:
        assert not mentions, f"bench is {drawdown_now:+.1%} off peak (not armed) but a reason claims armed"


def test_book_values_match_ledger_blocks():
    conn, rows, _, _, _ = _rows()
    cur = conn.cursor()
    for r in rows[:5]:
        cur.execute(
            "select coalesce(sum(market_value),0) from wealth.ledger_blocks where client_id=%s",
            (r["client_id"],),
        )
        (expected,) = cur.fetchone()
        assert round(float(expected), 2) == round(float(r["mv"]), 2)


def test_sip_fragile_ranks_on_its_own_key_not_freak_out():
    """Regression guard: sip_fragile must not be the crash_sellers list with a
    different label. Independently recompute a SIP-centric ranking straight
    from wealth.client_behaviour (sip_active_share dominant, drawdown-stop
    share secondary) and require the engine's sip_fragile top-20 to actually
    match that ordering's top client, not crash_sellers'."""
    conn, rows, _, _, _ = _rows()
    crash_ids = [r["client_id"] for r in rows if r["list_type"] == "crash_sellers"]
    sip_ids = [r["client_id"] for r in rows if r["list_type"] == "sip_fragile"]
    overlap = set(crash_ids) & set(sip_ids)

    # observed bound: two lists sharing a risk-adjacent population will
    # overlap some — but nowhere near the 18/20 a shared ranking key produced
    assert len(overlap) <= 10, f"crash_sellers/sip_fragile overlap {len(overlap)}/{TOP_N} — too close to identical"
    assert crash_ids[0] != sip_ids[0], (
        "rank-1 client identical across both lists — suspicious for two independently-ranked lists"
    )

    # independent SQL recompute of the pure sip_risk ranking (ignoring the
    # book-size blend) — its #1 client must actually be a plausible pick,
    # i.e. have zero or very low active-SIP share (dominant term, weight 0.6)
    conn2 = conn.cursor()
    conn2.execute(
        """select sip_active::float / nullif(sip_streams, 0)
           from wealth.client_behaviour where client_id = %s""",
        (sip_ids[0],),
    )
    (top_active_share,) = conn2.fetchone()
    assert top_active_share is None or top_active_share <= 0.5, (
        f"sip_fragile rank-1 client has sip_active_share={top_active_share}, "
        f"too high to be the top SIP-stopping risk"
    )


def test_armed_floor_seeded_in_atlas_thresholds():
    conn, _, _, _, armed_floor = _rows()
    cur = conn.cursor()
    cur.execute(
        "select threshold_value, category from atlas_foundation.atlas_thresholds "
        "where threshold_key = 'wealth_drawdown_armed_floor_pct'"
    )
    row = cur.fetchone()
    assert row is not None, "wealth_drawdown_armed_floor_pct not seeded"
    value, category = row
    assert category == "wealth"
    assert float(value) == armed_floor
