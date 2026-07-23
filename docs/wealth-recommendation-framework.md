# Wealth: client-portfolio recommendation framework

Status: **proposal for FM review** (2026-07-18). Data foundation is live; everything
in §4-§7 is design, not yet built. Grounded end-to-end in the real Jhaveri book —
every number below is computed from loaded data, none are illustrative.

## 1. What exists now (built this session)

**Pipeline** — `scripts/wealth/`: Drive PDFs → `parse_jhaveri.py` (word-position
parser, per-file reconciliation gates: units×NAV vs value, Σholdings vs stated
total, Σweights≈100, asset-split vs total) → `load_parsed.py` (idempotent) →
`map_schemes.py` (name-bridge into `atlas_foundation.de_mf_master`) →
`cohort_report.py` (read-only analysis). Raw PDFs live outside the repo at
`/home/ubuntu/jhaveri_data/` (PII, never committed).

**Schema `wealth`** (FM-approved second schema; PII-hardened, no anon/authenticated
access): `clients` (PAN-keyed) → `client_reports` (snapshot per valuation date;
flow summary + MV split + overall XIRR) → `holdings` (client × scheme × folio;
invested/withdrawn/dividends/units/cost/NAV/value/weight/abs-return/XIRR) →
`schemes` (615 display names, plan/option parsed, `mstar_id` bridge, match
provenance). The single-schema gate is unaffected (`wealth` is not in its regex;
`scripts/wealth/` is not in its scan list) — if wealth ever wires into
`atlas_daily.sh`, FM decides whether the gate expands.

**Load state**: 221/221 PDFs parse + reconcile clean → 219 clients, 220 reports
(as-on 14/07/2026), 3,309 holdings, ₹439.4 cr.

**Identity bridge (three layers, built in this order):**
1. Morningstar equity master: 202/510 schemes (Atlas-scored funds).
2. **AMFI NAVAll registry** (`amfi_bridge.py`): official name + AMFI code + ISIN +
   SEBI category for **99.0% of value**. Leftovers are genuinely not mutual funds
   (AIF/SIF long-short products, ~₹3.4 cr — an insight in itself).
3. **Morningstar holdings by ISIN** (`fetch_unmapped_holdings.py`): the holdings
   service accepts ISIN selectors, so every NON-DEBT scheme got its constituent
   holdings pulled (200 funds, 18.8k rows) and its mstar_id resolved. Only misses:
   5 dead segregated portfolios (correctly empty).

**Coverage after bridging (by value):** Equity ₹229 cr — 99% look-through, 75%
Atlas-scored; Hybrid ₹120 cr — 98% look-through; Commodities ₹57 cr — 100%
look-through; Debt ₹33 cr — AMFI identity only (per FM: debt stays category-level).

**Look-through** (`wealth.client_stock_exposure`, 247k client×stock rows over
₹419 cr of fund exposure): 62% resolves to Atlas-scored Nifty-500 stocks, 5.3%
identified-but-unscored stocks, 3.8% unidentified Indian stocks, 15.9% gold/silver
ETF units, 6.3% cash, 2.6% debt instruments inside hybrids. **Of pure stock
exposure, 87.1% is inside Atlas's scored 498** — the honest ceiling on stock-level
scoring today.

## 2. What the book actually looks like (the raw material)

| Fact | Number |
|---|---|
| AUM shape | 16 clients >₹5cr hold 37% of AUM; 96 at ₹1-5cr hold 47%; 108 <₹1cr hold 16% |
| Asset mix | 52% equity, 27% hybrid, 7% debt, 13% others (gold/silver FoFs) |
| Biggest sleeves | Multi-Asset ₹66cr, Dynamic Asset Alloc ₹63cr, Mid-cap ₹47cr, Aggr. Hybrid ₹38cr, Small-cap ₹34cr |
| Fragmentation | median 12 schemes/client; 73% of clients hold **3+ funds of the same sub-category** (₹197 cr affected) |
| Concentration | 81 clients have one fund ≥25% of portfolio; 58 have HHI ≥ 0.20 |
| Flows | 123 SIP-active vs 97 lumpsum-only; 35 dividend-takers; 19 heavy redeemers |
| Outcomes | median client XIRR 15.0%; 43 clients under 12%; 79 above 16% |
| Quality | median value-weighted Atlas composite 62.3 (range 45.8-81.4); **32.4% of scored equity value sits in category-bottom-quartile funds**; 98 clients hold >30% laggards |
| House book | PPFAS Flexi Cap in 66 clients, Kotak Midcap 56, Quant Multi Cap 54, ICICI BAF 41 |
| Single-AMC risk | Quant AMC: ₹44.5 cr across 130 clients (~10% of book) |
| Hygiene | 29 clients still hold dead segregated-portfolio units; 100% Regular plans (zero Direct — consistent with distributor book) |
| Swap capacity | 86.6% of value is LTCG-eligible (>1y); a single tax-clean swap per client yields median **+5.6 pts** weighted-composite gain (192 clients have one available) |
| True exposure | Top book-level stocks via look-through: ICICI Bank ₹13.4 cr and HDFC Bank ₹11.3 cr, each held by ~215/219 clients; 168 of 217 clients have 20-30% of stock exposure in financials |
| Illusory diversification | avg client touches ~401 distinct stocks through funds, but effective N ≈ 90 (median 83) — index-like exposure at active-fund fees |
| Behaviour evidence | SIP-active clients out-earn lumpsum-only: median XIRR 15.3% vs 14.2% |
| Tax reality | ₹166 cr unrealized gains (+60.7% on cost); 182 clients hold 2x+ positions — swap sizing must budget LTCG deliberately |
| Product-push ledger | median entry dates cluster: Quant funds mid-2021, small-caps 2021-23, BAF 2023, Defence index May-2025, silver FoFs Aug-2025, gold-silver FoF Nov-2025 |

