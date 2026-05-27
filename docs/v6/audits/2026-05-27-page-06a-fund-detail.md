# F.0 Audit · /v6/funds/F00001EBDX vs 06a-fund-ppfas.html

**Audit date:** 2026-05-27
**Live URL:** https://atlas.jslwealth.in/v6/funds/F00001EBDX (HTTP 200)
**Mockup file:** ~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/06a-fund-ppfas.html
**Verdict:** minor

## Section presence

| Section (from mockup) | One-line spec | Live status | Notes |
|---|---|---|---|
| Breadcrumb | Atlas › Funds › [Fund Name] | present | `FundDetailClient.tsx` renders breadcrumb (nav inside page via `FundHero`) |
| Page header | Serif 36px fund name + SWITCH IN/HOLD/SWITCH OUT stamp + meta chips (AMC, category, AUM, TER, manager, age, holdings, exit load) | present | `FundHero.tsx` renders fund name, action stamp, and meta chips; layout confirmed in component |
| Quartile pills panel | 4-pill widget showing Q1/Q2/Q3/Q4 with active pill highlighted, "last 24mo" label, "18 / 24 mo" footnote | partial | `FundHero.tsx` renders quartile pills; confirmed present. The "18 / 24 mo count" footnote may not be populated (requires historical quartile data per month) |
| 6-tile verdict strip | 3Y CAGR / Sharpe 3Y / Max drawdown 5Y / Alpha vs benchmark / Top-10 concentration / Category rank | present | `FundHero.tsx` renders verdict strip; tiles mapped from `FundDetail` fields |
| Performance chart section | 320px cumulative NAV growth chart (fund vs category median vs Nifty 500 TRI), timeframe chips | absent | No performance chart; `FundDetailClient.tsx` Overview tab shows `RankDecompositionCards` + `MultiBenchmarkRSWaterfall` (which uses return deltas, not NAV curve) |
| Drawdown chart | 220px drawdown trough chart below the performance chart | absent | No drawdown chart |
| Portfolio attribution section | 3-col: top-20 holdings table + sector allocation bars + performance attribution table (sector alpha contribution) | partial | `FundDetailClient.tsx` Holdings tab shows the top holdings list; sector allocation bars and attribution table are absent |
| Peer comparison table | Full-width table of category peers with current fund highlighted: name, 3Y/5Y CAGR, Sharpe, MaxDD, quartile pill, action chip | absent | No peer comparison table; `RankDecompositionCards` shows rank within category but not a full peer table |
| Quartile transition history | 130px SVG timeline showing Q1/Q2/Q3/Q4 per quarter over 3Y | absent | No quartile timeline chart on any tab |
| SWITCH check card | Checklist: criteria met/failed for whether this fund should be SWITCH IN/OUT; green/red check icons | partial | `SwitchProposalsBanner` shows switch proposals but not the individual rule-by-rule checklist card |
| Overview tab | RankDecompositionCards + RSWaterfall + returns summary | present | `FundDetailClient` Overview tab: confirmed present |
| Holdings tab | Top-20 holdings with ticker, sector, weight, Atlas verdict per holding | present | Holdings tab in `FundDetailClient` renders top holdings from `top_holdings` JSONB |
| Audit Trail tab | Placeholder (funds audit trail deferred to E.1) | present | "Audit Trail" tab renders but shows placeholder message |
| Footnote | Disclaimer + data-as-of | absent | No footnote |

## Token compliance

- [x] `FundHero.tsx` and `FundDetailClient.tsx` use semantic tokens throughout: `bg-signal-pos`, `text-signal-neg`, `border-teal`, `bg-paper-soft`, etc. Clean.
- [x] Tab nav: `border-teal text-teal` for active. Clean.
- [x] Fonts: `font-serif`, `font-sans`, `font-mono`. Clean.

## Component reuse

