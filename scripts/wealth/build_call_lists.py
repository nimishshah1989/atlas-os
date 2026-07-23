"""PREDICT call lists: three standing "who to call, and what to say" lists,
ranked and scripted from real per-client behaviour — no fitted model.

Three lists (`wealth.call_lists.list_type`), top 20 each, rank 1 = highest
priority within its own blend of risk score and book size (0.7 risk-percentile
+ 0.3 book-percentile within the list's own candidate pool):

  crash_sellers  clients most likely to sell into the next drawdown, ranked
                 by the freak-out score below. Reason names their own past
                 panic-selling; flagged "armed" in the reason text only when
                 the bench currently sits >10% below its running peak
                 (`behaviour_fingerprints.drawdown_windows`, same -10% floor
                 the rest of the wealth engine already uses — not a fitted or
                 re-invented threshold). Candidate pool: clients with a
                 wealth.client_behaviour row and book value > 0.
  sip_fragile    clients with SIP history whose SIP is most at risk of
                 stopping (or already has), same freak-out score. Candidate
                 pool: clients with sip_streams > 0 and book value > 0.
  disengaged     clients drifting away, using wealth.client_churn_risk's own
                 disengagement_score AS-IS (reused, not recomputed — it is
                 already a transparent 0-100 blend of quiet-months, SIP-stop
                 share and 12m-outflow share; see churn_clv.py). Candidate
                 pool: all rows in wealth.client_churn_risk.

Freak-out score (crash_sellers, sip_fragile) — HEURISTIC, not a fitted model
(n=234 in wealth.client_behaviour; nowhere near enough events for a real
classifier). Documented weights, per the MIT panic-prediction demo precedent
cited in docs/wealth-capability-atlas.md:

    score = 0.5 * panic_share
          + 0.2 * (1 - sip_active_share)
          + 0.2 * chase_hot_share
          + 0.1 * recent_seller
    scaled to 0-100.

Column mapping (wealth.client_behaviour unless noted):
  panic_share       panic_share            share of lifetime external outflow
                     ₹ that landed inside a bench drawdown window. NULL (no
                     outflows ever) -> 0.
  sip_active_share  sip_active / sip_streams  share of the client's own
                     detected SIP streams still active. No SIP history
                     (sip_streams = 0) -> 0.5 neutral, same convention
                     churn_clv.py already uses for "no evidence either way".
  chase_hot_share   chase_hot_share        share of equity buy ₹ placed after
                     a >10% trailing-quarter rally. NULL -> 0.
  recent_seller     computed here from wealth.transactions: 1 if the client
                     has an external sell (redemption/swp, amount > 0) dated
                     within the trailing 365 days of the ledger's last
                     transaction date, else 0. No existing column carries
                     this as a flag (client_churn_risk.out12_share is a
                     ₹-weighted share, not a binary "sold recently").

Reason/script text is grounded in that client's own numbers, one sentence,
one action verb, no semicolons — the RM reads it on the phone.

Usage: .venv/bin/python scripts/wealth/build_call_lists.py
"""
from __future__ import annotations

import sys

import pandas as pd
from behaviour_fingerprints import drawdown_windows
from engine_common import BENCH_ID, connect, nav_series
from psycopg2.extras import execute_values

TOP_N = 20
RISK_WEIGHT, BOOK_WEIGHT = 0.7, 0.3


def _pctile(s: pd.Series) -> pd.Series:
    """0-100 percentile rank, ties averaged. Constant series -> all 50."""
    if s.nunique() <= 1:
        return pd.Series(50.0, index=s.index)
    return s.rank(pct=True) * 100


def _blend_rank(df: pd.DataFrame, risk_col: str, mv_col: str = "mv") -> pd.DataFrame:
    blend = RISK_WEIGHT * _pctile(df[risk_col]) + BOOK_WEIGHT * _pctile(df[mv_col])
    return df.assign(_blend=blend).sort_values("_blend", ascending=False).head(TOP_N)