Taxonomy note: Jhaveri's report engine is internally inconsistent (e.g. silver
FoFs appear under Hybrid sections but count as "Others" in the summary). The
engine must re-classify from AMFI/Morningstar category once the full master
lands — never trust the report's fold for analytics.

## 3. Goal A — segmentation

Two layers, both glass-box (no black-box clustering until rule-based segments are
exhausted — auditability is the product's DNA and the RM must be able to say *why*
a client is in a segment):

**Layer 1 — structural (who they are):** size band (Emerging <1cr / Core 1-5cr /
Key >5cr) × engagement (SIP-active / lumpsum-only / income-taker) × revealed risk
posture (equity+aggressive-hybrid share: <40 conservative / 40-70 balanced / >70
growth). All computable today from `client_reports` alone.

**Layer 2 — need-state (what they need next):** derived flags, one client can
carry several: *performance-rescue* (XIRR <8% or laggard share >30% — 98 clients),
*consolidator* (3+ same-category funds — 160 clients), *concentration-risk* (HHI
≥0.2 or single-AMC >25%), *hygiene* (side-pockets, dust lines <1%, IDCW leakage),
*healthy-optimizable* (clean book, composite below segment top-quartile).

Segments drive **playbooks** (the recommendation templates in §5), not just
reporting. Later, once monthly snapshots accumulate, add behavioural features
(drawdown-time redemptions = panic-seller flag) and revisit clustering with the
panel data.

## 4. Goal B — portfolio evaluation (the scorecard)

**v1 IS BUILT** (`build_scorecard.py` → `wealth.client_scorecard`, 220 rows) and
is deliberately outcome-anchored per FM: a client compounding ≥15% XIRR is graded
A and the default stance is *stay the course* — recommendations require an
evidence gate (outcome < 12%, laggard share > 30%, heavy duplication, or dead
units), never score-chasing for its own sake.

**The gradient that validates the engine** (real data): outcome grades track
forward quality monotonically — Grade A clients (110, ₹243 cr) hold avg weighted
composite 62.5 with 41% laggard share; Grade D clients (20, ₹38 cr) hold 54.6
with 66% laggard share. What Atlas scores well is what actually made clients
money; the worst outcomes sit in the worst-scored funds today.

Full lens blend for v2, 0-100, weights in `atlas_foundation.atlas_thresholds`:

1. **Quality (40%)** — value-weighted Atlas fund composite over the scored equity
   sleeve (later hybrid/debt). Already computed: cohort median 62.3.
2. **Laggard drag (15%)** — % of scored value in category-bottom-quartile funds.
3. **Diversification (15%)** — HHI, top-holding weight, effective N (1/HHI),
   same-category duplication count, single-AMC share.
4. **Risk alignment (15%)** — asset mix vs segment risk posture; small+mid-cap
   share; (phase 2, from NAV series) portfolio vol, max drawdown, down-capture
   vs a category-blend benchmark.
5. **Hygiene (10%)** — side-pocket units, dust holdings, dormant laggards
   (>3y old AND bottom-quartile), IDCW leakage where no income need.
6. **Tax/friction posture (5%)** — LT share (swap capacity), exit-load exposure.
   Note: Regular-plan expense drag is deliberately NOT scored — direct-plan
   migration guts distributor economics; it is a business decision, not an
   engine recommendation.

Every scorecard displays its **coverage tier** honestly: Tier-1 value (Atlas
composite available), Tier-2 (NAV metrics only), Tier-3 (category heuristics
only — currently most hybrid/debt). Cohort today: 62 clients ≥80% Tier-1 on
equity, 41 below 50% — coverage itself is a data-quality KPI the engine must
drive toward 95% (§7).

Derivations render as expandable trees exactly like the board's DecileLadder /
constituent trees — a client asking "why is my score 54?" gets the full glass box.

## 5. Goal C — recommendations (minimum moves, maximum delta)

**Move types, ordered by friction:**
1. **SIP redirect** — zero tax, zero load, zero realization: future flows go to
   the better fund. First lever for the 123 SIP-active clients.
2. **Laggard swap (LTCG-clean)** — sell bottom-quartile fund held >1y, buy the
   playbook fund in the same sub-category. 86.6% of book value is eligible; use
   each FY's ₹1.25L LTCG exemption as a per-client tax budget the optimizer
   spends deliberately.
