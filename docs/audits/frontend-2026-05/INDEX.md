# Atlas Frontend Audit — 2026-05

Page-by-page UX/visual audit of every user-visible route. Report-only; no
code changes in this pass. Fixes happen in a subsequent prioritization +
implementation pass once findings are reviewed.

**Audited environment:** localhost:3001 (Next.js dev server pointing at
production Supabase DB + production internal API at 13.206.34.214:8002).
Same data and same UI as atlas.jslwealth.in.

**Scoring rubric:** see [CRITERIA.md](./CRITERIA.md)
**Per-page template:** see [TEMPLATE.md](./TEMPLATE.md)

---

## Audit progress

| # | Route | Type | Score | Report | Status |
|---|---|---|---|---|---|
| 1 | `/` | Home / regime | — | [home.md](./pages/home.md) | pending |
| 2 | `/stocks` | Screener | — | [stocks-list.md](./pages/stocks-list.md) | pending |
| 3 | `/stocks/[symbol]` | Detail | — | [stocks-detail.md](./pages/stocks-detail.md) | pending |
| 4 | `/sectors` | Screener | — | [sectors-list.md](./pages/sectors-list.md) | pending |
| 5 | `/sectors/[name]` | Detail | — | [sectors-detail.md](./pages/sectors-detail.md) | pending |
| 6 | `/etfs` | Screener | — | [etfs-list.md](./pages/etfs-list.md) | pending |
| 7 | `/etfs/[ticker]` | Detail | — | [etfs-detail.md](./pages/etfs-detail.md) | pending |
| 8 | `/funds` | Screener | — | [funds-list.md](./pages/funds-list.md) | pending |
| 9 | `/funds/[mstar_id]` | Detail | — | [funds-detail.md](./pages/funds-detail.md) | pending |
| 10 | `/us` | Country dashboard | — | [us.md](./pages/us.md) | pending |
| 11 | `/us/sectors/[name]` | Detail | — | [us-sector-detail.md](./pages/us-sector-detail.md) | pending |
| 12 | `/global` | Global pulse | — | [global.md](./pages/global.md) | pending |
| 13 | `/global/country/[ticker]` | Detail | — | [global-country-detail.md](./pages/global-country-detail.md) | pending |
| 14 | `/intelligence` | Morning dashboard | — | [intelligence.md](./pages/intelligence.md) | pending |
| 15 | `/intelligence/agents` | Chatbot | — | [intelligence-agents.md](./pages/intelligence-agents.md) | pending |
| 16 | `/intelligence/daily-brief` | Brief | — | [intelligence-daily-brief.md](./pages/intelligence-daily-brief.md) | pending |
| 17 | `/strategies` | List | — | [strategies-list.md](./pages/strategies-list.md) | pending |
| 18 | `/strategies/[id]` | Detail | — | [strategies-detail.md](./pages/strategies-detail.md) | pending |
| 19 | `/strategies/lab` | Strategy lab | — | [strategies-lab.md](./pages/strategies-lab.md) | pending |
| 20 | `/strategies/lab/[id]` | Genome detail | — | [strategies-lab-detail.md](./pages/strategies-lab-detail.md) | pending |
| 21 | `/strategies/lab/engine` | Engine room | — | [strategies-lab-engine.md](./pages/strategies-lab-engine.md) | pending |
| 22 | `/portfolios` | List | — | [portfolios-list.md](./pages/portfolios-list.md) | pending |
| 23 | `/portfolios/new` | Builder | — | [portfolios-new.md](./pages/portfolios-new.md) | pending |
| 24 | `/portfolios/[id]` | Detail | — | [portfolios-detail.md](./pages/portfolios-detail.md) | pending |
| 25 | `/signals` | Feed | — | [signals-list.md](./pages/signals-list.md) | pending |
| 26 | `/signals/[id]` | Detail | — | [signals-detail.md](./pages/signals-detail.md) | pending |
| 27 | `/admin/composite-proposals` | Admin queue | — | [admin-composite-proposals.md](./pages/admin-composite-proposals.md) | pending |
| 28 | `/admin/policies` | Admin policies | — | [admin-policies.md](./pages/admin-policies.md) | pending |
| 29 | `/admin/weight-performance` | Admin metrics | — | [admin-weight-performance.md](./pages/admin-weight-performance.md) | pending |
| 30 | `/admin/validator` | Admin validator | — | [admin-validator.md](./pages/admin-validator.md) | pending |
| 31 | `/health` | Health dashboard | — | [health.md](./pages/health.md) | pending |
| 32 | `/methodology` | Methodology | — | [methodology.md](./pages/methodology.md) | pending |
| 33 | Global navigation / topbar | Shell | — | [global-nav.md](./pages/global-nav.md) | pending |

---

## Cross-cutting findings (filled at end)

See [FINDINGS_SUMMARY.md](./FINDINGS_SUMMARY.md) — patterns observed on 3+
pages that warrant a system-wide fix (design tokens, shared components,
nav refactor, etc.).

---

## How to read a per-page report

Each report file under `pages/` follows [TEMPLATE.md](./TEMPLATE.md):

1. Screenshot reference + one-paragraph "what this page is"
2. 10-dimension scorecard with sub-2 scores explained
3. Itemized findings, each tagged P0–P3 with file:line where known
4. "What works well" so we don't regress on fixes
5. Cross-page patterns flagged for the summary