def compute_all(conn) -> tuple[list[dict], bool, float]:
    """Returns (rows, armed, drawdown_now). rows = one dict per (list_type, rank)."""
    beh = pd.read_sql(
        """select client_id, panic_share, panic_out_rs, panic_loss_out_rs,
                  chase_hot_share, sip_streams, sip_active, sip_stopped,
                  sip_stops_in_drawdown
           from wealth.client_behaviour""",
        conn,
    )
    mv = pd.read_sql(
        "select client_id, coalesce(sum(market_value),0)::float mv from wealth.ledger_blocks group by 1",
        conn,
    )
    txns = pd.read_sql(
        """select client_id, txn_date, txn_type, amount::float amount
           from wealth.transactions
           where txn_type in ('redemption','swp') and amount > 0 and txn_date is not null""",
        conn,
    )
    txns["txn_date"] = pd.to_datetime(txns.txn_date)
    ledger_end = txns.txn_date.max()
    recent_sellers = set(
        txns[txns.txn_date > ledger_end - pd.Timedelta(days=365)].client_id.unique()
    )

    df = beh.merge(mv, on="client_id", how="left")
    df["mv"] = df.mv.fillna(0.0)
    df["panic_share"] = df.panic_share.fillna(0.0).astype(float)
    df["chase_hot_share"] = df.chase_hot_share.fillna(0.0).astype(float)
    df["sip_active_share"] = df.apply(
        lambda r: (r.sip_active / r.sip_streams) if r.sip_streams else 0.5, axis=1
    )
    df["recent_seller"] = df.client_id.isin(recent_sellers).astype(int)
    df["freak_out"] = (
        0.5 * df.panic_share
        + 0.2 * (1 - df.sip_active_share)
        + 0.2 * df.chase_hot_share
        + 0.1 * df.recent_seller
    ) * 100

    # ---- crash_sellers: drawdown-armed state (>10% off running peak, same
    # floor drawdown_windows already uses across the wealth engine) ----
    bench = nav_series(conn, BENCH_ID)
    drawdown_now = float(bench.iloc[-1] / bench.cummax().iloc[-1] - 1)
    armed = drawdown_now <= -0.10

    rows: list[dict] = []

    # crash_sellers
    pool = df[df.mv > 0].copy()
    top = _blend_rank(pool, "freak_out")
    for i, r in enumerate(top.itertuples(), start=1):
        reason = (
            f"Sold ₹{r.panic_out_rs / 1e5:.1f}L during past market falls "
            f"({r.panic_share:.0%} of everything they ever withdrew), "
            f"₹{r.panic_loss_out_rs / 1e5:.1f}L of it below cost."
        )
        if armed:
            reason += f" Market is currently {abs(drawdown_now):.0%} off its peak — this list is armed."
        script = (
            f"Last big fall they pulled out ₹{r.panic_out_rs / 1e5:.0f}L near the bottom — "
            f"call now and ask them to do nothing for 72 hours."
        )
        rows.append(dict(list_type="crash_sellers", rank=i, client_id=int(r.client_id),
                          mv=round(r.mv, 2), reason=reason, script=script, score=round(r.freak_out, 2)))

    # sip_fragile
    pool = df[(df.mv > 0) & (df.sip_streams > 0)].copy()
    top = _blend_rank(pool, "freak_out")
    for i, r in enumerate(top.itertuples(), start=1):
        reason = (
            f"{int(r.sip_active)} of {int(r.sip_streams)} SIP streams still running; "
            f"{int(r.sip_stopped)} already stopped, {int(r.sip_stops_in_drawdown)} of those "
            f"stopped during a market fall."
        )
        if r.sip_active > 0:
            script = (
                f"They still run {int(r.sip_active)} SIP(s) — call and remind them "
                f"it buys more units exactly when prices are down."
            )
        else:
            script = (
                f"Their last SIP stopped {int(r.sip_stopped)} stream(s) back — "
                f"call and ask if they'd restart it now that prices are down."
            )
        rows.append(dict(list_type="sip_fragile", rank=i, client_id=int(r.client_id),
                          mv=round(r.mv, 2), reason=reason, script=script, score=round(r.freak_out, 2)))

    # disengaged (reuses wealth.client_churn_risk's own score, not recomputed)
    churn = pd.read_sql(
        "select client_id, mv, months_since_inflow, sip_stop_share, out12_share, disengagement_score "
        "from wealth.client_churn_risk",
        conn,
    )
    churn["mv"] = churn.mv.fillna(0.0).astype(float)
    top = _blend_rank(churn, "disengagement_score")
    for i, r in enumerate(top.itertuples(), start=1):
        sip_txt = "no SIP history" if pd.isna(r.sip_stop_share) else f"{r.sip_stop_share:.0%} of SIPs stopped"
        reason = (
            f"No fresh money in {r.months_since_inflow:.0f} months, {sip_txt}, "
            f"{r.out12_share:.0%} of book pulled out in the last year."
        )
        script = (
            f"It's been {r.months_since_inflow:.0f} months since new money came in — "
            f"call to reconnect and ask if anything's changed."
        )
        rows.append(dict(list_type="disengaged", rank=i, client_id=int(r.client_id),
                          mv=round(r.mv, 2), reason=reason, script=script,
                          score=round(float(r.disengagement_score), 2)))

    return rows, armed, drawdown_now


def main() -> int:
    conn = connect()
    rows, armed, drawdown_now = compute_all(conn)

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.call_lists")
    cur.execute(
        """create table wealth.call_lists (
             list_type text not null,
             rank int not null,
             client_id bigint not null references wealth.clients(client_id),
             mv numeric(18,2), reason text, script text, score numeric(8,2),
             primary key (list_type, rank)
           )"""
    )
    execute_values(
        cur,
        "insert into wealth.call_lists (list_type, rank, client_id, mv, reason, script, score) values %s",
        [(r["list_type"], r["rank"], r["client_id"], r["mv"], r["reason"], r["script"], r["score"])
         for r in rows],
        page_size=500,
    )
    cur.execute("revoke all on wealth.call_lists from anon, authenticated")
    conn.commit()

    n_lists = len({r["list_type"] for r in rows})
    print(f"call lists: {n_lists} lists × {TOP_N} rows")
    print(f"crash_sellers ARMED={armed} (bench {drawdown_now:+.1%} off running peak)")
    names = pd.read_sql("select client_id, full_name from wealth.clients", conn).set_index("client_id").full_name
    for lt in ("crash_sellers", "sip_fragile", "disengaged"):
        print(f"\n{lt} top 3:")
        for r in [r for r in rows if r["list_type"] == lt][:3]:
            nm = names.get(r["client_id"], "?")
            print(f"  #{r['rank']} {nm} · ₹{r['mv'] / 1e5:.1f}L · score {r['score']}")
            print(f"     reason: {r['reason']}")
            print(f"     script: {r['script']}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
