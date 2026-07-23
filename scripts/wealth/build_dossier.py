"""Regenerate both wealth dashboard HTMLs from live tables + dossier JSON.

The two artifact pages (main dossier + plain-language edition) embed one data
blob in <script id="data" type="application/json">. This script:
  1. refreshes that blob from client_analytics.py output (--dossier JSON)
     extended with the transaction-engine tables (behaviour, advice, what-ifs);
  2. injects the three new sections (Behaviour / Advice ledger / What-if) and
     their render code between EXT markers — idempotent, re-runnable;
  3. re-titles the vs-Benchmark section copy from approximation to exact.

Outputs patched files in /home/ubuntu/jhaveri_data/reports/ ready for artifact
republish after headless-browse verification.

Usage:
    .venv/bin/python scripts/wealth/build_dossier.py \
        --dossier /home/ubuntu/jhaveri_data/dossier_data.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
from engine_common import connect

REPORTS = Path("/home/ubuntu/jhaveri_data/reports")
MAIN = REPORTS / "jhaveri-portfolio-intelligence.html"
SIMPLE = REPORTS / "jhaveri-simple-version.html"
BEGIN, END = "<!-- EXT:BEGIN -->", "<!-- EXT:END -->"
JS_BEGIN, JS_END = "/* EXT-JS:BEGIN */", "/* EXT-JS:END */"


def jr(v, nd=2):
    return None if v is None or pd.isna(v) else round(float(v), nd)


def assemble_ext(conn) -> dict:
    beh = pd.read_sql(
        """select b.*, c.full_name from wealth.client_behaviour b
           join wealth.clients c using (client_id)""",
        conn,
    )
    for c in beh.columns:
        if c not in ("full_name",):
            beh[c] = pd.to_numeric(beh[c], errors="coerce")
    gap = pd.read_sql(
        """select client_id, sum(gap_rs)::float gap_rs,
                  sum(invested)::float invested,
                  avg(gap_pp) filter (where invested > 100000)::float gap_pp
           from wealth.behaviour_gap group by 1""",
        conn,
    )
    beh = beh.merge(gap, on="client_id", how="left")
    adv = pd.read_sql("select * from wealth.advice_ledger", conn)
    for c in ("amount", "alpha_1y_pp", "alpha_1y_rs", "alpha_3y_pp", "alpha_3y_rs"):
        adv[c] = pd.to_numeric(adv[c], errors="coerce")
    waves = pd.read_sql("select * from wealth.advice_waves order by inflow_rs desc", conn)
    cf = pd.read_sql(
        """select f.*, c.full_name from wealth.counterfactuals f
           join wealth.clients c using (client_id)""",
        conn,
    )
    for c in cf.columns:
        if c != "full_name":
            cf[c] = pd.to_numeric(cf[c], errors="coerce")
    led = pd.read_sql(
        """select count(*) n, count(distinct client_id) nc, min(txn_date) d0, max(txn_date) d1,
                  count(*) filter (where approx) n_approx
           from wealth.transactions""",
        conn,
    ).iloc[0]

    s1 = adv.dropna(subset=["alpha_1y_pp"])
    s3 = adv.dropna(subset=["alpha_3y_pp"])
    beh_rows = [
        dict(
            id=int(r.client_id), name=r.full_name,
            de=jr(r.disposition, 3), chase=jr(r.chase_avg_3m_pct),
            hot=jr(r.chase_hot_share, 3), panic=jr(r.panic_share, 3),
            panic_rs=jr(r.panic_out_rs, 0), leak=jr(r.div_leak_rs, 0),
            sips=int(r.sip_streams or 0), sipstop=int(r.sip_stopped or 0),
            sipdd=int(r.sip_stops_in_drawdown or 0),
            gap=jr(r.gap_pp), gaprs=jr(r.gap_rs, 0),
        )
        for r in beh.itertuples()
    ]
    cf_rows = [
        dict(
            id=int(r.client_id), name=r.full_name,
            index_=jr(r.cf_index_rs, 0), panic=jr(r.cf_no_panic_rs, 0),
            sip=jr(r.cf_sip_alive_rs, 0), switch=jr(r.cf_no_switch_rs, 0),
            nswitch=int(r.switches or 0), npanic=int(r.panic_sells or 0),
        )
        for r in cf.itertuples()
    ]
    worst = adv.dropna(subset=["alpha_3y_rs"]).nsmallest(10, "alpha_3y_rs")
    best = adv.dropna(subset=["alpha_3y_rs"]).nlargest(5, "alpha_3y_rs")
    sw_rows = [
        dict(
            d=str(r.switch_date), amt=jr(r.amount, 0), frm=(r.from_name or "?")[:42],
            to=(r.to_name or "?")[:42], a1=jr(r.alpha_1y_pp), a3=jr(r.alpha_3y_pp),
            rs3=jr(r.alpha_3y_rs, 0), adv=r.advisor_name,
        )
        for r in pd.concat([worst, best]).itertuples()
    ]
    return dict(
        behaviour=dict(
            rows=beh_rows,
            cohort=dict(
                de_med=jr(beh.disposition.median(), 3),
                de_strong=int((beh.disposition > 0.1).sum()),
                chase_med=jr(beh.chase_avg_3m_pct.median()),
                panic_cr=jr(beh.panic_out_rs.sum() / 1e7),
                panic_loss_cr=jr(beh.panic_loss_out_rs.sum() / 1e7),
                panic_clients=int((beh.panic_share > 0.25).sum()),
                leak_cr=jr(beh.div_leak_rs.sum() / 1e7),
                sip_stopped=int(beh.sip_stopped.sum()),
                sip_dd=int(beh.sip_stops_in_drawdown.sum()),
                gap_med=jr(beh.gap_pp.median()),
            ),
        ),
        advice=dict(
            n=len(adv), moved_cr=jr(adv.amount.sum() / 1e7),
            s1=dict(n=len(s1), good=jr((s1.alpha_1y_pp > 0).mean(), 3),
                    med=jr(s1.alpha_1y_pp.median()), net_l=jr(s1.alpha_1y_rs.sum() / 1e5, 1)),
            s3=dict(n=len(s3), good=jr((s3.alpha_3y_pp > 0).mean(), 3),
                    med=jr(s3.alpha_3y_pp.median()), net_l=jr(s3.alpha_3y_rs.sum() / 1e5, 1)),
            switches=sw_rows,
            waves=[
                dict(
                    fund=(r.scheme_name or "?")[:46], start=str(r.window_start),
                    n=int(r.n_clients), cr=jr(pd.to_numeric(r.inflow_rs) / 1e7),
                    f1=jr(pd.to_numeric(r.fwd1y_scheme)), b1=jr(pd.to_numeric(r.fwd1y_bench)),
                    f3=jr(pd.to_numeric(r.fwd3y_scheme)), b3=jr(pd.to_numeric(r.fwd3y_bench)),
                )
                for r in waves.head(12).itertuples()
            ],
        ),
        cf=dict(
            rows=cf_rows,
            cohort={
                k: jr(pd.to_numeric(cf[c]).sum() / 1e7)
                for k, c in [("index", "cf_index_rs"), ("panic", "cf_no_panic_rs"),
                             ("sip", "cf_sip_alive_rs"), ("switch", "cf_no_switch_rs")]
            },
        ),
        ledger=dict(
            n=int(led.n), clients=int(led.nc), d0=str(led.d0), d1=str(led.d1),
            approx=int(led.n_approx),
        ),
    )


def strip_ext(html: str) -> str:
    html = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END), "", html, flags=re.S)
    html = re.sub(re.escape(JS_BEGIN) + ".*?" + re.escape(JS_END), "", html, flags=re.S)
    return html


def swap_data(html: str, data: dict) -> str:
    blob = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return re.sub(
        r'(<script id="data" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + blob + m.group(2),
        html,
        flags=re.S,
    )


MAIN_SECTIONS = f"""{BEGIN}
<style>.tile .s{{font-size:.72rem;color:var(--muted);margin-top:2px;line-height:1.35}}</style>
<section class="page" id="pg-behaviour" data-title="Behaviour">
  <h2>How clients actually behave — from every transaction since 2000</h2>
  <p class="lead">Money-weighted vs fund returns, winner-selling, momentum-chasing, drawdown
  selling and dividend leakage, measured from the full Folio Ledger history
  (<span id="bh-n"></span> transactions). Positive disposition = sells winners, rides losers
  (Odean PGR−PLR). Behaviour gap follows Morningstar's Mind-the-Gap method — part of any gap
  is mechanical (Hayley 2014), so read it as a flag, not a verdict.</p>
  <div class="tiles" id="bh-tiles"></div>
  <div class="tablewrap"><table id="bh-table"></table></div>