- [x] `FundHero`, `RankDecompositionCards`, `MultiBenchmarkRSWaterfall`, `GradeChip`, `SwitchProposalsBanner` — all from `components/v6/`. Correct.
- [ ] Missing: `FundNAVChart` — no cumulative NAV growth chart component.
- [ ] Missing: `FundDrawdownChart` — no drawdown trough chart component.
- [ ] Missing: `FundPeerTable` — no peer comparison table component.
- [ ] Missing: `QuartileTimeline` — no quartile transition history chart.
- [ ] Missing: `SwitchCheckCard` — no rule-by-rule SWITCH criteria checklist component.
- [ ] Missing: sector allocation bars in Holdings tab — only the holdings list is rendered, not the sector tilt visualization.

## Data correctness

- [x] Fund name, category, AUM, TER rendered from `getFundDetail()`. Real data.
- [x] 6-tile verdict strip: 3Y CAGR proxy (`ret_12m`), composite score, category rank rendered from live data.
- [x] RankDecompositionCards: rank components from fund scorecard. Real.
- [x] Holdings tab: top_holdings JSONB from `atlas_fund_scorecard.top_holdings` — real holdings data.
- [ ] Performance chart: absent — NAV history not fetched; `waterfallData` is set to `null` in page.tsx (comment says "TODO(v6.1)").
- [ ] Sharpe 3Y: sourced from `sub_metrics` JSONB if present; may be `—` for funds without Sharpe computed.
- [ ] Max drawdown 5Y: similarly from `sub_metrics` JSONB.
- [ ] Alpha vs benchmark: from `sub_metrics` JSONB; may be `—`.
- [ ] Quartile pills count ("18 / 24 mo"): no historical monthly quartile data queried; pill shows current quartile only.
- [ ] Peer comparison table: absent — no peers fetched.
- [ ] Quartile timeline: absent — no data.

## Per-gap closure plan

1. **Performance chart (NAV growth) absent** — file: `frontend/src/app/v6/funds/[code]/page.tsx`; change: add `getNAVHistory(code, months=36)` query from `atlas_fund_nav_daily`; create `frontend/src/components/v6/FundNAVChart.tsx` using Recharts LineChart; render fund NAV + category median + Nifty 500 TRI lines with timeframe chips (1Y/3Y/5Y). Wire into `FundDetailClient.tsx` Overview tab below the verdict strip. Comment at line 43-44 of `fund/[code]/page.tsx` notes this is `TODO(v6.1)`.

2. **Drawdown chart absent** — file: create `frontend/src/components/v6/FundDrawdownChart.tsx`; derive drawdown from NAV history using running-maximum formula; render as area chart (negative fill) at 220px height. Wire into Overview tab below NAV chart.

3. **Peer comparison table absent** — file: create `frontend/src/components/v6/FundPeerTable.tsx`; query: `getFundPeers(category, snapshotDate)` in `lib/queries/v6/funds.ts` — fetch all funds in the same category sorted by composite; render table with current fund highlighted (using `bg-accent/8` or similar). Wire into Overview or new "Peers" tab.

4. **Quartile transition timeline absent** — file: create `frontend/src/components/v6/QuartileTimeline.tsx`; data: `getQuartileHistory(code)` query on `atlas_fund_scorecard` ranked over monthly snapshots. Render 130px SVG with Q1/Q2/Q3/Q4 color segments per quarter. Wire into Overview tab.

5. **SWITCH check card absent** — file: create `frontend/src/components/v6/SwitchCheckCard.tsx`; show the rules that drove the current SWITCH proposal (from `atlas_switch_rules` — rule_name, description, pass/fail). Wire into Overview tab for funds that have switch proposals. Data: filter `switchProposals` by fund `iid` + join with `atlas_switch_rules`.

6. **Sector allocation bars missing from Holdings tab** — file: `frontend/src/components/v6/FundDetailClient.tsx` Holdings tab; change: after the top-holdings list, add sector tilt bars derived from `top_holdings` JSONB (group by sector, sum weights). Uses existing `top_holdings` data — no new query needed.
