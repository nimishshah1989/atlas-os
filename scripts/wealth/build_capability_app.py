# allow-large: plan-mandated single-file app template (HTML/CSS/JS inline string)
"""Build the Jhaveri capability app — ONE self-contained, CSP-safe HTML file.

Reads the live wealth.* tables at build time and embeds EVERYTHING as a single
<script id="data" type="application/json"> block. The app is hash-routed vanilla
JS with inline CSS; zero external requests (no CDN, no fonts fetch, no images —
inline SVG only). Rule #0: every number on screen is computed here from the DB,
nothing invented.

Routes: #book (6 scroll-snap chapters) · #calls (three PREDICT lists) ·
#client/<id> (the 8-section Audit Pack).

Output: /home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html (~2-4 MB).
Not committed — lives outside the repo. Gate it with validate_wealth_app.py.

Usage: set -a; source .env; set +a; .venv/bin/python scripts/wealth/build_capability_app.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

from build_audit_packs import SECTION_NAMES
from engine_common import connect

OUT = Path("/home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html")


def _f(x):
    """-> float rounded, or None (never NaN/Inf — strict-JSON safe)."""
    if x is None:
        return None
    v = float(x)
    if not math.isfinite(v):
        return None
    return round(v, 4)


def lcr_py(n: float) -> str:
    """₹ in L/cr, en-IN style (mirror of the JS lcr for build-time story text)."""
    a = abs(n)
    if a >= 1e7:
        return f"₹{n/1e7:.2f} cr"
    if a >= 1e5:
        return f"₹{n/1e5:.2f} L"
    return f"₹{round(n):,}"


# ----------------------------------------------------------------- fetch --

def fetch(conn) -> dict:
    def q(sql):
        return pd.read_sql(sql, conn)

    asof = q("select max(as_on_date) d from wealth.client_reports").d.iloc[0]
    asof = asof.isoformat()

    book_row = q("""
        select (select count(distinct household_name) from wealth.households) families,
               (select count(*) from wealth.clients) clients,
               (select extract(year from min(txn_date))::int from wealth.transactions) since
    """).iloc[0]
    mv_cr = _f(q("""select round(sum(mv_total)/1e7,1) v from (
        select distinct on (client_id) mv_total from wealth.client_reports
        order by client_id, as_on_date desc) t""").v.iloc[0])
    book = {"families": int(book_row.families), "clients": int(book_row.clients),
            "mv_cr": mv_cr, "since": int(book_row.since)}

    # ch2 — typical yearly growth + a ₹10L growth strip
    growth = _f(q("""select percentile_cont(0.5) within group (order by xirr_client) m
                     from wealth.client_benchmark where xirr_client is not null""").m.iloc[0])
    r = (growth or 0) / 100.0
    strip = [{"year": y, "value": round(1_000_000 * (1 + r) ** y)} for y in range(0, 11)]

    # ch3 — share of clients ahead of the index fund (never say "alpha")
    pct_ahead = int(round(_f(q("""select 100.0*sum(case when alpha>0 then 1 else 0 end)/count(*) p
        from wealth.client_benchmark where alpha is not null""").p.iloc[0])))

    # ch4 — what habits cost / protected, each card opens a real call list
    stay = _f(q("select round(sum(staying_power_rs)/1e7,1) v from wealth.value_statements").v.iloc[0])
    sip_cost = _f(q("select round(sum(cf_sip_alive_rs)/1e7,1) v from wealth.counterfactuals").v.iloc[0])
    div_cost = _f(q("select round(sum(div_leak_rs)/1e7,1) v from wealth.client_behaviour").v.iloc[0])

    def top_call(list_type):
        rows = q(f"""select client_id, reason from wealth.call_lists
                     where list_type='{list_type}' order by rank limit 1""")
        if rows.empty:
            return None, None
        return int(rows.client_id.iloc[0]), rows.reason.iloc[0]

    # cards 1 & 2 open their matching call list; card 3 (dividends) has no call
    # list, so it opens a real high-dividend-leakage client's own page — headline,
    # number, story and click-through all agree.
    ch4 = []
    for key, title, amt, verb in [
        ("crash_sellers", "Held through the crashes", stay,
         "protected by clients who stayed invested through every major fall"),
        ("sip_fragile", "Stopped SIPs", sip_cost,
         "the running total left behind when steady monthly investing was switched off"),
    ]:
        cid, reason = top_call(key)
        ch4.append({"href": f"calls:{key}", "title": title, "amount_cr": amt,
                    "subtitle": verb, "story": reason, "sample_ids": [cid] if cid else []})

    dl = q("""select b.client_id, b.div_leak_rs, c.full_name
              from wealth.client_behaviour b join wealth.clients c on c.client_id = b.client_id
              where b.div_leak_rs > 0 order by b.div_leak_rs desc limit 1""")
    dl_id = int(dl.client_id.iloc[0]) if not dl.empty else None
    dl_story = (f"One client alone has taken about {lcr_py(float(dl.div_leak_rs.iloc[0]))} of "
                f"dividends as cash instead of letting it compound — open their page to see it."
                if not dl.empty else None)
    ch4.append({"href": f"client:{dl_id}" if dl_id else "calls:disengaged",
                "title": "Dividends taken as cash", "amount_cr": div_cost,
                "subtitle": "paid out and spent instead of being reinvested to compound",
                "story": dl_story, "sample_ids": [dl_id] if dl_id else []})

    # ch5 — our advice, marked honestly
    ledg = q("""select count(*) n, sum(case when alpha_1y_pp>0 then 1 else 0 end) ahead
                from wealth.advice_ledger where alpha_1y_pp is not null""").iloc[0]
    waves = q("select count(*) n, sum(n_clients) fam, round(sum(inflow_rs)/1e7,1) cr from wealth.advice_waves").iloc[0]
    wave_list = q("""select scheme_name, window_start, window_end, n_clients,
                            fwd1y_scheme, fwd1y_bench from wealth.advice_waves
                     where fwd1y_scheme is not null order by inflow_rs desc limit 12""")
    ch5 = {
        "switch_ahead": int(ledg.ahead), "switch_total": int(ledg.n),
        "waves": int(waves.n), "families_nudged": int(waves.fam),
        "wave_rows": [
            {"fund": w.scheme_name, "from": str(w.window_start), "to": str(w.window_end),
             "n": int(w.n_clients), "scheme": _f(w.fwd1y_scheme), "bench": _f(w.fwd1y_bench)}
            for w in wave_list.itertuples()],
    }

    chapters = {
        "ch2": {"growth_pct": growth, "strip": strip},
        "ch3": {"pct_ahead": pct_ahead, "dots_filled": max(0, min(10, round(pct_ahead / 10)))},
        "ch4": ch4,
        "ch5": ch5,
    }

    # ---- call lists (name + book MV per row) ----
    calls_df = q("""
        select cl.client_id, cl.list_type, cl.rank, cl.reason, cl.script,
               c.full_name, r.mv_total
        from wealth.call_lists cl
        join wealth.clients c on c.client_id = cl.client_id
        left join lateral (select mv_total from wealth.client_reports cr
                           where cr.client_id = cl.client_id
                           order by as_on_date desc limit 1) r on true
        order by cl.list_type, cl.rank""")
    call_lists = {}
    for lt, g in calls_df.groupby("list_type"):
        call_lists[lt] = [
            {"id": str(row.client_id), "name": row.full_name, "book_rs": _f(row.mv_total),
             "reason": row.reason, "script": row.script}
            for row in g.itertuples()]

    # ---- per-client packs + prose + chips ----
    names = q("select client_id, full_name from wealth.clients")
    name_by = dict(zip(names.client_id, names.full_name))
    hh = q("select client_id, household_name, members, household_mv, succession_flag from wealth.households")
    hh_by = {r.client_id: {"name": r.household_name, "members": int(r.members),
                            "mv": _f(r.household_mv), "succession": r.succession_flag}
             for r in hh.itertuples()}
    beh = q("""select client_id, panic_share, sip_streams, sip_active, div_leak_rs,
                      chase_hot_share from wealth.client_behaviour""")
    beh_by = {r.client_id: r for r in beh.itertuples()}
    packs = q("select client_id, payload, prose from wealth.audit_packs")

    def chips(cid):
        b = beh_by.get(cid)
        if b is None:
            return ["Not enough history yet"]
        out = []
        ps = float(b.panic_share or 0)
        out.append("Sells in market falls" if ps >= 0.25
                   else "Sometimes sells in falls" if ps > 0 else "Holds through falls")
        streams, active = int(b.sip_streams or 0), int(b.sip_active or 0)
        out.append("No active SIPs" if streams == 0
                   else "Keeps every SIP running" if active >= streams
                   else "Some SIPs stopped" if active > 0 else "All SIPs stopped")
        out.append("Takes dividends as cash" if float(b.div_leak_rs or 0) > 0
                   else "Reinvests dividends")
        return out

    clients = {}
    for row in packs.itertuples():
        cid = row.client_id
        pack = row.payload
        # value.summary is engine-provenance text (never rendered) — don't embed it
        if isinstance(pack.get("value"), dict):
            pack["value"].pop("summary", None)
        clients[str(cid)] = {
            "name": name_by.get(cid),
            "household": hh_by.get(cid),
            "chips": chips(cid),
            "pack": pack,             # already strict-JSON clean (build_audit_packs)
            "prose": row.prose or {},  # NULL for most; JS falls back to a template line
        }

    return {"asof": asof, "book": book, "chapters": chapters,
            "sections": SECTION_NAMES, "call_lists": call_lists, "clients": clients}


# --------------------------------------------------------------- render --

def render(data: dict) -> str:
    blob = json.dumps(data, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")  # never break out of the <script> block
    return HTML.replace("__DATA__", blob)


def main() -> int:
    conn = connect()
    data = fetch(conn)
    conn.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = render(data)
    OUT.write_text(html, encoding="utf-8")
    size = len(html.encode("utf-8"))
    print(f"wrote {OUT} ({size/1e6:.2f} MB, {len(data['clients'])} clients, "
          f"{sum(len(v) for v in data['call_lists'].values())} call rows)")
    return 0


# ------------------------------------------------------------- template --
# One string: inline CSS (design tokens verbatim from the locked plan) + the
# JSON data block + vanilla-JS hash router. No external requests anywhere.
HTML = r"""<style>
:root{
  --paper:#FAF7F1; --card:#FFFFFF; --ink:#232019; --muted:#6B6357; --line:#E7E0D4;
  --accent:#0E5A6D; --good:#256C3C; --warn:#9A6A0A; --crit:#A63A32; --soft:#0E5A6D12;
  --serif:Georgia,'Times New Roman',serif;
  --sans:-apple-system,'Segoe UI',Roboto,sans-serif;
}
:root[data-theme=dark]{
  --paper:#14120E; --card:#1C1915; --ink:#EDE7DC; --muted:#9A917F; --line:#2E2A22;
  --accent:#4FB3C9; --good:#57BE7C; --warn:#DFA83D; --crit:#E06B5F; --soft:#4FB3C91F;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
.num,.big{font-variant-numeric:tabular-nums}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.eyebrow{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);font-weight:600}
.big{font-family:var(--serif);font-size:clamp(40px,7vw,72px);line-height:1.02;
  letter-spacing:-.02em;font-weight:600}