</section>
<section class="page" id="pg-advice" data-title="Advice ledger">
  <h2>The advice ledger — every switch we recommended, scored later <span class="tag">internal</span></h2>
  <p class="lead">Paired switch-out→switch-in events from the ledgers, scored by what the two
  funds actually did over the following 1 and 3 years. Also: push waves — five or more clients
  entering the same fund inside 30 days — and how those entries aged vs the index fund.</p>
  <div class="tiles" id="ad-tiles"></div>
  <h3>Best and worst aged switches (3y ₹ impact)</h3>
  <div class="tablewrap"><table id="ad-table"></table></div>
  <h3>Push waves</h3>
  <div class="tablewrap"><table id="ad-waves"></table></div>
</section>
<section class="page" id="pg-whatif" data-title="What-if">
  <h2>Counterfactuals — the ₹ cost of each behaviour, per client</h2>
  <p class="lead">Historical replays of NAV series that actually happened — no forward
  projections. Panic and stopped-SIP scenarios assume the cash earned nothing meanwhile, so
  they are upper bounds. "Index everything" replays every external rupee into the Nifty-50
  index fund on its true date.</p>
  <div class="tiles" id="cf-tiles"></div>
  <div class="tablewrap"><table id="cf-table"></table></div>
</section>
{END}"""


MAIN_JS = f"""{JS_BEGIN}
(function() {{
  const E = D.behaviour, A = D.advice, F = D.cf;
  if (!E) return;
  const fmtL = v => v == null ? '—' : (v >= 1e7 || v <= -1e7 ? (v / 1e7).toFixed(2) + ' cr' : (v / 1e5).toFixed(1) + ' L');
  const pct = v => v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(2);
  document.getElementById('bh-n').textContent = D.ledger.n.toLocaleString('en-IN');
  const tile = (k, v, s) => `<div class="tile"><div class="l">${{k}}</div><div class="v">${{v}}</div><div class="s">${{s || ''}}</div></div>`;
  const bc = E.cohort;
  document.getElementById('bh-tiles').innerHTML =
    tile('Median disposition', bc.de_med == null ? '—' : bc.de_med.toFixed(2), bc.de_strong + ' strong winner-sellers') +
    tile('Buys after rallies', pct(bc.chase_med) + '%', 'median trailing-3m at equity buys') +
    tile('Sold in drawdowns', '₹' + bc.panic_cr + ' cr', bc.panic_clients + ' clients >25% of exits; ₹' + bc.panic_loss_cr + ' cr below cost') +
    tile('Dividends taken as cash', '₹' + bc.leak_cr + ' cr', 'never compounded') +
    tile('SIPs stopped', bc.sip_stopped, bc.sip_dd + ' stopped inside a crash') +
    tile('Median behaviour gap', pct(bc.gap_med) + ' pp/yr', 'money-weighted vs fund return');
  const rows = E.rows.slice().sort((a, b) => (b.panic_rs || 0) - (a.panic_rs || 0));
  document.getElementById('bh-table').innerHTML =
    '<tr><th>Client</th><th>Disposition</th><th>Chase 3m%</th><th>Panic share</th><th>Panic ₹</th><th>Div leak ₹</th><th>SIPs stopped</th><th>Gap pp/yr</th></tr>' +
    rows.map(r => `<tr><td>${{r.name}}</td><td>${{r.de == null ? '—' : r.de.toFixed(2)}}</td><td>${{pct(r.chase)}}</td><td>${{r.panic == null ? '—' : (r.panic * 100).toFixed(0) + '%'}}</td><td>${{fmtL(r.panic_rs)}}</td><td>${{fmtL(r.leak)}}</td><td>${{r.sipstop}}${{r.sipdd ? ' (' + r.sipdd + ' in crash)' : ''}}</td><td>${{pct(r.gap)}}</td></tr>`).join('');
  document.getElementById('ad-tiles').innerHTML =
    tile('Switches paired', A.n, '₹' + A.moved_cr + ' cr moved') +
    tile('Aged 1 year', A.s1.n + ' scored', (A.s1.good * 100).toFixed(0) + '% added value · median ' + pct(A.s1.med) + 'pp · net ₹' + A.s1.net_l + 'L') +
    tile('Aged 3 years', A.s3.n + ' scored', (A.s3.good * 100).toFixed(0) + '% added value · median ' + pct(A.s3.med) + 'pp · net ₹' + A.s3.net_l + 'L') +
    tile('Push waves', A.waves.length, '≥5 clients into one fund in 30 days');
  document.getElementById('ad-table').innerHTML =
    '<tr><th>Date</th><th>₹</th><th>Out of</th><th>Into</th><th>1y Δpp</th><th>3y Δpp</th><th>3y ₹</th></tr>' +
    A.switches.map(r => `<tr><td>${{r.d}}</td><td>${{fmtL(r.amt)}}</td><td>${{r.frm}}</td><td>${{r.to}}</td><td>${{pct(r.a1)}}</td><td>${{pct(r.a3)}}</td><td>${{fmtL(r.rs3)}}</td></tr>`).join('');
  document.getElementById('ad-waves').innerHTML =
    '<tr><th>Fund</th><th>Window</th><th>Clients</th><th>₹ cr</th><th>Fund 1y%</th><th>Index 1y%</th><th>Fund 3y%</th><th>Index 3y%</th></tr>' +
    A.waves.map(r => `<tr><td>${{r.fund}}</td><td>${{r.start}}</td><td>${{r.n}}</td><td>${{r.cr}}</td><td>${{pct(r.f1)}}</td><td>${{pct(r.b1)}}</td><td>${{pct(r.f3)}}</td><td>${{pct(r.b3)}}</td></tr>`).join('');
  const cc = F.cohort;
  document.getElementById('cf-tiles').innerHTML =
    tile('Index everything', '₹' + cc.index + ' cr', 'every rupee into Nifty-50 fund instead') +
    tile('No drawdown selling', '₹' + cc.panic + ' cr', 'upper bound — cash assumed idle') +
    tile('SIPs never stopped', '₹' + cc.sip + ' cr', 'foregone gain on missed instalments') +
    tile('No switches', '₹' + cc.switch + ' cr', 'stayed in the source fund');
  const cfr = F.rows.slice().sort((a, b) => (b.panic || 0) + (b.sip || 0) - (a.panic || 0) - (a.sip || 0));
  document.getElementById('cf-table').innerHTML =
    '<tr><th>Client</th><th>Index-everything Δ</th><th>No-panic Δ</th><th>SIP-alive Δ</th><th>No-switch Δ</th></tr>' +
    cfr.map(r => `<tr><td>${{r.name}}</td><td>${{fmtL(r.index_)}}</td><td>${{fmtL(r.panic)}}${{r.npanic ? ' (' + r.npanic + ')' : ''}}</td><td>${{fmtL(r.sip)}}</td><td>${{fmtL(r.switch)}}${{r.nswitch ? ' (' + r.nswitch + ')' : ''}}</td></tr>`).join('');
}})();
{JS_END}"""


def patch_main(data: dict) -> None:
    html = strip_ext(MAIN.read_text())
    html = swap_data(html, data)
    # tab keys: insert before 'method'
    html = html.replace(
        "const P = ['overview','bench','risk','alloc','fees','rules','method']",
        "const P = ['overview','bench','risk','alloc','fees','rules','behaviour','advice','whatif','method']",
    )
    # sections before the Method page
    html = html.replace('<section class="page" id="pg-method"', MAIN_SECTIONS + '\n<section class="page" id="pg-method"')
    # exactness copy on the bench page
    html = html.replace(
        "same dated rupees into the index fund",
        "same dated rupees — every ledger cash flow, exact — into the index fund",
    )
    # render JS as its own script before </body> (or at end)
    js = f'<script>{MAIN_JS}</script>'
    html = html.rstrip() + "\n" + BEGIN + js + END + "\n" if "</body>" not in html else html.replace("</body>", BEGIN + js + END + "</body>")
    MAIN.write_text(html)
    print(f"patched {MAIN.name}: {len(html)} bytes")


SIMPLE_BLOCK = f"""{BEGIN}
<style>.tile .s{{font-size:.72rem;color:var(--muted);margin-top:2px;line-height:1.35}}</style>
<div class="body">
  <h1 style="font-size:1.35rem;margin-top:2.2rem">What the full transaction history adds</h1>
  <p class="note">We now hold every transaction back to 2000 — <span id="sx-n"></span> of them.
  These numbers are replays of what actually happened, not projections.</p>
  <div class="grid" id="sx-tiles"></div>
  <p class="note" id="sx-note"></p>