3. **Consolidation** — 3+ same-category funds → best 1-2 (often combinable with
   #2 in the same transaction set).
4. **Trim** (concentration >25% single fund / >X% single AMC) and **hygiene
   exits** (dust lines, write-off recognition of side-pockets).

**Optimizer:** greedy, constrained: rank all candidate moves by
`Δ(portfolio score) per unit of friction` where friction = realized tax + exit
load + a per-move relationship cost; take top moves until `≤ N per quarter`
(default 3) or marginal Δ < threshold. Constraints: no STCG except hygiene
emergencies, min move size, asset-mix drift ≤5pp unless the goal IS de-risking,
never breach segment risk posture. All knobs in `atlas_thresholds`.

**Cluster-level recommendations are the unlock for 220+ clients:** the house
book means one research decision fans out consistently — e.g. a single "replace
fund X with Y in sub-category Z" verdict applies to 41-66 clients at once, each
client's version differing only in sizing/tax path. RMs get one story to tell,
compliance gets one documented rationale, and the dry-run already shows a median
+5.6-pt composite gain from ONE swap per client.

**Measurement (non-negotiable, day 1):** every recommendation is logged
(hash-chained, `decisions.jsonl` style) with lifecycle
`proposed → presented → accepted → executed → measured`. The client's pre-rec
portfolio becomes the **counterfactual shadow book**; the walk-forward
champion/challenger machinery from `atlas/portfolio` replays both and reports
realized delta quarterly. No measurement → no credibility → no fee migration.

## 6. Business model lens

The engine converts a transactional distribution book into a recurring advisory
relationship: (a) quarterly auto-generated Portfolio Health Report per client
(glass-box, Atlas-branded), (b) advisor console ranking WHO to call by
`available Δ × AUM` (191931 alone is 158 clients / ₹336 cr — an RM territory,
not a family), (c) measured value narrative ("your book: +X pts quality, +Y%
vs counterfactual") underwriting a fee/AUM-based advisory tier, (d) family
roll-ups (`family_group` already loaded) for the real households in the data.
The same scorecard is the prospecting tool: run any prospect's CAS/valuation
PDF through the pipeline → instant diagnostic — the demo IS the sales pitch.

## 7. Build order (each step unlocks the next)

1. **Full AMFI scheme master + NAV ingest** (extends the existing AMFI boundary;
   real source, free): identity + NAV for debt/hybrid/FoF → bridge coverage
   ~95%, unlocks scoring beyond equity. Single biggest gap; everything in §4-§5
   is throttled by it.
2. **Risk metrics from NAV series** (vol / MDD / down-capture / rolling returns)
   for every bridged scheme → completes Lens 4 and the risk-return trade-off view.
3. **Hybrid/debt scoring extension** — category-relative ranks reusing the fund
   lens pattern (needs 1+2).
4. **Holdings look-through** via `de_mf_holdings` (already ingested for universe
   funds): true stock-level overlap between a client's funds ("your 4 flexi-caps
   are 62% the same portfolio") — the most persuasive consolidation artifact.
5. **Scorecard + optimizer as nightly jobs** writing `wealth.client_scorecard_daily`
   / `wealth.recommendations` (gated like every Atlas producer; FM decides
   whether they join `atlas_daily.sh` or a separate wealth orchestrator).
6. **Advisor console** (board page over the wealth schema behind auth — NOT the
   anon key; schema is already revoked from anon) + client one-pager PDF.
7. **Monthly re-ingestion** of valuation PDFs → snapshot panel → behavioural
   features, panic-seller detection, measured rec outcomes (§5).

## 8. The output (what this produces, concretely)

1. **Client Portfolio Report** — auto-generated per client (PDF/page, glass-box):
   outcome grade + XIRR vs peers; scorecard with derivations; look-through truths
   (effective stocks, financials share, top-10 stocks, what your funds actually
   own); 0-3 recommended moves, each carrying *evidence → action → expected
   incremental value (composite pts + historical return spread context) → cost
   (tax/load) → confidence*. A-grade clean books explicitly get "no changes
   recommended". This is what the RM takes into the meeting.
2. **Advisor console** — auth-only board page over `wealth`: priority queue
   (needs-attention × AUM; today: 175/220 flagged, of which 45 are C/D-grade
   performance rescues holding ₹87 cr), segment map, cluster recommendations
   (one verdict fans out to all holders of a house-book fund), coverage tiles.
3. **The recurring engine** — monthly valuation re-ingestion (snapshot panel →
   behaviour features), nightly scorecard refresh off Atlas scores, recommendation
   lifecycle log (proposed→presented→accepted→executed→measured) with shadow-book
   counterfactual deltas. The measured delta is the fee-migration story.

## 9. Open items for FM

- Bless the `wealth` schema name + the §7 order (esp. #1, which touches the
  ingestion stable).
- Recommendation governance: advisor-in-the-loop always (engine proposes, human
  presents); confirm.
- Direct-plan stance (§4 note) — excluded from scoring by design; confirm.
- The 191931 mega-group: RM book or genuine family? Changes roll-up semantics.
- Data handling: PDFs + `wealth` schema hold PAN/contact PII on the prod box —
  confirm retention/access policy before any board surface exists.
