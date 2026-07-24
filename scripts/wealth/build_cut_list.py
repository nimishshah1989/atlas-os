"""Cut-list engine — Prompt 7 of the seven-prompt MF audit. One row per client.

Per client, decide which HELD funds are redundant-and-weak (safe to cut), in a
tax-efficient unwind order, plus the smallest fund set that keeps the same
look-through stock exposure.

  cut  = redundant ∩ weak, ordered cheapest-to-exit first.
         redundant = the "adds least NEW exposure" member of a >50% overlap pair
                     (smallest rupee exposure to stocks ONLY it holds).
         weak      = label mismatch OR bottom-quartile fund_rank OR a poor *scored*
                     fund_performance signal (insufficient_history is UNKNOWN, not weak).
  keep = greedy set-cover: fewest funds whose union of look-through holdings covers
         >= COVERAGE_TARGET_PCT of the portfolio's total look-through rupee exposure.
  Evidence-gated: no >50% pair and no weak fund -> cut=[] with the plain-language note.

Money (tax_if_sold_now sums) is computed in Decimal; only display-only look-through
rupee aggregates use float.
Usage: set -a; source .env; set +a; .venv/bin/python scripts/wealth/build_cut_list.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from decimal import Decimal

from build_overlap import latest_fund_weights
from engine_common import connect
from psycopg2.extras import execute_values

# Set-cover coverage target. 90% keeps the portfolio's material look-through bets
# while dropping the long tail of near-zero positions that inflate the fund count;
# the last ~10% of rupee exposure is spread over many tiny holdings that any
# broad-market fund already re-covers, so demanding 100% would defeat consolidation.
COVERAGE_TARGET_PCT = 90.0

CLEAN_NOTE = "nothing to cut — portfolio holds genuinely different bets"


def weak_funds(conn) -> dict[int, list[str]]:
    """scheme_id -> list of weak-signal reason strings. Absent = not weak.

    Bottom-quartile uses build_scorecard's exact convention
    (cat_rank/cat_size > 0.75 at the latest fund_rank_daily date). fund_performance
    contributes only on verdict='scored' (insufficient_history = unknown, never weak),
    and beat_count is used directionally (PR-vs-TR flatters funds ~1-1.5%/yr, so a
    scored fund that STILL beat in <half its windows is genuinely weak).
    """
    cur = conn.cursor()
    cur.execute(
        """
        with latest as (select max(date) d from atlas_foundation.fund_rank_daily)
        select s.scheme_id,
               (lc.verdict = 'mismatch')                              as label_mm,
               lc.category,
               (fr.cat_rank::float / nullif(fr.cat_size, 0) > 0.75)   as bottom_q,
               fr.cat_rank, fr.cat_size,
               (fp.verdict = 'scored')                                as scored,
               fp.dn_capture_pct, fp.beat_count, fp.windows
        from wealth.schemes s
        left join wealth.fund_label_check lc on lc.scheme_id = s.scheme_id
        left join atlas_foundation.fund_rank_daily fr
               on fr.mstar_id = s.mstar_id and fr.date = (select d from latest)
        left join wealth.fund_performance fp on fp.scheme_id = s.scheme_id
        """
    )
    out: dict[int, list[str]] = {}
    for sid, label_mm, cat, bottom_q, crank, csize, scored, dncap, beat, win in cur.fetchall():
        reasons: list[str] = []
        if label_mm:
            reasons.append(f"label mismatch ({cat})")
        if bottom_q:
            reasons.append(f"bottom-quartile fund_rank ({crank}/{csize})")
        if scored and dncap is not None and float(dncap) > 100:
            reasons.append(f"downside capture {float(dncap):.0f}% (fell more than benchmark)")
        if scored and beat is not None and win and beat < win / 2.0:
            reasons.append(f"beat benchmark only {beat}/{win} rolling windows")
        if reasons:
            out[sid] = reasons
    return out


def set_cover(fund_stocks: dict, port_exp: dict, total_exp: float):
    """Greedy max-coverage: fewest funds to cover >= COVERAGE_TARGET_PCT of total_exp.

    Returns [(scheme_id, marginal_rupees_covered)] in pick order. Each step adds the
    fund contributing the most not-yet-covered portfolio rupee exposure.
    """
    if total_exp <= 0:
        return []
    target = total_exp * COVERAGE_TARGET_PCT / 100.0
    covered_isins: set = set()
    covered_rs = 0.0
    chosen: list[tuple[int, float]] = []
    remaining = set(fund_stocks)
    while covered_rs < target and remaining:
        best_sid, best_gain = None, 0.0
        for sid in remaining:
            gain = sum(port_exp[i] for i in fund_stocks[sid] if i not in covered_isins)
            if gain > best_gain:
                best_gain, best_sid = gain, sid
        if best_sid is None:  # nothing adds new exposure
            break
        chosen.append((best_sid, best_gain))
        covered_isins |= set(fund_stocks[best_sid])
        covered_rs += best_gain
        remaining.discard(best_sid)
    return chosen


def main() -> int:
    conn = connect()
    cur = conn.cursor()
    fw = latest_fund_weights(conn)  # mstar_id -> {isin: (name, weight_pct)}
    weak = weak_funds(conn)  # scheme_id -> [reasons]

    cur.execute(
        """select h.client_id, h.scheme_id, s.mstar_id, s.display_name, sum(h.market_value)
           from wealth.holdings h join wealth.schemes s using (scheme_id)
           where h.market_value > 0 and s.mstar_id is not null
           group by 1, 2, 3, 4"""
    )
    by_client: dict[int, list] = defaultdict(list)
    for cid, sid, mid, name, mv in cur.fetchall():
        if mid in fw:  # only funds with real look-through participate
            by_client[cid].append((sid, mid, name, mv))

    # exit tax (Decimal money) + exit-load flag, per client x scheme, over OPEN lots
    cur.execute(
        """select client_id, scheme_id, coalesce(sum(tax_if_sold_now), 0),
                  bool_or(holding_days <= 365)
           from wealth.lots where status = 'open' and scheme_id is not null
           group by 1, 2"""
    )
    exit_tax: dict[tuple[int, int], Decimal] = {}
    short_hold: dict[tuple[int, int], bool] = {}
    for cid, sid, tax, short in cur.fetchall():
        exit_tax[(cid, sid)] = Decimal(tax)
        short_hold[(cid, sid)] = bool(short)

    cur.execute(
        "select client_id, scheme_a, scheme_b from wealth.client_fund_overlap where overlap_pct > 50"
    )
    pairs: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for cid, a, b in cur.fetchall():
        pairs[cid].append((a, b))

    rows = []
    n_with_cut = 0
    for cid, funds in by_client.items():
        # portfolio look-through: rupee exposure per stock + who holds each stock
        port_exp: dict[str, float] = defaultdict(float)
        holders: dict[str, set] = defaultdict(set)
        fund_stocks: dict[int, dict[str, float]] = {}
        mv_by_sid: dict[int, float] = {}
        name_by_sid: dict[int, str] = {}
        for sid, mid, name, mv in funds:
            mvf = float(mv)
            mv_by_sid[sid] = mvf
            name_by_sid[sid] = name
            fs: dict[str, float] = {}
            for isin, (_nm, w) in fw[mid].items():
                r = mvf * w / 100.0
                port_exp[isin] += r
                holders[isin].add(sid)
                fs[isin] = r
            fund_stocks[sid] = fs
        total_exp = sum(port_exp.values())

        # redundant = the "least new exposure" member of each >50% pair.
        # unique_rs(f) = rupee exposure to stocks held ONLY by f; tie -> smaller position.
        unique_rs = {
            sid: sum(r for isin, r in fund_stocks[sid].items() if len(holders[isin]) == 1)
            for sid in mv_by_sid
        }
        redundant: set = set()
        for a, b in pairs.get(cid, []):
            if a in mv_by_sid and b in mv_by_sid:
                key_a = (unique_rs[a], mv_by_sid[a])
                key_b = (unique_rs[b], mv_by_sid[b])
                redundant.add(a if key_a <= key_b else b)

        # set-cover keep set (over ALL look-through funds)
        chosen = set_cover(fund_stocks, port_exp, total_exp)
        keep_sids = {sid for sid, _ in chosen}
        keep = [
            {
                "fund": name_by_sid[sid],
                "scheme_id": sid,
                "evidence": f"covers {gain / total_exp * 100:.1f}% of look-through exposure (min set-cover)",
            }
            for sid, gain in chosen
        ]
        min_fund_count = len(chosen)

        # cut = redundant ∩ weak, minus anything the minimal set needs (never cut a
        # fund that is load-bearing for coverage); order ascending exit_tax.
        cut_sids = [sid for sid in redundant if sid in weak and sid not in keep_sids]
        cut_sids.sort(key=lambda sid: exit_tax.get((cid, sid), Decimal(0)))
        cut = []
        for order, sid in enumerate(cut_sids, 1):
            tax = exit_tax.get((cid, sid), Decimal(0))
            load = (
                "exit load may apply (a lot held <365d)"
                if short_hold.get((cid, sid))
                else "no exit load (all lots >365d)"
            )
            reason = "; ".join(weak[sid]) + f"; redundant vs held peer; {load}"
            cut.append(
                {
                    "fund": name_by_sid[sid],
                    "scheme_id": sid,
                    "reason": reason,
                    "exit_tax_rs": float(round(tax, 2)),
                    "unwind_order": order,
                }
            )

        has_weak = any(sid in weak for sid in mv_by_sid)
        if cut:
            n_with_cut += 1
            note = (
                f"{len(cut)} fund(s) both redundant and weak → unwind cheapest-to-exit first; "
                f"min set-cover keeps {min_fund_count} of {len(funds)} to hold the same exposure"
            )
        elif not pairs.get(cid) and not has_weak:
            note = CLEAN_NOTE
        else:
            note = (
                "no clean cut — redundant funds are performing, or weak funds are unique bets; "
                f"min set-cover keeps {min_fund_count} of {len(funds)}"
            )
        rows.append((cid, json.dumps(keep), json.dumps(cut), min_fund_count, note))

    cur.execute("drop table if exists wealth.cut_list")
    cur.execute(
        """create table wealth.cut_list (
            client_id bigint primary key, keep jsonb, cut jsonb,
            min_fund_count int, note text)"""
    )
    execute_values(cur, "insert into wealth.cut_list values %s", rows)
    cur.execute("revoke all on wealth.cut_list from anon, authenticated")
    conn.commit()
    print(
        f"cut_list: {len(rows)} clients, {n_with_cut} with >=1 redundant-and-weak cut, "
        f"{len(rows) - n_with_cut} with nothing to cut"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