</div>
{END}"""

SIMPLE_JS = f"""{JS_BEGIN}
(function() {{
  const E = D.behaviour, F = D.cf, A = D.advice;
  if (!E) return;
  document.getElementById('sx-n').textContent = D.ledger.n.toLocaleString('en-IN');
  const t = (k, v, s) => `<div class="tile"><div class="l">${{k}}</div><div class="v">${{v}}</div><div class="s">${{s || ''}}</div></div>`;
  const bc = E.cohort, cc = F.cohort;
  document.getElementById('sx-tiles').innerHTML =
    t('Sold during crashes', '₹' + bc.panic_cr + ' cr', bc.panic_clients + ' clients did most of their selling in falling markets') +
    t('Sold below what they paid', '₹' + bc.panic_loss_cr + ' cr', 'crash-selling locked in these losses') +
    t('Dividends taken as cash', '₹' + bc.leak_cr + ' cr', 'money that never got a chance to grow') +
    t('SIPs stopped', bc.sip_stopped, bc.sip_dd + ' were stopped right inside a crash — the worst moment') +
    t('If SIPs had continued', '₹' + cc.sip + ' cr', 'growth missed by stopping — an upper-bound estimate') +
    t('If nobody sold in crashes', '₹' + cc.panic + ' cr', 'what those units would be worth today — upper bound') +
    t('Switch advice, aged 3 years', (A.s3.good * 100).toFixed(0) + '% helped', 'of ' + A.s3.n + ' switches we could score against what both funds then did') +
    t('Every rupee in the index instead', '₹' + cc.index + ' cr', 'the whole book, replayed into the Nifty-50 fund');
  document.getElementById('sx-note').textContent =
    'Method notes: crash windows are computed from the index fund\\'s own history (falls of 10% or more), not picked by hand. ' +
    'Behaviour-gap figures follow Morningstar\\'s Mind-the-Gap approach; part of any gap is mechanical, so we use it as a conversation starter, never an accusation.';
}})();
{JS_END}"""


def patch_simple(data: dict) -> None:
    html = strip_ext(SIMPLE.read_text())
    html = swap_data(html, data)
    anchor = "</body>" if "</body>" in html else None
    block = SIMPLE_BLOCK + f"<script>{SIMPLE_JS}</script>"
    if anchor:
        html = html.replace(anchor, block + anchor)
    else:
        html = html.rstrip() + "\n" + block + "\n"
    SIMPLE.write_text(html)
    print(f"patched {SIMPLE.name}: {len(html)} bytes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dossier", required=True)
    args = ap.parse_args()
    data = json.load(open(args.dossier))
    conn = connect()
    data.update(assemble_ext(conn))
    conn.close()
    patch_main(data)
    patch_simple(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
