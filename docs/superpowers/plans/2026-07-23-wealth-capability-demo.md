# Wealth Capability Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the PROFILE/PREDICT/PRESCRIBE client-intelligence engine (8 new builders) and the plain-language RM frontend, published as a new private artifact, all computed from existing `wealth.*` + `atlas_foundation.*` tables.

**Architecture:** Each engine is a standalone script in `scripts/wealth/` following the established pattern (repo `.venv`, `ATLAS_DB_URL`, `engine_common.connect()`, drop/create its derived table, revoke anon, print a self-check summary). `build_audit_packs.py` assembles everything into per-client JSON; `narrate_audit_packs.py` adds validated plain-language prose; `build_capability_app.py` emits one self-contained HTML app verified in headless browse before artifact publish.

**Tech Stack:** Python 3.12 (repo `.venv`: pandas/numpy/psycopg2), Postgres (Supabase), vanilla JS + inline CSS single-file frontend, `claude -p` CLI for narration, gstack browse for verification.

## Global Constraints

- **Rule #0:** no synthetic data anywhere, including tests — every test reads real rows from the live DB (read-only) and asserts on real computed output.
- Money = `numeric` in DB; python `Decimal` for tax math, float OK for display aggregates.
- Every derived table: `drop table if exists` + create + `revoke all ... from anon, authenticated`.
- Language rules (frontend + narration): never show XIRR/alpha/disposition/PGR-PLR/counterfactual; use "yearly growth", "ahead of/behind the index fund", "sells winners, keeps losers", "what-if". No table visible without opening an expander.
- Narration validator: any number in prose absent from the section payload → hard fail for that section.
- All new scripts run as `.venv/bin/python scripts/wealth/<name>.py` from repo root with `.env` sourced. Tests run as `.venv/bin/python -m pytest tests/wealth/<file> -v` (explicit path; CI's `-m unit` sweep does not pick these up — they need the DB).
- Frontend: both themes via tokens; Indian formatting (₹, L/cr, `en-IN` locale); `tabular-nums`; no external requests (artifact CSP); no `NaN` in embedded JSON (`allow_nan=False`).
- Commits after every task, message style `feat(wealth): ...`.

**Design tokens (frontend, locked here so no executor improvises):**
- Identity: "ledger book, modern hand" — warm paper, ink, one deep peacock accent. Deliberately NOT the dossier's teal-on-grey.
- Light: `--paper:#FAF7F1 --card:#FFFFFF --ink:#232019 --muted:#6B6357 --line:#E7E0D4 --accent:#0E5A6D --good:#256C3C --warn:#9A6A0A --crit:#A63A32 --soft:#0E5A6D12`
- Dark: `--paper:#14120E --card:#1C1915 --ink:#EDE7DC --muted:#9A917F --line:#2E2A22 --accent:#4FB3C9 --good:#57BE7C --warn:#DFA83D --crit:#E06B5F --soft:#4FB3C91F`
- Type: display `Georgia, 'Times New Roman', serif` for chapter headlines and big numbers; UI/body `-apple-system, 'Segoe UI', Roboto, sans-serif`; numbers always `font-variant-numeric: tabular-nums`.
- Big-number style: serif, `clamp(40px,7vw,72px)`, tight letter-spacing; one per screen.

---

### Task 1: Overlap engine (`build_overlap.py`)

**Files:**
- Create: `scripts/wealth/build_overlap.py`
- Test: `tests/wealth/test_overlap.py`

**Interfaces:**
- Consumes: `wealth.holdings` (current snapshot, scheme_id+market_value), `wealth.schemes.mstar_id`, `atlas_foundation.de_mf_holdings` (mstar_id, isin, holding_name, weight_pct, as_of_date — use each fund's latest as_of_date only).
- Produces: table `wealth.client_overlap(client_id bigint, eff_bets numeric(8,2), top_stock_isin text, top_stock_name text, top_stock_rs numeric(18,0), top10_share numeric(6,3), n_funds int, n_stocks int, primary key(client_id))` and `wealth.client_fund_overlap(client_id bigint, scheme_a bigint, scheme_b bigint, overlap_pct numeric(6,2))` (overlap = Σ min(w_a, w_b) over shared ISINs, %). Function `latest_fund_weights(conn) -> dict[mstar_id, dict[isin,(name,weight)]]`.

- [ ] **Step 1: Write the failing test** (real data: pick two widely-held real funds at runtime)

```python
# tests/wealth/test_overlap.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set -a && source .env && set +a && .venv/bin/python -m pytest tests/wealth/test_overlap.py -v`
Expected: FAIL `ModuleNotFoundError: build_overlap`

- [ ] **Step 3: Write the engine**

```python
# scripts/wealth/build_overlap.py
"""Per-client fund-overlap: pairwise overlap, true stock exposure, effective bets.

overlap(A,B) = sum over shared ISINs of min(weight_A, weight_B) — the standard
'common portfolio' measure. eff_bets = 1 / sum(w_i^2) (inverse Herfindahl) over the
client's look-through stock weights.
Usage: .venv/bin/python scripts/wealth/build_overlap.py
"""
from __future__ import annotations
import sys
from collections import defaultdict
from engine_common import connect
from psycopg2.extras import execute_values


def latest_fund_weights(conn):
    cur = conn.cursor()
    cur.execute(
        """select h.mstar_id, h.isin, max(h.holding_name), sum(h.weight_pct)
           from atlas_foundation.de_mf_holdings h
           join (select mstar_id, max(as_of_date) d from atlas_foundation.de_mf_holdings
                 group by 1) l on l.mstar_id = h.mstar_id and l.d = h.as_of_date
           where h.isin is not null and h.weight_pct > 0
           group by 1, 2"""
    )
    out: dict = defaultdict(dict)
    for mid, isin, name, w in cur.fetchall():
        out[mid][isin] = (name, float(w))
    return out


def pairwise_overlap(wa: dict, wb: dict) -> float:
    return round(sum(min(wa[i][1], wb[i][1]) for i in wa.keys() & wb.keys()), 2)


def main() -> int:
    conn = connect(); cur = conn.cursor()
    fw = latest_fund_weights(conn)
    cur.execute(
        """select h.client_id, h.scheme_id, s.mstar_id, h.market_value::float
           from wealth.holdings h join wealth.schemes s using (scheme_id)
           where h.market_value > 0 and s.mstar_id is not null"""
    )
    rows = cur.fetchall()
    by_client = defaultdict(list)
    for cid, sid, mid, mv in rows:
        if mid in fw:
            by_client[cid].append((sid, mid, mv))
    o_rows, p_rows = [], []
    for cid, funds in by_client.items():
        stock = defaultdict(float); names = {}
        total_mv = sum(mv for _, _, mv in funds)
        for _, mid, mv in funds:
            for isin, (name, w) in fw[mid].items():
                stock[isin] += mv * w / 100.0
                names[isin] = name
        if not stock or total_mv <= 0:
            continue
        wts = {i: v / total_mv for i, v in stock.items()}
        herf = sum(w * w for w in wts.values())
        eff = round(1.0 / herf, 2) if herf > 0 else None
        top = sorted(stock.items(), key=lambda kv: -kv[1])
        top10 = round(sum(v for _, v in top[:10]) / total_mv, 3)
        o_rows.append((cid, eff, top[0][0], names[top[0][0]][:80], round(top[0][1]),
                       top10, len(funds), len(stock)))
        for i in range(len(funds)):
            for j in range(i + 1, len(funds)):
                ov = pairwise_overlap(fw[funds[i][1]], fw[funds[j][1]])
                if ov >= 20:  # store meaningful pairs only
                    p_rows.append((cid, funds[i][0], funds[j][0], ov))
    cur.execute("drop table if exists wealth.client_overlap")
    cur.execute("""create table wealth.client_overlap (
        client_id bigint primary key, eff_bets numeric(8,2), top_stock_isin text,
        top_stock_name text, top_stock_rs numeric(18,0), top10_share numeric(6,3),
        n_funds int, n_stocks int)""")
    execute_values(cur, "insert into wealth.client_overlap values %s", o_rows)
    cur.execute("drop table if exists wealth.client_fund_overlap")
    cur.execute("""create table wealth.client_fund_overlap (
        client_id bigint, scheme_a bigint, scheme_b bigint, overlap_pct numeric(6,2))""")
    execute_values(cur, "insert into wealth.client_fund_overlap values %s", p_rows, page_size=2000)
    for t in ("client_overlap", "client_fund_overlap"):
        cur.execute(f"revoke all on wealth.{t} from anon, authenticated")
    conn.commit()
    print(f"overlap: {len(o_rows)} clients, {len(p_rows)} heavy pairs (>=20%), "
          f"median eff_bets {sorted(r[1] for r in o_rows if r[1])[len(o_rows)//2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `set -a && source .env && set +a && .venv/bin/python -m pytest tests/wealth/test_overlap.py -v`
Expected: PASS

- [ ] **Step 5: Run the engine, sanity-check output**

Run: `set -a && source .env && set +a && .venv/bin/python scripts/wealth/build_overlap.py`
Expected: `overlap: ~200+ clients, ... median eff_bets` between 15 and 120 (Indian MF look-through reality).

- [ ] **Step 6: Commit** — `git add scripts/wealth/build_overlap.py tests/wealth/test_overlap.py && git commit -m "feat(wealth): client fund-overlap + effective-bets engine"`

---

### Task 2: Label check engine (`build_label_check.py`)

**Files:**
- Create: `scripts/wealth/build_label_check.py`
- Test: `tests/wealth/test_label_check.py`

**Interfaces:**
- Consumes: `atlas_foundation.de_mf_holdings` (latest per fund), `atlas_foundation.equity_marketcap` (instrument_id, market_cap_cr) + `atlas_foundation.instrument_master` (instrument_id→isin) for SEBI ranks, `wealth.schemes` (mstar_id, sub_category, display_name) restricted to currently-held schemes.
- Produces: `wealth.fund_label_check(scheme_id bigint primary key, mstar_id text, category text, equity_pct numeric(6,2), large_pct numeric(6,2), mid_pct numeric(6,2), small_pct numeric(6,2), unclassified_pct numeric(6,2), verdict text, detail text)`. Verdict ∈ `ok | drift | mismatch | no_data`. Function `sebi_ranks(conn) -> dict[isin, 'large'|'mid'|'small']` (top 100 by mcap = large, 101–250 = mid, rest = small).

- [ ] **Step 1: Write the failing test**

```python
# tests/wealth/test_label_check.py
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
```

- [ ] **Step 2: Run to verify FAIL** — `... pytest tests/wealth/test_label_check.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Write the engine**

```python
# scripts/wealth/build_label_check.py
"""Does each held fund do what its name says? SEBI cap-split truth per fund.

SEBI: large = top 100 by full mcap, mid = 101-250, small = 251+. Category rules
encoded below (minimum mandates). Constituents without an equity mcap match are
'unclassified' (debt/cash/foreign/unlisted) — equity_pct counts classified equity.
Usage: .venv/bin/python scripts/wealth/build_label_check.py
"""
from __future__ import annotations
import re, sys
from engine_common import connect
from psycopg2.extras import execute_values

# (regex on wealth.schemes display/sub_category, rule fn(large, mid, small, equity) -> ok?)
CATEGORY_RULES = [
    (re.compile(r"large\s*(&|and)\s*mid", re.I), "Large & Mid Cap",
     lambda L, M, S, E: L >= 35 and M >= 35),
    (re.compile(r"large\s*cap", re.I), "Large Cap", lambda L, M, S, E: L >= 80 * E / 100),
    (re.compile(r"mid\s*cap", re.I), "Mid Cap", lambda L, M, S, E: M >= 65 * E / 100),
    (re.compile(r"small\s*cap", re.I), "Small Cap", lambda L, M, S, E: S >= 65 * E / 100),
    (re.compile(r"multi\s*cap", re.I), "Multi Cap", lambda L, M, S, E: L >= 25 and M >= 25 and S >= 25),
    (re.compile(r"flexi", re.I), "Flexi Cap", lambda L, M, S, E: E >= 65),
]


def sebi_ranks(conn):
    cur = conn.cursor()
    cur.execute(
        """select im.isin, row_number() over (order by m.market_cap_cr desc) rk
           from atlas_foundation.equity_marketcap m
           join atlas_foundation.instrument_master im using (instrument_id)
           where im.isin is not null and m.market_cap_cr is not null""")
    return {isin: ("large" if rk <= 100 else "mid" if rk <= 250 else "small")
            for isin, rk in cur.fetchall()}


def classify_fund(conn, mstar_id, ranks):
    cur = conn.cursor()
    cur.execute(
        """select isin, sum(weight_pct) from atlas_foundation.de_mf_holdings h
           where mstar_id = %s
             and as_of_date = (select max(as_of_date) from atlas_foundation.de_mf_holdings
                               where mstar_id = %s)
             and isin is not null group by 1""", (mstar_id, mstar_id))
    L = M = S = U = 0.0
    for isin, w in cur.fetchall():
        b = ranks.get(isin)
        if b == "large": L += float(w)
        elif b == "mid": M += float(w)
        elif b == "small": S += float(w)
        else: U += float(w)
    return dict(large_pct=round(L, 2), mid_pct=round(M, 2), small_pct=round(S, 2),
                unclassified_pct=round(U, 2), equity_pct=round(L + M + S, 2))


def main() -> int:
    conn = connect(); cur = conn.cursor()
    ranks = sebi_ranks(conn)
    cur.execute("""select distinct s.scheme_id, s.mstar_id, s.display_name, s.sub_category
                   from wealth.schemes s join wealth.holdings h using (scheme_id)
                   where s.mstar_id is not null""")
    rows = []
    for sid, mid, disp, sub in cur.fetchall():
        c = classify_fund(conn, mid, ranks)
        cat, verdict, detail = None, "no_data", ""
        if c["equity_pct"] + c["unclassified_pct"] > 0:
            name = f"{disp} {sub or ''}"
            for rx, label, rule in CATEGORY_RULES:
                if rx.search(name):
                    cat = label
                    ok = rule(c["large_pct"], c["mid_pct"], c["small_pct"], c["equity_pct"])
                    verdict = "ok" if ok else "mismatch"
                    detail = (f"label {label}: large {c['large_pct']}% mid {c['mid_pct']}% "
                              f"small {c['small_pct']}% (unclassified {c['unclassified_pct']}%)")
                    break
            else:
                cat, verdict = "Other", "ok"  # no cap mandate to check
        rows.append((sid, mid, cat, c["equity_pct"], c["large_pct"], c["mid_pct"],
                     c["small_pct"], c["unclassified_pct"], verdict, detail))
    cur.execute("drop table if exists wealth.fund_label_check")
    cur.execute("""create table wealth.fund_label_check (
        scheme_id bigint primary key, mstar_id text, category text,
        equity_pct numeric(6,2), large_pct numeric(6,2), mid_pct numeric(6,2),
        small_pct numeric(6,2), unclassified_pct numeric(6,2), verdict text, detail text)""")
    execute_values(cur, "insert into wealth.fund_label_check values %s", rows)
    cur.execute("revoke all on wealth.fund_label_check from anon, authenticated")
    conn.commit()
    n_bad = sum(1 for r in rows if r[8] == "mismatch")
    print(f"label check: {len(rows)} held funds, {n_bad} mismatch their label")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test → PASS.** Step 5: Run engine; expected `label check: ~300 held funds, small n mismatch`. Spot-read 3 mismatch rows — plausible (hybrids/flexi behaving large-cap).
- [ ] **Step 6: Commit** — `git commit -m "feat(wealth): SEBI label-check engine"`

---

### Task 3: Tax harvest engine (`build_tax_harvest.py`)

**Files:**
- Create: `scripts/wealth/build_tax_harvest.py`
- Test: `tests/wealth/test_tax_harvest.py`

**Interfaces:**
- Consumes: `wealth.lots` (status/buy_date/units/unit_basis/nav_now/tax_bucket/realized_gain/sell_date, equity via `wealth.schemes.asset_class`), `atlas_foundation.atlas_thresholds` (`portfolio_tax_ltcg_exemption_inr`, `portfolio_tax_ltcg_pct`).
- Produces: `wealth.tax_harvest(client_id bigint primary key, fy text, realized_ltcg numeric(18,0), headroom numeric(18,0), gain_candidates jsonb, gain_value numeric(18,0), tax_saved_if_harvested numeric(18,0), loss_candidates jsonb, loss_note text, carry_forward numeric(18,0))`. Rules encoded: FY = Apr–Mar; headroom = max(0, 1.25L − realized LTCG this FY); gain candidates = open equity LTCG lots (oldest first) filling headroom; **loss harvesting only recommended when realized LTCG exceeds the exemption** (exemption-before-set-off rule), else `loss_note` explains carry-forward-only.

- [ ] **Step 1: Failing test** (real client with open equity gains):

```python
# tests/wealth/test_tax_harvest.py
import os, sys
def test_headroom_and_candidates_real_client():
    sys.path.insert(0, "scripts/wealth")
    from build_tax_harvest import compute_client, current_fy_start, EXEMPT
    import engine_common
    conn = engine_common.connect()
    cur = conn.cursor()
    cur.execute("""select l.client_id from wealth.lots l join wealth.schemes s using (scheme_id)
                   where l.status='open' and s.asset_class='Equity' and l.tax_bucket='ltcg'
                     and l.unrealized_gain > 50000 limit 1""")
    cid = cur.fetchone()[0]
    r = compute_client(conn, cid)
    assert 0 <= r["headroom"] <= float(EXEMPT)
    assert r["gain_value"] <= r["headroom"] + 1  # never harvest past the exemption
    for c in r["gain_candidates"]:
        assert c["gain"] > 0 and c["bucket"] == "ltcg"
```

- [ ] **Step 2: FAIL run.** **Step 3: Implementation:**

```python
# scripts/wealth/build_tax_harvest.py
"""Per-client FY tax-harvest sheet: gain-harvest headroom in the Rs 1.25L LTCG
exemption (use-it-or-lose-it, resets 1 Apr; no wash-sale rule in India), loss
candidates gated by the exemption-before-set-off rule, carry-forward ledger.
Usage: .venv/bin/python scripts/wealth/build_tax_harvest.py
"""
from __future__ import annotations
import json, sys
from datetime import date
from decimal import Decimal
from engine_common import connect
from psycopg2.extras import execute_values, Json

def load_rates(cur):
    cur.execute("""select threshold_key, threshold_value from atlas_foundation.atlas_thresholds
                   where threshold_key in ('portfolio_tax_ltcg_exemption_inr','portfolio_tax_ltcg_pct')""")
    m = dict(cur.fetchall())
    return Decimal(str(m["portfolio_tax_ltcg_exemption_inr"])), Decimal(str(m["portfolio_tax_ltcg_pct"]))

EXEMPT = None  # set in main/compute via load_rates; tests import after first call

def current_fy_start(today=None) -> date:
    t = today or date.today()
    return date(t.year if t.month >= 4 else t.year - 1, 4, 1)

def indian_fy_label(d: date) -> str:
    s = d.year if d.month >= 4 else d.year - 1
    return f"FY{s % 100:02d}-{(s + 1) % 100:02d}"

def compute_client(conn, cid):
    global EXEMPT
    cur = conn.cursor()
    if EXEMPT is None:
        EXEMPT, _ = load_rates(cur)
    exempt, ltcg_rate = load_rates(cur)
    fy0 = current_fy_start()
    cur.execute("""select coalesce(sum(l.realized_gain),0) from wealth.lots l
                   join wealth.schemes s using (scheme_id)
                   where l.client_id=%s and l.status='closed' and s.asset_class='Equity'
                     and l.tax_bucket='ltcg' and l.sell_date >= %s and l.realized_gain > 0""",
                (cid, fy0))
    realized = Decimal(str(cur.fetchone()[0]))
    headroom = max(Decimal(0), exempt - realized)
    cur.execute("""select l.lot_id, l.fund_name, l.buy_date, l.units, l.unit_basis, l.nav_now,
                          l.unrealized_gain
                   from wealth.lots l join wealth.schemes s using (scheme_id)
                   where l.client_id=%s and l.status='open' and s.asset_class='Equity'
                     and l.tax_bucket='ltcg' and l.unrealized_gain > 0
                   order by l.buy_date nulls first""", (cid,))
    gains, used = [], Decimal(0)
    for lot_id, fn, bd, units, basis, nav, ug in cur.fetchall():
        if used >= headroom:
            break
        take_gain = min(Decimal(str(ug)), headroom - used)
        frac = take_gain / Decimal(str(ug))
        gains.append(dict(lot_id=lot_id, fund=fn[:60], buy_date=str(bd),
                          units=round(float(units) * float(frac), 3),
                          gain=round(float(take_gain)), bucket="ltcg"))
        used += take_gain
    # losses: only actionable when realized LTCG beyond exemption exists
    cur.execute("""select l.lot_id, l.fund_name, l.unrealized_gain from wealth.lots l
                   join wealth.schemes s using (scheme_id)
                   where l.client_id=%s and l.status='open' and s.asset_class='Equity'
                     and l.unrealized_gain < -5000 order by l.unrealized_gain limit 10""", (cid,))
    losses = [dict(lot_id=i, fund=f[:60], loss=round(float(g))) for i, f, g in cur.fetchall()]
    loss_note = ("actionable: realized gains exceed the exemption — set-off saves 12.5%"
                 if realized > exempt else
                 "hold: gains are within the tax-free band; harvesting losses now only "
                 "creates a carry-forward (8 years, needs on-time ITR)")
    # carry-forward: net realized losses by FY (informational)
    cur.execute("""select coalesce(sum(realized_gain),0) from wealth.lots
                   where client_id=%s and status='closed' and realized_gain < 0
                     and sell_date >= %s""", (cid, fy0))
    cf = Decimal(str(cur.fetchone()[0]))
    return dict(fy=indian_fy_label(fy0), realized_ltcg=round(float(realized)),
                headroom=round(float(headroom)), gain_candidates=gains,
                gain_value=round(float(used)),
                tax_saved_if_harvested=round(float(used * ltcg_rate)),
                loss_candidates=losses, loss_note=loss_note,
                carry_forward=round(float(-cf)))

def main() -> int:
    conn = connect(); cur = conn.cursor()
    cur.execute("select distinct client_id from wealth.lots where status='open'")
    cids = [r[0] for r in cur.fetchall()]
    rows = []
    for cid in cids:
        r = compute_client(conn, cid)
        rows.append((cid, r["fy"], r["realized_ltcg"], r["headroom"], Json(r["gain_candidates"]),
                     r["gain_value"], r["tax_saved_if_harvested"], Json(r["loss_candidates"]),
                     r["loss_note"], r["carry_forward"]))
    cur.execute("drop table if exists wealth.tax_harvest")
    cur.execute("""create table wealth.tax_harvest (
        client_id bigint primary key, fy text, realized_ltcg numeric(18,0),
        headroom numeric(18,0), gain_candidates jsonb, gain_value numeric(18,0),
        tax_saved_if_harvested numeric(18,0), loss_candidates jsonb, loss_note text,
        carry_forward numeric(18,0))""")
    execute_values(cur, "insert into wealth.tax_harvest values %s", rows, page_size=500)
    cur.execute("revoke all on wealth.tax_harvest from anon, authenticated")
    conn.commit()
    tot = sum(r[6] for r in rows)
    print(f"tax harvest: {len(rows)} clients, cohort tax-saved-if-harvested ₹{tot/1e5:.1f}L this FY")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: test PASS. Step 5: run engine** — expected cohort saving in lakhs (~₹1.25L × 12.5% × n eligible). **Step 6: Commit** `feat(wealth): FY tax-harvest engine (gain headroom + set-off gating)`.

---

### Task 4: Value statement engine (`build_value_statement.py`)

**Files:**
- Create: `scripts/wealth/build_value_statement.py`
- Test: `tests/wealth/test_value_statement.py`

**Interfaces:**
- Consumes: `wealth.counterfactuals` (cf_sip_alive_rs, cf_no_panic_rs), `wealth.client_behaviour` (panic_out_rs, div_leak_rs), `wealth.advice_ledger` (alpha_1y_rs per client), `wealth.client_flags`/fee columns via `wealth.client_flags` (fee_save basis — reuse `client_analytics` fee outputs stored in dossier data; simplest real source: recompute from flags table if present else 0), `wealth.tax_harvest.tax_saved_if_harvested`, drawdown windows from `behaviour_fingerprints.drawdown_windows` + SIP txns for discipline value.
- Produces: `wealth.value_statements(client_id bigint primary key, sip_discipline_rs numeric(18,0), staying_power_rs numeric(18,0), advice_outcome_rs numeric(18,0), fee_save_yr_rs numeric(18,0), tax_headroom_rs numeric(18,0), coaching_opportunity_rs numeric(18,0), summary jsonb)`. Semantics (all realized/certain, labelled):
  - `sip_discipline_rs` = value today of units bought via SIP **inside drawdown windows** minus cash paid (their reward for continuing — real).
  - `staying_power_rs` = for non-panic clients: value today of units they held through drawdowns that panic-peers sold (computed as their drawdown-window holdings kept × growth since window end); for panic clients 0.
  - `advice_outcome_rs` = Σ alpha_1y_rs of their scored switches (realized).
  - `fee_save_yr_rs` = from closet-index flags (certain annual).
  - `tax_headroom_rs` = this FY's harvestable saving.
  - `coaching_opportunity_rs` = their panic + leakage + stopped-SIP counterfactual (what coaching could have saved — labelled opportunity, not achievement).

- [ ] **Step 1: Failing test:** real client with SIP-in-drawdown history → `sip_discipline_rs > 0`; a known panic client → `staying_power_rs == 0` and `coaching_opportunity_rs > 0`.

```python
# tests/wealth/test_value_statement.py
import sys
def test_components_real_clients():
    sys.path.insert(0, "scripts/wealth")
    from build_value_statement import compute_all
    import engine_common
    conn = engine_common.connect()
    rows = compute_all(conn)
    assert len(rows) > 150
    some_sip = [r for r in rows if r["sip_discipline_rs"] > 0]
    assert some_sip, "book has 1,353 SIP streams; discipline value must exist"
    panic = [r for r in rows if r["coaching_opportunity_rs"] > 100000]
    assert panic, "142 drawdown-sellers exist; opportunity must be non-empty"
```

- [ ] **Step 2: FAIL.** **Step 3:** implement `compute_all(conn) -> list[dict]` + `main()` writing the table (pattern identical to Task 3: drop/create/insert/revoke/print). SIP-in-drawdown value: join `wealth.transactions` sip rows with date in any drawdown window (import `drawdown_windows`, bench from `engine_common.nav_series`), value = units × scheme latest NAV (mapped schemes only) − amount. Staying-power: holdings balance at window start (from running balances) that remained at window end × NAV growth window-end→today, only for clients with `panic_share < 0.10`. Advice outcome: `select client_id, coalesce(sum(alpha_1y_rs),0) from wealth.advice_ledger group by 1`. Fee save: `select client_id, sum(est_value) from wealth.client_flags where rule like '%closet%' group by 1` (verify actual rule string at execution; fall back to 0 with a printed count if the flags table stores fees differently). Coaching opportunity: `panic_loss_out_rs + div_leak_rs + cf_sip_alive_rs` (each ≥0, labelled upper bound).
- [ ] **Step 4: PASS. Step 5: run** — print cohort totals per component (expect: discipline ₹ crores; opportunity ₹ tens of crores consistent with earlier findings). **Step 6: Commit** `feat(wealth): per-client realized value statement`.

---

### Task 5: Call lists + freak-out score (`build_call_lists.py`)

**Files:**
- Create: `scripts/wealth/build_call_lists.py`
- Test: `tests/wealth/test_call_lists.py`

**Interfaces:**
- Consumes: `wealth.client_behaviour`, `wealth.client_churn_risk`, `wealth.ledger_blocks` (book MV), bench NAV (drawdown state), SIP streams from `wealth.transactions`.
- Produces: `wealth.call_lists(list_type text, rank int, client_id bigint, mv numeric(18,2), reason text, script text, score numeric(8,2), primary key(list_type, rank))`. `list_type ∈ crash_sellers | sip_fragile | disengaged`. Freak-out score (transparent, documented weights — heuristic per MIT feature set, NOT a fitted model at n=234): `0.5·panic_share + 0.2·(1 − sip_active_share) + 0.2·chase_hot_share + 0.1·recent_seller` scaled 0–100. `crash_sellers` list is built always but flagged `armed` in reason text only when the bench sits >10% below its running peak (compute from `nav_series`).
- Scripts follow the one-action rule: e.g. `"Last big fall you sold ₹42L near the bottom — this time, do nothing for 72 hours and call us first."`

- [ ] Steps: failing test (top crash_seller row has panic_share > 0.25 and a script mentioning one action verb only — assert no ';' and single sentence), FAIL, implement, PASS, run (`call lists: 3 lists × 20 rows`), commit `feat(wealth): PREDICT call lists + freak-out score`.

---

### Task 6: Household roll-up (`build_household.py`)

**Files:**
- Create: `scripts/wealth/build_household.py`
- Test: `tests/wealth/test_household.py`

**Interfaces:**
- Consumes: `wealth.clients.family_group`, `wealth.client_profile_ext.joint_holders`, `wealth.ledger_blocks` MV, `wealth.transactions` (transmission_in/out events), `wealth.client_overlap`.
- Produces: `wealth.households(household_id bigint, client_id bigint, household_name text, members int, household_mv numeric(18,2), succession_flag text)` — household = clients sharing a normalized surname within the same `family_group` **or** appearing in each other's `joint_holders` string (normalized-name containment). `succession_flag`: `transmission_seen | single_holder_concentrated | none`.

- [ ] Steps: failing test on a real known family (Zinzuvadia cluster: ≥3 members resolve to one household; the Amin family shows `transmission_seen` — Prafulbhai is deceased-departed), FAIL, implement (union-find over the two edge types), PASS, run (expect ~120–160 households from 234 clients), commit `feat(wealth): household roll-up + succession flags`.

---

### Task 7: Audit-pack assembly (`build_audit_packs.py`)

**Files:**
- Create: `scripts/wealth/build_audit_packs.py`
- Test: `tests/wealth/test_audit_packs.py`

**Interfaces:**
- Consumes: every table above + `wealth.client_benchmark`, `wealth.client_behaviour`, `wealth.counterfactuals`, `wealth.client_flags`, `wealth.lots`, `wealth.holdings`, `wealth.households`.
- Produces: `wealth.audit_packs(client_id bigint, section text, payload jsonb, prose text, computed_asof date, primary key(client_id, section))` with sections exactly: `map, label_check, overlap, fees, benchmark, habits, value, actions` (8). Each payload self-contained for rendering: every number the frontend or narration will show. Missing-data sections get `payload = {"insufficient": true, "why": "<plain reason>"}` — never silently absent.

- [ ] **Step 1: failing integration test** — build packs for 3 real named clients (pick: highest-MV client, one panic client, one clean-A client, resolved by query not by hardcoded name), assert all 8 sections present, `map.total_mv > 0`, benchmark section has either verdict or insufficient-reason.
- [ ] Steps 2–5: FAIL → implement assembly (pure SELECT + dict-building; no new math; ~250 lines) → PASS → run for all clients (`audit packs: 220 clients × 8 sections`) → commit `feat(wealth): audit-pack assembler`.

---

### Task 8: Narration + validator (`narrate_audit_packs.py`)

**Files:**
- Create: `scripts/wealth/narrate_audit_packs.py`
- Test: `tests/wealth/test_narration_validator.py`

**Interfaces:**
- Consumes: `wealth.audit_packs.payload`.
- Produces: updates `wealth.audit_packs.prose`. Public functions: `render_prompt(section, payload) -> str` (fixed per-section templates in the stockizen voice, language rules enforced in the prompt), `validate(prose, payload) -> list[str]` (violations), `narrate(conn, client_id)`.
- Validator rule (exact): extract number tokens from prose via `re.findall(r"[\d][\d,]*\.?\d*", prose)`, normalize (strip commas), and for each with float value ≥ 10: require its normalized string to appear in `json.dumps(payload)` normalized the same way, allowing L/cr scaled forms (value×1e5, ×1e7, and rounded to 1–2 decimals). Violation → prose replaced by deterministic template text (`template_only(section, payload)`), and the incident counted in the run summary.
- Batch: `claude -p` (claude CLI on PATH), model default, one call per client (all sections in one prompt, JSON out), resumable (`where prose is null`), `--limit` flag for smoke runs.

- [ ] **Step 1: validator failing test** (pure, real payload pulled from DB): prose quoting a payload number passes; prose with an invented `₹99,999` fails.
- [ ] Steps: FAIL → implement → PASS → smoke `--limit 3` end-to-end (read the 3 clients' prose aloud-quality check: no jargon terms — assert banned-word list `["XIRR","alpha","disposition","PGR","PLR","counterfactual"]` absent) → full run (~220 calls, batch, ~30–45 min) → commit `feat(wealth): audit-pack narration with number validator`.

---

### Task 9: Frontend app (`build_capability_app.py` + `validate_wealth_app.py`)

**Files:**
- Create: `scripts/wealth/build_capability_app.py` (emits `/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html`)
- Create: `scripts/wealth/validate_wealth_app.py`
- Test: validation IS the test (post-build gate) — plus browse verification steps below.

**Interfaces:**
- Consumes: all `wealth.*` tables incl. audit_packs prose; dossier JSON not used (this app reads DB directly).
- Produces: one self-contained HTML (~2–4 MB) with `<script id="data" type="application/json">` holding `{book, chapters, call_lists, clients:{id: {profile, pack}}, households, asof}`; hash-routed screens `#book #calls #client/<id>`; design tokens from Global Constraints verbatim.

Layout contract (executor follows exactly):
- `#book`: 6 full-viewport chapters (scroll-snap + arrow keys). Each: eyebrow (chapter n), serif headline (the one sentence), one big serif number, one visual (chapter 2: ₹10L growth strip as inline SVG bars per year; chapter 3: 10 person-dots, 8 filled; chapter 4: three story cards; chapter 5: two stat pairs + wave list expander; chapter 6: three capability cards linking `#calls` and a sample `#client/`), and a `details` "how we know this".
- `#calls`: three filter chips, ranked rows (`name · ₹book · reason`, script line under, muted), click → client.
- `#client/<id>`: search box (datalist over all clients), profile header (household chip + 3 behaviour chips), then the 8 pack sections in order, each: section eyebrow (the check's name), prose paragraph (the narration), one big number (from payload `headline_value` — assembler guarantees it), optional mini-visual (overlap: effective-bets dial as SVG arc; fees: two-bar compare; benchmark: two-line growth compare), `details` expander with the numbers table + method note. Ends with Action List cards (action verb first, tax line under).
- `validate_wealth_app.py` gate: file parses as JSON-embedded HTML, `NaN` absent, all clients in data resolvable, byte size < 6 MB, then headless-browse: zero console errors on `#book`, `#calls`, and 3 real `#client/` pages (GSTACK_CHROMIUM_NO_SANDBOX=1, file copied under /tmp).

- [ ] Steps: write `validate_wealth_app.py` first (it will FAIL on missing file), implement builder + HTML/JS (single template string, ~600 lines), run validator → PASS, screenshot all three screens in browse and **Read the screenshots** (visual gate: serif big numbers render, chips wrap on 1280px, dark theme via `data-theme` toggle works), commit `feat(wealth): capability app frontend + validation gate`.

---

### Task 10: Orchestrator, full run, publish

**Files:**
- Create: `scripts/wealth/run_wealth_engine.sh`
- Modify: `scripts/wealth/README.md` (one paragraph: the engine chain + one-command refresh)

**Interfaces:** none new — sequences everything:

```bash
#!/usr/bin/env bash
# One-command refresh: engines → packs → narration → app → validate.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; source .env; set +a
PY=.venv/bin/python
for s in build_overlap build_label_check build_tax_harvest build_value_statement \
         build_call_lists build_household build_audit_packs; do
  echo "== $s"; $PY scripts/wealth/$s.py
done
$PY scripts/wealth/narrate_audit_packs.py "$@"
$PY scripts/wealth/build_capability_app.py
$PY scripts/wealth/validate_wealth_app.py
echo "READY: /home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html"
```

- [ ] Run full chain end-to-end clean (`bash scripts/wealth/run_wealth_engine.sh`), fix anything that surfaces, then publish the app as a **NEW artifact** (new file path ⇒ new URL, favicon `🧭`, title "Jhaveri Client Intelligence"), verify the published page loads via WebFetch, and commit `feat(wealth): engine orchestrator + capability app shipped`.
- [ ] Update memory (`wealth-transactions-engine.md`: append capability-demo state + new artifact URL).

---

## Self-review notes

- **Spec coverage:** overlap ✓(T1) label ✓(T2) tax ✓(T3) value ✓(T4) call-lists+freak-out ✓(T5) household ✓(T6) packs ✓(T7) narration+validator ✓(T8) frontend+language+design ✓(T9) orchestrator+publish ✓(T10). Bloat Check deferred per spec. Chapter copy numbers come from live tables at build time (not hardcoded).
- **Types:** table DDLs stated once in their producing task and consumed by name in T7/T9; section list (`map, label_check, overlap, fees, benchmark, habits, value, actions`) is the single source of truth, repeated verbatim in T7, T8, T9.
- **Honesty rails:** insufficient-data payloads (T7), validator fallback (T8), labelled opportunity-vs-realized components (T4), heuristic (not fitted) freak-out score documented (T5).
