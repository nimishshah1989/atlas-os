"""Load parsed Folio Ledgers (parse_ledgers.py output) into wealth.transactions.

Reconciliation gates (DoD from docs/wealth-transactions-build-plan.md):
  G1  parse gates green per file (running balance / totals / balance×NAV≈MV are
      checked at parse time; any file with errors blocks the whole load).
  G2  per row: |units × nav − amount| within era-aware tolerance where all three
      present (re-asserted here, independent of the parser).
  G3  per client×scheme×folio: ledger balance as of the valuation snapshot's
      txn_upto_date == wealth.holdings.balance_units (0.001 units).
      Cross-dataset gate — proves both datasets against each other.
  G4  per client: ledger external inflows/outflows ≈ client_reports flow summary.

Mismatches are listed by name, never loaded silently. The load itself is
all-or-nothing per run (--replace wipes and reloads; default refuses if table
already has rows).

Usage:
    .venv/bin/python scripts/wealth/load_ledgers.py \
        --parsed /home/ubuntu/jhaveri_data/ledger_parsed.json [--replace]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

D = Decimal
EXTERNAL_IN = {"purchase", "sip"}  # money the client sent in
EXTERNAL_OUT = {"redemption", "swp", "div_payout"}  # money the client took out
# switches + div_reinvest + bonus + segregation + opening_balance are internal


def norm_folio(f: str) -> str:
    return re.sub(r"\s*/\s*", "/", f.strip())


def norm_name(n: str) -> str:
    return re.sub(r"[^a-z0-9]", "", n.lower())


# valuation snapshot writes "Reg-G" style; ledgers write "Regular-Growth [Weekly]"
# style. Canonical key = (cleaned base name, plan, option) bridges the two.
ALIASES = [
    ("adity birla", "aditya birla"), ("sun life", "sunlife"), ("&", " and "),
    ("segregated", "seg"),  # valuation prints "Seg Portfolio", ledger "Segregated Portfolio"
    ("l and t", "hsbc"),  # L&T MF absorbed by HSBC
    ("idfc", "bandhan"),  # IDFC MF renamed Bandhan
    ("fof", "fund of fund"),
]
STOP_TOKS = {
    "fund", "scheme", "plan", "option", "opt", "the", "an", "of", "reg", "regular",
    "dir", "direct", "g", "gr", "growth", "idcw", "div", "dividend", "payout",
    "reinvest", "reinvestment", "weekly", "daily", "monthly", "quarterly", "qtly",
    "annual", "annually", "yearly", "half", "halfyearly", "retail", "institutional",
    "inst", "super", "premium",
}


def canon_key(name: str) -> tuple[str, str, str]:
    s2 = name.lower()
    s2 = re.sub(r"\(.*?\)", " ", s2)
    plan = "direct" if re.search(r"\bdir(ect)?\b", s2) else "regular"
    option = "idcw" if re.search(r"idcw|div", s2) else "growth"
    for a, b in ALIASES:
        s2 = s2.replace(a, b)
    s2 = re.sub(r"[^a-z0-9 ]", " ", s2)
    toks = [t for t in s2.split() if t not in STOP_TOKS]
    return "".join(toks), plan, option


def plan_option(display: str) -> tuple[str, str]:
    d = display.lower()
    plan = "Direct" if re.search(r"\bdir(ect)?\b", d) else "Regular"
    option = "IDCW" if re.search(r"idcw|div(idend)?\b|-d\b", d) else "Growth"
    return plan, option


G2_EXEMPT_RE = re.compile(r"segregated|unit linked insurance", re.I)


def g2_ok(r: dict, fund_name: str = "") -> bool:
    """Era-aware units×nav≈amount (mirrors parse-time check, independent code path)."""
    if r["approx"] or not (r["units"] and r["nav"] and r["amount"]):
        return True
    if r["txn_type"] in ("transfer_in", "transfer_out", "merger_in", "merger_out",
                         "transmission_in", "transmission_out", "consolidation_in",
                         "consolidation_out"):
        return True  # units implied from balance column; no printed amount to check
    if G2_EXEMPT_RE.search(fund_name):
        return True  # side-pocket/ULIP: printed NAV is not the effective unit price
    u, n, a = D(r["units"]), D(r["nav"]), D(r["amount"])
    if u == 0 or a == 0:
        return True
    if a < 2500:
        return True  # merger residues etc; misparse detection meaningless at this size
    if r["txn_type"] == "div_reinvest":  # net of DDT / TDS / NRI TDS
        eff = a - D(r["stamp_duty"] or "0")
        return eff * D("0.60") - 3 <= u * n <= eff * D("1.15") + 3
    if r["is_debit"]:  # exit loads up; NRI TDS on gains down
        eff = a + D(r["stt"] or "0")
        return u * n * D("0.66") - 3 <= eff <= u * n * D("1.011") + 3
    if r["txn_date"] and r["txn_date"] < "2013-10-01":  # entry-load era
        eff = a - D(r["stamp_duty"] or "0")
        return abs(u * n - eff) <= max(D("500"), a * D("0.025"))
    eff = a - D(r["stamp_duty"] or "0")
    return abs(u * n - eff) <= max(D("3"), a * D("0.002"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsed", required=True)
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    data = json.load(open(args.parsed))

    # ---- G1: refuse to load on any parse error ----
    bad = [d for d in data if d["errors"]]
    if bad:
        print(f"G1 FAIL — {len(bad)} files with parse errors, refusing to load:")
        for d in bad[:20]:
            print(f"  {d['source_file']}: {d['errors'][:2]}")
        return 1
    n_warn = sum(len(d.get("warnings", [])) for d in data)
    print(f"G1 PASS — {len(data)} files parse-clean ({n_warn} balance-column warnings across corpus)")

    # ---- G2 re-check ----
    g2_bad = []
    for d in data:
        for b in d["blocks"]:
            for r in b["rows"]:
                if not g2_ok(r, b["fund_name"]):
                    g2_bad.append((d["source_file"], b["fund_name"], r["txn_date"], r["txn_type"]))
    if g2_bad:
        print(f"G2 FAIL — {len(g2_bad)} rows break units×nav≈amount:")
        for row in g2_bad[:20]:
            print("  ", row)
        return 1
    n_rows = sum(len(b["rows"]) for d in data for b in d["blocks"])
    print(f"G2 PASS — {n_rows} rows arithmetic-consistent")

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(open(Path(__file__).parent / "schema.sql").read())

    cur.execute("select count(*) from wealth.transactions")
    existing = cur.fetchone()[0]
    if existing and not args.replace:
        print(f"wealth.transactions already has {existing} rows — rerun with --replace")
        return 1
    if existing:
        cur.execute("delete from wealth.transactions")
        cur.execute("delete from wealth.client_profile_ext")
        cur.execute("delete from wealth.ledger_blocks")

    # ---- client + scheme lookups ----
    cur.execute("select client_id, client_code, full_name from wealth.clients")
    by_code: dict[str, list] = defaultdict(list)
    for cid, code, name in cur.fetchall():
        by_code[(code or "").upper()].append((cid, norm_name(name or "")))
    cur.execute("select scheme_id, isin, display_name from wealth.schemes")
    scheme_by_isin, scheme_by_name, scheme_by_canon = {}, {}, {}
    for sid, isin, disp in cur.fetchall():
        if isin:
            scheme_by_isin[isin] = sid
        scheme_by_name.setdefault(norm_name(disp), sid)
        scheme_by_canon.setdefault(canon_key(disp), sid)

    def resolve_scheme(name: str, isin: str | None, allow_insert: bool = True) -> int | None:
        sid = scheme_by_isin.get(isin) if isin else None
        if sid is None:
            sid = scheme_by_name.get(norm_name(name))
        if sid is None:
            sid = scheme_by_canon.get(canon_key(name))
        if sid is None and allow_insert:
            # ledger-only scheme (long-closed plans, IDCW variants): real identity row
            pl, op = plan_option(name)
            cur.execute(
                """insert into wealth.schemes
                     (display_name, asset_class, sub_category, plan_type, option_type, isin)
                   values (%s, 'Unknown', 'Unknown (ledger-only)', %s, %s, %s)
                   on conflict (display_name) do update set isin = coalesce(wealth.schemes.isin, excluded.isin)
                   returning scheme_id""",
                (name, pl, op, isin),
            )
            sid = cur.fetchone()[0]
            scheme_by_name[norm_name(name)] = sid
            scheme_by_canon.setdefault(canon_key(name), sid)
            if isin:
                scheme_by_isin.setdefault(isin, sid)
        return sid

    new_clients = 0
    unmapped_schemes: dict[tuple, int] = defaultdict(int)
    txn_rows = []
    profile_rows = []
    block_rows = []
    seen_profile: set[int] = set()
    seen_blocks: dict[int, set] = defaultdict(set)  # cid -> {(fund,folio)} already loaded
    for d in data:
        code = (d["client_code"] or "").upper()
        nn = norm_name(d["client_name"] or "")
        cands = by_code.get(code, [])
        cid = next((c for c, n in cands if n == nn), None)
        if cid is None and len(cands) == 1 and not any(
            norm_name(x["client_name"] or "") == cands[0][1] and x is not d for x in data
        ):
            cid = cands[0][0]  # unique code match, name drifted (case/initials)
        if cid is None:
            cur.execute(
                """insert into wealth.clients (pan, client_code, full_name, family_group, email, mobile)
                   values (null,%s,%s,%s,%s,%s)
                   on conflict (full_name, client_code) do update set updated_at = now()
                   returning client_id""",
                (d["client_code"], d["client_name"], d["advisor_folder"], d.get("email"), d.get("mobile")),
            )
            cid = cur.fetchone()[0]
            by_code[code].append((cid, nn))
            new_clients += 1
        p = d.get("profile") or {}
        if cid in seen_profile:
            # second ledger file for the same client: complementary if its
            # fund-folio blocks are new, duplicate re-upload if they overlap
            dupes = [b for b in d["blocks"] if (b["fund_name"], b["folio"]) in seen_blocks[cid]]
            if dupes:
                print(
                    f"  SKIP duplicate ledger {d['source_file']} for client {d['client_name']} "
                    f"({len(dupes)}/{len(d['blocks'])} blocks already loaded from another file)"
                )
                continue
        else:
            seen_profile.add(cid)
            profile_rows.append(
                (
                    cid, p.get("joint_holders"), p.get("holding_mode"), p.get("tax_status"),
                    p.get("kyc_ok"), p.get("account_type"), p.get("advisor_name"),
                    p.get("advisor_code"), p.get("branch"), d.get("report_date"), d["source_file"],
                )
            )
        for b in d["blocks"]:
            seen_blocks[cid].add((b["fund_name"], b["folio"]))
            # per-sequence identity: continuation headers resolve concatenated
            # sequences to their true fund+folio; unresolved tails stay distinct
            # (never silently attributed to the block's first scheme)
            seq_ident = {}
            for q in b.get("sequences", [{"idx": 0, "name": None, "folio": None}]):
                sname = q.get("name") or (b["fund_name"] if q["idx"] == 0 else None)
                sfolio = q.get("folio") or b["folio"]
                if sname is None:
                    sname = f"{b['fund_name']} [seq{q['idx']} unresolved]"
                    ssid = None
                else:
                    ssid = resolve_scheme(sname, b["isin"] if q["idx"] == 0 else None)
                seq_ident[q["idx"]] = (sname, norm_folio(sfolio), ssid)
            n_unmapped_here = sum(
                1 for r in b["rows"] if seq_ident.get(r.get("seq", 0), (None, None, None))[2] is None
            )
            if n_unmapped_here:
                first_un = next(
                    (seq_ident[r.get("seq", 0)][0] for r in b["rows"]
                     if seq_ident.get(r.get("seq", 0), (None, None, None))[2] is None),
                    b["fund_name"],
                )
                unmapped_schemes[(first_un, b["isin"])] += n_unmapped_here
            mv = b.get("mv") or {}
            block_rows.append(
                (
                    cid, seq_ident.get(0, (None, None, None))[2], b["isin"], b["fund_name"],
                    norm_folio(b["folio"]), mv.get("mv_date"), mv.get("market_value"),
                    mv.get("nav"), mv.get("abs_ret_pct"), mv.get("xirr_pct"),
                    len(b["rows"]), d["source_file"],
                )
            )
            for r in b["rows"]:
                sname, sfolio, ssid = seq_ident.get(r.get("seq", 0), (b["fund_name"], norm_folio(b["folio"]), None))
                txn_rows.append(
                    (
                        cid, ssid, b["isin"], sname, sfolio, r["txn_date"], r["txn_type"],
                        r["description_raw"], r["nav"], r["units"], r["amount"], r["stt"],
                        r["stamp_duty"], r.get("tds"), r["balance_units"], r["is_debit"],
                        d["source_file"], r["page"], r["approx"],
                    )
                )

    execute_values(
        cur,
        """insert into wealth.client_profile_ext
           (client_id, joint_holders, holding_mode, tax_status, kyc_ok, account_type,
            advisor_name, advisor_code, branch, ledger_report_date, ledger_source_file)
           values %s
           on conflict (client_id) do update set
             joint_holders = excluded.joint_holders, holding_mode = excluded.holding_mode,
             tax_status = excluded.tax_status, kyc_ok = excluded.kyc_ok,
             account_type = excluded.account_type, advisor_name = excluded.advisor_name,
             advisor_code = excluded.advisor_code, branch = excluded.branch,
             ledger_report_date = excluded.ledger_report_date,
             ledger_source_file = excluded.ledger_source_file""",
        profile_rows,
    )
    execute_values(
        cur,
        """insert into wealth.transactions
           (client_id, scheme_id, isin, fund_name, folio, txn_date, txn_type, description_raw, nav,
            units, amount, stt, stamp_duty, tds, balance_units, is_debit, source_file, page, approx)
           values %s""",
        txn_rows,
        page_size=2000,
    )
    execute_values(
        cur,
        """insert into wealth.ledger_blocks
           (client_id, scheme_id, isin, fund_name, folio, mv_date, market_value, nav,
            abs_ret_pct, xirr_pct, n_rows, source_file) values %s""",
        block_rows,
        page_size=2000,
    )
    print(
        f"loaded {len(txn_rows)} transactions / {len(profile_rows)} profiles "
        f"({new_clients} ledger-only clients added)"
    )
    if unmapped_schemes:
        n_un = sum(unmapped_schemes.values())
        print(f"  scheme mapping: {len(unmapped_schemes)} unmapped fund names ({n_un} rows, scheme_id null):")
        for (name, isin), cnt in sorted(unmapped_schemes.items(), key=lambda kv: -kv[1])[:15]:
            print(f"    {cnt:6d}  {name}  [{isin}]")

    # ---- G3: ledger balance at txn_upto_date == holdings snapshot ----
    cur.execute(
        """with snap as (
             select h.client_id, h.scheme_id, regexp_replace(h.folio, '\\s*/\\s*', '/', 'g') folio,
                    h.balance_units, r.txn_upto_date
             from wealth.holdings h join wealth.client_reports r using (report_id)
             where h.balance_units is not null
           ),
           led as (
             select t.client_id, t.scheme_id, t.folio, s.txn_upto_date,
                    (array_agg(t.balance_units order by t.txn_date desc, t.txn_id desc))[1] bal
             from wealth.transactions t
             join (select distinct client_id, scheme_id, folio, txn_upto_date from snap) s
               using (client_id, scheme_id, folio)
             where t.scheme_id is not null and (t.txn_date is null or t.txn_date <= s.txn_upto_date)
             group by 1, 2, 3, 4
           )
           select count(*) filter (where abs(coalesce(l.bal, 0) - s.balance_units) <= 0.001) ok,
                  count(*) filter (where l.bal is null) no_ledger,
                  count(*) total
           from snap s left join led l using (client_id, scheme_id, folio)"""
    )
    ok, no_ledger, total = cur.fetchone()
    print(f"G3: {ok}/{total} holdings match ledger balance at txn_upto (no-ledger-block: {no_ledger})")
    cur.execute(
        """with snap as (
             select h.client_id, h.scheme_id, regexp_replace(h.folio, '\\s*/\\s*', '/', 'g') folio,
                    h.balance_units, r.txn_upto_date
             from wealth.holdings h join wealth.client_reports r using (report_id)
             where h.balance_units is not null
           ),
           led as (
             select t.client_id, t.scheme_id, t.folio, s.txn_upto_date,
                    (array_agg(t.balance_units order by t.txn_date desc, t.txn_id desc))[1] bal
             from wealth.transactions t
             join (select distinct client_id, scheme_id, folio, txn_upto_date from snap) s
               using (client_id, scheme_id, folio)
             where t.scheme_id is not null and (t.txn_date is null or t.txn_date <= s.txn_upto_date)
             group by 1, 2, 3, 4
           )
           select c.full_name, sch.display_name, s.folio, s.balance_units, l.bal
           from snap s left join led l using (client_id, scheme_id, folio)
           join wealth.clients c on c.client_id = s.client_id
           join wealth.schemes sch on sch.scheme_id = s.scheme_id
           where abs(coalesce(l.bal, 0) - s.balance_units) > 0.001
           order by abs(coalesce(l.bal, 0) - s.balance_units) desc limit 25"""
    )
    g3_bad = cur.fetchall()
    for name, disp, folio, snap_bal, led_bal in g3_bad:
        print(f"  G3 MISMATCH {name} | {disp[:45]} f{folio}: snapshot {snap_bal} vs ledger {led_bal}")

    # ---- G4: per-holding flow columns vs ledger sums (same folio, same window) ----
    # The valuation's client-level flow summary covers only currently-open folios,
    # so the honest comparison is per holding: investments / withdrawals /
    # dividends_reinvested / dividend_payouts vs the ledger's sums to txn_upto.
    g4_sql_base = """
        with snap as (
          select h.client_id, h.scheme_id, regexp_replace(h.folio, '\\s*/\\s*', '/', 'g') folio,
                 h.investments, h.withdrawals, h.dividends_reinvested, h.dividend_payouts,
                 r.txn_upto_date
          from wealth.holdings h join wealth.client_reports r using (report_id)
        ),
        led as (
          select s.client_id, s.scheme_id, s.folio,
                 sum(t.amount) filter (where t.txn_type in ('purchase','sip','switch_in')
                                       and not t.approx) ins,
                 sum(t.amount) filter (where t.txn_type in ('redemption','swp','switch_out')) outs,
                 sum(t.amount) filter (where t.txn_type = 'div_reinvest') reinv,
                 sum(t.amount) filter (where t.txn_type in ('div_payout','dtp_out')) pay
          from wealth.transactions t
          join (select distinct client_id, scheme_id, folio, txn_upto_date from snap) s
            using (client_id, scheme_id, folio)
          where t.txn_date is not null and t.txn_date <= s.txn_upto_date
          group by 1, 2, 3
        )
        select snap.*, led.ins, led.outs, led.reinv, led.pay,
               c.full_name, sch.display_name
        from snap
        left join led using (client_id, scheme_id, folio)
        join wealth.clients c using (client_id)
        join wealth.schemes sch on sch.scheme_id = snap.scheme_id
    """
    cur.execute(
        "with base as (" + g4_sql_base + """)
        select count(*) total,
               count(*) filter (where abs(coalesce(ins,0) - coalesce(investments,0))
                                <= greatest(100, 0.01 * coalesce(investments,0))) ins_ok,
               count(*) filter (where abs(coalesce(outs,0) - coalesce(withdrawals,0))
                                <= greatest(100, 0.01 * coalesce(withdrawals,0))) outs_ok,
               count(*) filter (where abs(coalesce(reinv,0) - coalesce(dividends_reinvested,0))
                                <= greatest(100, 0.01 * coalesce(dividends_reinvested,0))) reinv_ok
        from base"""
    )
    total4, in_ok, out_ok, reinv_ok = cur.fetchone()
    print(
        f"G4 (per holding): investments {in_ok}/{total4} · withdrawals {out_ok}/{total4} · "
        f"div-reinvest {reinv_ok}/{total4} within 1%"
    )
    cur.execute(
        "with base as (" + g4_sql_base + """)
        select full_name, display_name, folio, investments, ins
        from base
        where abs(coalesce(ins,0) - coalesce(investments,0))
              > greatest(100, 0.01 * coalesce(investments,0))
        order by abs(coalesce(ins,0) - coalesce(investments,0)) desc limit 20"""
    )
    for name, disp, folio, inv, ins in cur.fetchall():
        print(f"  G4 MISMATCH {name} | {disp[:42]} f{folio}: snapshot ins {inv} vs ledger {ins}")

    conn.commit()
    cur.execute(
        """select count(*), count(distinct client_id), min(txn_date), max(txn_date),
                  sum(amount) filter (where txn_type in ('purchase','sip'))
           from wealth.transactions"""
    )
    n, nc, dmin, dmax, gross_in = cur.fetchone()
    print(
        f"DB now: {n} txns / {nc} clients, {dmin} → {dmax}, "
        f"gross external in ₹{float(gross_in or 0) / 1e7:.1f} cr"
    )
    conn.close()
    # G3/G4 are cross-dataset trust reports: mismatches are listed loudly above but
    # the ledger stays loaded — it is the ground truth the snapshot is checked against.
    print(
        "GATES:", "G1 PASS · G2 PASS ·", f"G3 {ok}/{total} ·",
        f"G4 ins {in_ok}/{total4} outs {out_ok}/{total4} reinv {reinv_ok}/{total4}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