h1,h2,h3{font-family:var(--serif);font-weight:600;letter-spacing:-.01em;margin:0}
.wrap{max-width:920px;margin:0 auto;padding:0 20px}
details{margin-top:18px;border-top:1px solid var(--line);padding-top:12px}
details summary{cursor:pointer;color:var(--accent);font-size:.9rem;font-weight:600;
  list-style:none}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"▸ ";}
details[open] summary::before{content:"▾ ";}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:.9rem}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.method{color:var(--muted);font-size:.85rem;margin-top:8px}

/* top bar */
.bar{position:sticky;top:0;z-index:20;display:flex;gap:6px;align-items:center;
  background:var(--paper);border-bottom:1px solid var(--line);padding:10px 18px}
.bar .brand{font-family:var(--serif);font-weight:600;font-size:1.05rem;margin-right:auto}
.bar a,.bar button{font-family:var(--sans);font-size:.85rem;font-weight:600;
  padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);
  color:var(--ink);cursor:pointer}
.bar a.on{background:var(--accent);color:#fff;border-color:var(--accent)}

/* book */
.book{scroll-snap-type:y mandatory;height:calc(100vh - 45px);overflow-y:scroll}
.chapter{scroll-snap-align:start;min-height:calc(100vh - 45px);display:flex;
  align-items:center;padding:40px 20px}
.chapter .inner{max-width:820px;margin:0 auto;width:100%}
.chapter h2{font-size:clamp(24px,3.4vw,34px);margin:14px 0 22px;max-width:20ch}
.visual{margin:8px 0 4px}
.cards{display:flex;flex-wrap:wrap;gap:16px;margin-top:8px}
.card{flex:1 1 240px;background:var(--card);border:1px solid var(--line);
  border-radius:14px;padding:18px}
.card .big{font-size:clamp(30px,4.4vw,44px)}
.card h3{font-size:1.05rem;margin-bottom:6px}
.card p{color:var(--muted);font-size:.9rem;margin:6px 0 0}
.dots{display:flex;gap:10px;flex-wrap:wrap;max-width:420px}

/* calls */
.chips{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0 22px}
.chip{font-size:.85rem;font-weight:600;padding:8px 14px;border-radius:999px;
  border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.row{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px;margin-bottom:10px;color:var(--ink)}
.row:hover{border-color:var(--accent);text-decoration:none}
.row .rline{display:flex;justify-content:space-between;gap:14px;align-items:baseline}
.row .rname{font-weight:700}
.row .rbook{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.row .reason{color:var(--ink);font-size:.92rem;margin-top:4px}
.row .script{color:var(--muted);font-size:.88rem;margin-top:4px;font-style:italic}

/* client */
.searchbox{margin:16px 0}
.searchbox input{width:100%;max-width:420px;padding:10px 14px;border-radius:10px;
  border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:1rem}
.profile{background:var(--soft);border:1px solid var(--line);border-radius:14px;
  padding:18px 20px;margin-bottom:8px}
.profile h1{font-size:clamp(22px,3vw,30px)}
.hchip{display:inline-block;font-size:.8rem;font-weight:600;padding:4px 10px;border-radius:999px;
  background:var(--card);border:1px solid var(--line);margin:8px 8px 0 0;color:var(--muted)}
.section{padding:26px 0;border-top:1px solid var(--line)}
.section h3{font-size:1.15rem;margin:6px 0 10px}
.section .prose{max-width:60ch}
.section .big{margin:14px 0 4px}
.insuf{color:var(--muted);font-style:italic;max-width:60ch}
.act{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:10px;padding:14px 16px;margin-bottom:10px}
.act .verb{font-weight:700}
.act .tax{color:var(--muted);font-size:.88rem;margin-top:4px}
.foot{color:var(--muted);font-size:.8rem;padding:30px 20px;text-align:center}
</style>

<script id="data" type="application/json">__DATA__</script>

<div class="bar" role="navigation" aria-label="Primary">
  <span class="brand">The Book</span>
  <a href="#book" data-nav>Book</a>
  <a href="#calls" data-nav>Who to call</a>
  <a href="#client/" data-nav>A client</a>
  <button id="theme" aria-label="Toggle light or dark theme">◑ Theme</button>
</div>
<main id="app" role="main"></main>

<script>
"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
const app = document.getElementById("app");
const esc = s => String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const enIN = n => Math.round(n).toLocaleString("en-IN");
function lcr(n){ if(n==null) return "—"; const a=Math.abs(n);
  if(a>=1e7) return "₹"+(n/1e7).toFixed(2)+" cr";
  if(a>=1e5) return "₹"+(n/1e5).toFixed(2)+" L";
  return "₹"+enIN(n); }
function pct(n){ return n==null?"—":(n>=0?"":"")+n.toFixed(1)+"%"; }

/* ---- theme ---- */
document.getElementById("theme").onclick = () => {
  const r=document.documentElement;
  r.setAttribute("data-theme", r.getAttribute("data-theme")==="dark"?"light":"dark");
};

/* ---- inline SVG helpers ---- */
function svgBars(strip){
  const W=560,H=150,pad=24, max=Math.max(...strip.map(d=>d.value));
  const bw=(W-pad)/strip.length;
  const bars=strip.map((d,i)=>{
    const h=(d.value/max)*(H-30), x=pad+i*bw, y=H-h-16;
    return `<rect x="${x+3}" y="${y}" width="${bw-6}" height="${h}" rx="2" fill="var(--accent)"></rect>`+
           (i===0||i===strip.length-1?`<text x="${x+bw/2}" y="${H-3}" font-size="10" fill="var(--muted)" text-anchor="middle">Yr ${d.year}</text>`:"");
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Ten lakh rupees growing year by year">${bars}</svg>`;
}
function svgDots(filled){
  let out="";
  for(let i=0;i<10;i++){ const on=i<filled;
    out+=`<circle cx="${20+i*38}" cy="24" r="13" fill="${on?"var(--accent)":"none"}" stroke="var(--accent)" stroke-width="2"></circle>`;
  }
  return `<svg viewBox="0 0 400 48" width="100%" style="max-width:420px" role="img" aria-label="${filled} of 10 ahead of the index fund">${out}</svg>`;
}
function svgDial(eff, stocks){
  // arc: eff genuinely-different bets out of the underlying stocks actually held
  const frac=(stocks&&eff!=null)?Math.max(0.02,Math.min(1,eff/stocks)):0.02, R=54, C=Math.PI*R;
  const off=C*(1-frac);
  const lab=eff==null?"unknown":eff.toFixed(1);
  return `<svg viewBox="0 0 140 90" width="160" role="img" aria-label="About ${lab} genuinely different bets out of ${stocks==null?"the":stocks} underlying stocks held">
    <path d="M16 78 A62 62 0 0 1 124 78" fill="none" stroke="var(--line)" stroke-width="12" stroke-linecap="round"/>
    <path d="M16 78 A62 62 0 0 1 124 78" fill="none" stroke="var(--accent)" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${C}" stroke-dashoffset="${off}"/>
    <text x="70" y="72" text-anchor="middle" font-family="var(--serif)" font-size="26" fill="var(--ink)">${lab}</text>
  </svg>`;
}
function svgTwoLine(rClient, rBench){
  // two growth curves from yearly-growth rates over 8 years
  const yrs=8,W=340,H=120;
  const pts=r=>{let s="";for(let y=0;y<=yrs;y++){const v=Math.pow(1+(r||0)/100,y);
    const x=20+(y/yrs)*(W-30), max=Math.pow(1+Math.max(rClient,rBench,1)/100,yrs);
    const yy=H-14-(v/max)*(H-30); s+=(y?"L":"M")+x.toFixed(0)+" "+yy.toFixed(0)+" ";}return s;};
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:360px" role="img" aria-label="Your growth versus the index fund">
    <path d="${pts(rBench)}" fill="none" stroke="var(--muted)" stroke-width="2" stroke-dasharray="4 3"/>
    <path d="${pts(rClient)}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>
    <text x="${W-4}" y="14" text-anchor="end" font-size="10" fill="var(--accent)">you</text>
    <text x="${W-4}" y="28" text-anchor="end" font-size="10" fill="var(--muted)">index fund</text>
  </svg>`;
}

/* ---- routing ---- */
function nav(){
  const h=location.hash.replace(/^#/,"")||"book";
  document.querySelectorAll(".bar a[data-nav]").forEach(a=>{
    const t=a.getAttribute("href").replace(/^#/,"");
    a.classList.toggle("on", h===t || (t==="book"&&h==="book") ||
      (t==="calls"&&h==="calls") || (t==="client/"&&h.startsWith("client/")));
  });
  if(h==="book") return renderBook();
  if(h==="calls") return renderCalls();
  if(h.startsWith("client/")) return renderClient(h.slice(7));
  renderBook();
}
window.addEventListener("hashchange", ()=>{app.scrollTop=0;nav();});

/* ---- screen 1: the book ---- */
function chapter(n, eyebrow, headline, big, visualHTML, howHTML){
  return `<section class="chapter"><div class="inner">
    <div class="eyebrow">Chapter ${n} · ${esc(eyebrow)}</div>
    <h2>${headline}</h2>
    <div class="big">${big}</div>
    <div class="visual">${visualHTML||""}</div>
    <details><summary>How we know this</summary>${howHTML}</details>
  </div></section>`;
}
function renderBook(){
  const b=DATA.book, c=DATA.chapters;
  const chaps=[];
  chaps.push(chapter(1,"The book",
    `${b.families} families and ${b.clients} accounts, with records going back to ${b.since}.`,
    "₹"+b.mv_cr+" cr",
    "",
    `<div class="method">Family count = distinct households (surname + joint-holder roll-up). Book value = the header total on each client's latest valuation report, added up. Oldest transaction on file is dated ${b.since}.</div>`));

  chaps.push(chapter(2,"Did clients make money?",
    `A typical client's money has grown about ${c.ch2.growth_pct}% every year.`,
    c.ch2.growth_pct+"%/yr",
    svgBars(c.ch2.strip),
    `<div class="method">Growth here is the median yearly growth across all clients, measured on their real money-in and money-out dates. The bars show ₹10 lakh growing at that rate — ₹10 L becomes about ${lcr(c.ch2.strip[10].value)} over ten years.</div>`));

  chaps.push(chapter(3,"An honest comparison",
    `We replayed every client's exact investments into a plain Nifty-50 index fund. ${c.ch3.dots_filled} in 10 came out ahead.`,
    c.ch3.pct_ahead+"%",
    svgDots(c.ch3.dots_filled),
    `<div class="method">For each client we took their real money-in and money-out dates and put the same amounts into an ICICI Pru Nifty-50 index fund on the same days, then compared. ${c.ch3.pct_ahead}% of clients ended ahead of the index. Note: this is our current book — clients who left over the years are not in it.</div>`));

  const cardHref=card=>{
    const [kind,arg]=card.href.split(":");
    if(kind==="client") return {href:`#client/${arg}`,click:""};
    return {href:"#calls",click:`sessionStorage.setItem('callfilter','${arg}')`};
  };
  const cards=c.ch4.map(card=>{const h=cardHref(card);return `
    <a class="card" href="${h.href}" onclick="${h.click}">
      <h3>${esc(card.title)}</h3>
      <div class="big">₹${card.amount_cr==null?"—":card.amount_cr} cr</div>
      <p>${esc(card.subtitle)}.</p>
      <p style="margin-top:8px;color:var(--ink)">${esc(card.story||"")}</p>
    </a>`;}).join("");
  chaps.push(chapter(4,"What habits cost, and saved",
    "The same three habits, measured across the whole book. Each card opens the clients it affects.",
    "",
    `<div class="cards">${cards}</div>`,
    `<div class="method">"Held through the crashes" = the realised value protected for clients who stayed invested through major falls. The other two are upper-bound estimates of value left behind when SIPs were stopped or dividends taken as cash instead of reinvested — labelled as estimates, not booked losses.</div>`));

  const c5=c.ch5;
  const waveRows=c5.wave_rows.map(w=>`<tr><td>${esc(w.fund)}</td><td class="n">${w.n}</td>
    <td class="n">${pct(w.scheme)}</td><td class="n">${pct(w.bench)}</td></tr>`).join("");
  chaps.push(chapter(5,"Our advice, marked honestly",
    "We keep score of our own calls — the switches we suggested and the funds we pushed clients into.",
    c5.switch_ahead+" of "+c5.switch_total,
    `<div class="cards">
       <div class="card"><h3>Switches that worked</h3><div class="big">${c5.switch_ahead}/${c5.switch_total}</div><p>fund switches we advised were ahead of the old fund a year later.</p></div>
       <div class="card"><h3>Funds we pushed</h3><div class="big">${c5.waves}</div><p>buying waves across ${enIN(c5.families_nudged)} client positions — the year-after record is below.</p></div>
     </div>`,
    `<div class="method">Every advised switch is replayed one year forward: old fund vs new fund. Every buying wave is checked against a Nifty-50 index fund a year later. We show wins and misses both.</div>
     <details style="margin-top:14px"><summary>The push-wave scorecard</summary>
       <table><thead><tr><th>Fund</th><th class="n">Clients</th><th class="n">Fund +1yr</th><th class="n">Index +1yr</th></tr></thead><tbody>${waveRows}</tbody></table>
       <div class="method">Percent = one-year growth after the wave. Where the fund column beats the index column, the push added value.</div>
     </details>`));

  const sample=Object.keys(DATA.clients).sort((a,b)=>a-b)[0];
  chaps.push(chapter(6,"What this makes possible",
    "Three capabilities, running on our own book today — not a pitch, a demonstration.",
    "",
    `<div class="cards">
      <div class="card"><h3>Profile</h3><p style="color:var(--ink)">We can tell a client how they behave — whether they sell in every crash, keep their SIPs alive, or take dividends as cash — from what they actually did.</p></div>
      <div class="card"><h3>Predict &amp; prevent</h3><p style="color:var(--ink)">We know who to call this week and what to say, before they act. <a href="#calls">See the call lists →</a></p></div>
      <div class="card"><h3>Prescribe</h3><p style="color:var(--ink)">Every client gets a plain-language audit of what they own, what they pay, and what to do. <a href="#client/${sample}">Open a client audit →</a></p></div>
    </div>`,
    `<div class="method">Profile is computed from each client's transaction history. Predict lists are regenerated every run. Prescribe assembles seven checks per client, every number traced to a source table.</div>`));

  app.innerHTML = `<div class="book" id="book">${chaps.join("")}</div>`;
  // arrow-key chapter nav
  const bookEl=document.getElementById("book");
  bookEl.tabIndex=0;
  bookEl.onkeydown=e=>{
    const secs=[...bookEl.querySelectorAll(".chapter")];
    const cur=secs.findIndex(s=>s.getBoundingClientRect().top>=-5);
    if(e.key==="ArrowDown"&&cur<secs.length-1){e.preventDefault();secs[cur+1].scrollIntoView({behavior:"smooth"});}
    if(e.key==="ArrowUp"&&cur>0){e.preventDefault();secs[cur-1].scrollIntoView({behavior:"smooth"});}
  };
}

/* ---- screen 2: who to call ---- */
const CALL_META={crash_sellers:"Crash sellers",sip_fragile:"Fragile SIPs",disengaged:"Drifting away"};
function renderCalls(){
  const lists=DATA.call_lists;
  const keys=Object.keys(CALL_META).filter(k=>lists[k]);
  let active=sessionStorage.getItem("callfilter");
  if(!keys.includes(active)) active=keys[0];
  const chips=keys.map(k=>`<button class="chip${k===active?" on":""}" data-list="${k}">${esc(CALL_META[k])}</button>`).join("");
  app.innerHTML=`<div class="wrap" style="padding-top:26px">
    <div class="eyebrow">Predict &amp; prevent</div>
    <h1 style="font-size:clamp(24px,3.4vw,32px);margin-top:8px">Who to call this week</h1>
    <div class="chips" role="tablist">${chips}</div>
    <div id="rows"></div>
    <div class="foot">Each name is a client on our book. The line under is what to say. Click a row to open their full audit.</div>
  </div>`;
  const paint=k=>{
    document.querySelectorAll(".chip").forEach(c=>c.classList.toggle("on",c.dataset.list===k));
    document.getElementById("rows").innerHTML=(lists[k]||[]).map(r=>`
      <a class="row" href="#client/${r.id}">
        <div class="rline"><span class="rname">${esc(r.name)}</span><span class="rbook">${lcr(r.book_rs)} on our book</span></div>
        <div class="reason">${esc(r.reason)}</div>
        <div class="script">Script: ${esc(r.script)}</div>
      </a>`).join("");
  };
  document.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{sessionStorage.setItem("callfilter",c.dataset.list);paint(c.dataset.list);});
  paint(active);
}

/* ---- screen 3: client audit pack ---- */
const SEC_META={
  map:["The map","What you own, in one clean picture"],
  label_check:["The label check","Does each fund do what its name says?"],
  overlap:["The overlap trap","How many genuinely different bets you own"],
  fees:["What you actually pay","The fees, in rupees a year"],
  benchmark:["Did you beat the market?","Your money vs a plain index fund"],
  habits:["Your habits","How you behave — and what it costs"],
  value:["What our advice was worth","The value we've added, added up"],
  actions:["The action list","What to do next"],
};
function bigFor(key,p){
  if(p.insufficient) return null;
  if(key==="map") return lcr(p.headline_value);
  if(key==="label_check") return p.n_mismatch+(p.n_mismatch===1?" fund off-label":" funds off-label");
  if(key==="overlap") return (p.eff_bets==null?"—":p.eff_bets.toFixed(1))+" real bets";
  if(key==="fees") return lcr(p.fee_save_yr_rs)+"/yr";
  if(key==="benchmark"){const a=p.alpha; return a==null?"—":(a>=0?"+":"")+a.toFixed(1)+"%/yr "+(a>=0?"ahead":"behind");}
  if(key==="habits") return Math.round((p.panic_share||0)*100)+"% sold in falls";
  if(key==="value") return lcr(p.realized_total_rs);
  if(key==="actions") return p.n_actions+(p.n_actions===1?" thing to do":" things to do");
  return lcr(p.headline_value);
}
function fallbackProse(key,p,name){
  const n=esc(name||"This client");
  if(p.insufficient) return "";
  if(key==="map") return `${n}'s money with us is ${lcr(p.total_mv)}, spread across ${p.n_funds||"several"} funds holding ${p.n_stocks||"many"} different stocks underneath.`;
  if(key==="label_check") return p.n_mismatch>0?`${p.n_mismatch} of ${p.n_funds_checked} funds don't invest the way their name suggests — worth a closer look.`:`All ${p.n_funds_checked} checked funds invest broadly the way their names suggest.`;
  if(key==="overlap") return `Across all the funds, there are really about ${p.eff_bets==null?"a handful of":p.eff_bets.toFixed(1)} genuinely different bets — the rest is the same stocks showing up again and again.`;
  if(key==="fees") return p.fee_save_yr_rs>0?`We estimate about ${lcr(p.fee_save_yr_rs)} a year could be saved on fees without changing what you're really invested in.`:`No obvious fee savings flagged — the funds held aren't the closet-index kind.`;
  if(key==="benchmark"){const a=p.alpha; return a==null?"":`Put the exact same money on the exact same dates into a plain index fund, and you'd be ${a>=0?"ahead":"behind"} by about ${Math.abs(a).toFixed(1)}% a year.`;}
  if(key==="habits") return `In past market falls, ${Math.round((p.panic_share||0)*100)}% of everything ever withdrawn was pulled out during the drop.`;
  if(key==="value") return `Adding up SIP discipline, staying invested, switches, fees and tax, the value we've helped with comes to about ${lcr(p.realized_total_rs)}.`;
  if(key==="actions") return p.n_actions>0?`There ${p.n_actions===1?"is":"are"} ${p.n_actions} thing${p.n_actions===1?"":"s"} worth doing on this account.`:`Nothing pressing — a genuinely clean account right now.`;
  return "";
}
function visualFor(key,p){
  if(p.insufficient) return "";
  if(key==="overlap") return svgDial(p.eff_bets, p.n_stocks);
  if(key==="benchmark" && p.xirr_client!=null) return svgTwoLine(p.xirr_client, p.xirr_bench);
  return "";
}
function tableFor(key,p){
  const rows=[];
  const R=(k,v)=>rows.push(`<tr><td>${k}</td><td class="n">${v}</td></tr>`);
  if(key==="map"){R("Book value",lcr(p.total_mv));R("Funds",p.n_funds);R("Stocks underneath",p.n_stocks);R("Years with us",p.tenure_years);}
  else if(key==="label_check"){(p.funds||[]).slice(0,12).forEach(f=>rows.push(
    `<tr><td>${esc(f.fund)}${f.coverage_note?`<div class="method" style="margin-top:2px">${esc(f.coverage_note)}</div>`:""}</td><td class="n">${esc(f.verdict)}</td></tr>`));}
  else if(key==="overlap"){R("Genuinely different bets",p.eff_bets==null?"—":p.eff_bets.toFixed(1));R("Biggest single stock",esc(p.top_stock_name)+" · "+lcr(p.top_stock_rs));R("Top-10 stocks share",p.top10_share==null?"—":(p.top10_share*100).toFixed(0)+"%");if(p.worst_fund_pair)R("Most-overlapping pair",esc(p.worst_fund_pair.fund_a)+" / "+esc(p.worst_fund_pair.fund_b)+" ("+(p.worst_fund_pair.overlap_pct).toFixed(0)+"%)");}
  else if(key==="fees"){R("Estimated saving / year",lcr(p.fee_save_yr_rs));(p.flags||[]).forEach(f=>rows.push(`<tr><td>${esc(f.rule||f.evidence)}</td><td class="n">${lcr(f.est_value)}</td></tr>`));}
  else if(key==="benchmark"){R("Your yearly growth",pct(p.xirr_client));R("Index-fund yearly growth",pct(p.xirr_bench));R("Ahead / behind",p.alpha==null?"—":(p.alpha>=0?"+":"")+p.alpha.toFixed(1)+"%/yr");R("Money-in / money-out events",p.n_flows);}
  else if(key==="habits"){R("Withdrawn during falls",Math.round((p.panic_share||0)*100)+"%");if(p.sip_active_share!=null)R("SIPs still running",Math.round(p.sip_active_share*100)+"%");R("Dividends taken as cash",lcr(p.div_leak_rs));if(p.cf_no_panic_rs!=null)R("Est. value if never sold in falls",lcr(p.cf_no_panic_rs));}
  else if(key==="value"){const r=p.realized||{};R("SIP discipline",lcr(r.sip_discipline_rs));R("Staying invested",lcr(r.staying_power_rs));R("Switch outcomes",lcr(r.advice_outcome_rs));R("Fee savings",lcr(r.fee_save_yr_rs));R("Tax headroom",lcr(r.tax_headroom_rs));R("Total realised",lcr(p.realized_total_rs));}
  return rows.length?`<table><tbody>${rows.join("")}</tbody></table>`:"";
}
function actionsHTML(p){
  const cards=[];
  (p.calls||[]).forEach(c=>cards.push(`<div class="act"><div class="verb">Call this client</div><div>${esc(c.reason)}</div><div class="tax">${esc(c.script)}</div></div>`));
  (p.flags||[]).forEach(f=>cards.push(`<div class="act"><div class="verb">${esc(f.action||"Review")}</div><div>${esc(f.evidence)}</div>${f.est_value?`<div class="tax">Worth about ${lcr(f.est_value)}</div>`:""}</div>`));
  if(p.tax && p.tax.n_gain_candidates>0)cards.push(`<div class="act"><div class="verb">Harvest gains this year (${esc(p.tax.fy)})</div><div>${p.tax.n_gain_candidates} lot(s) with tax-free headroom of ${lcr(p.tax.headroom)}.</div><div class="tax">Est. tax saved: ${lcr(p.tax.tax_saved_if_harvested)}${p.tax.loss_note?" · "+esc(p.tax.loss_note):""}</div></div>`);
  return cards.length?cards.join(""):`<div class="insuf">Nothing pressing on this account right now.</div>`;
}
function renderClient(id){
  const opts=Object.entries(DATA.clients).map(([cid,c])=>`<option value="${esc(c.name)}" data-id="${cid}">`).join("");
  const search=`<div class="searchbox">
    <label class="eyebrow" for="csearch">Find a client</label><br>
    <input id="csearch" list="clist" placeholder="Type a client name…" autocomplete="off" aria-label="Find a client">
    <datalist id="clist">${opts}</datalist></div>`;
  const c=DATA.clients[id];
  if(!c){
    app.innerHTML=`<div class="wrap" style="padding-top:26px"><div class="eyebrow">Prescribe</div>
      <h1 style="font-size:clamp(24px,3.4vw,32px);margin-top:8px">The client audit</h1>${search}
      <p class="insuf">Pick a client above to open their audit pack.</p></div>`;
    wireSearch(); return;
  }
  const hh=c.household||{};
  const hchips=[hh.name?`<span class="hchip">🏠 ${esc(hh.name)} · ${hh.members} member${hh.members===1?"":"s"}</span>`:"",
    ...(c.chips||[]).map(ch=>`<span class="hchip">${esc(ch)}</span>`)].join("");
  const secs=DATA.sections.map(key=>{
    const p=(c.pack||{})[key]||{}; const meta=SEC_META[key];
    if(p.insufficient){
      return `<div class="section" id="sec-${key}"><div class="eyebrow">${esc(meta[1])}</div>
        <h3>${esc(meta[0])}</h3><p class="insuf">We can't say this honestly for you yet — ${esc(p.reason)}.</p></div>`;
    }
    const prose=(c.prose&&c.prose[key])||fallbackProse(key,p,c.name);
    const vis=visualFor(key,p);
    const body = key==="actions"
      ? actionsHTML(p)
      : `<p class="prose">${esc(prose)}</p>
         ${bigFor(key,p)?`<div class="big">${bigFor(key,p)}</div>`:""}
         ${vis?`<div class="visual">${vis}</div>`:""}
         <details><summary>How we know this</summary>
           ${tableFor(key,p)}
           <div class="method">${esc(p.method||"")}</div>
         </details>`;
    return `<div class="section" id="sec-${key}"><div class="eyebrow">${esc(meta[1])}</div>
      <h3>${esc(meta[0])}</h3>${body}</div>`;
  }).join("");
  app.innerHTML=`<div class="wrap" style="padding-top:22px">
    <div class="eyebrow">Prescribe · client audit</div>${search}
    <div class="profile">
      <h1>${esc(c.name)}</h1>
      <div>${hchips}</div>
    </div>
    ${secs}
    <div class="foot">Every number above is computed from ${esc(c.name)}'s own transaction and holdings history, as on ${esc(DATA.asof)}.</div>
  </div>`;
  wireSearch();
}
function wireSearch(){
  const inp=document.getElementById("csearch"); if(!inp) return;
  inp.onchange=()=>{
    const opt=[...document.querySelectorAll("#clist option")].find(o=>o.value===inp.value);
    if(opt) location.hash="client/"+opt.dataset.id;
  };
}

nav();
</script>
"""


if __name__ == "__main__":
    sys.exit(main())
