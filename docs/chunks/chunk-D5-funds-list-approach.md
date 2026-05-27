# Chunk D.5 — /v6/funds list + SwitchProposalsBanner

## Data scale
- atlas_fund_scorecard: ~400–600 rows (NAV-lagged snapshot; single latest snapshot)
- atlas_mf_switch_rules: 14 rows (seeded by migration 095)
- atlas_mf_recommendation_daily: 0 rows (NAV gap, migration 096 documents this)
- atlas_paper_portfolio: 0 rows (v6.0 launch state — empty)

## Approach

### switch_proposals.ts
Reads atlas_mf_switch_rules WHERE active=TRUE then:
1. Gets held iid set (B.1's getHeldIidSet — empty set in v6.0)
2. For each held fund, queries atlas_mf_recommendation_daily for current peer_quartile
3. If peer_quartile <= current_quartile_floor AND a Q1/Q2 fund exists in same category with >= min_target_consistency_months → yields a SwitchProposal
4. atlas_mf_recommendation_daily is currently empty: query returns [] without error (NULL check guards)
5. getSwitchProposals() returns Promise<SwitchProposal[]> — empty when portfolio empty OR when no fund meets switch criteria

### FundsList.tsx  
Client component (≤500 LOC) that:
1. Shows IndustrySnapshot (funds variant) — existing component
2. Shows BubbleRiskReturnChart with funds data — risk=ret_6m std proxy, ret=composite_score-derived
3. Shows SignatureMatrix (funds variant) — placeholder cells until v6.1 has factor data
4. Shows ranked table with all required columns
   - PortfolioBadge default visible column: reads from heldIidSet prop
   - GradeChip for atlas grade (derived from composite_score quartile)
   - Expense ratio from sub_metrics JSONB
   - 3y CAGR from ret_12m (proxy — real 3y CAGR is v6.1 work, atlas_fund_metrics_daily has it)
   - ColumnChooser for optional columns

### page.tsx modification
Thin RSC (≤250 LOC):
- Fetches: getFundsForDate, getIndustrySnapshot('funds'), getHeldIidSet, getSwitchProposals
- Passes all data to FundsList client component
- SwitchProposalsBanner renders above FundsList

### SwitchProposalsBanner.tsx
Client component (≤200 LOC):
- Accepts proposals: SwitchProposal[]
- Silent when proposals.length === 0
- Expanded accordion on click showing source_fund → target_fund pairs

## Wiki patterns checked
- portfolio_holdings.ts pattern for empty-set handling
- funds.ts for existing data shape
- IndustrySnapshot.tsx for component interface

## Existing code reused
- `getHeldIidSet()` from B.1
- `IndustrySnapshot` component (C.11)
- `BubbleRiskReturnChart` (C.8)
- `SignatureMatrix` (C.12)
- `PortfolioBadge` (B.6)
- `GradeChip` (A.7)
- `ColumnChooser` + `useColumnPreferences` (A.3)
- `toNumber()` from lib/v6/decimal.ts (A.10)

## Edge cases
- atlas_mf_recommendation_daily empty → getSwitchProposals returns []
- atlas_paper_portfolio empty → getHeldIidSet returns Set() → 0 proposals, no badge
- NULL composite_score → grade shown as 'failed-gate'
- NULL expense_ratio → '—' display
- NULL ret_12m → '—' display

## Extended fund row type
getFundsExtended() adds to existing ScreenFund:
- expense_ratio: string | null (from sub_metrics->>'expense_ratio')
- composite_score_raw: string | null
- rank_in_category: number | null
- category_size: number | null
- is_atlas_leader: boolean | null
- is_avoid: boolean | null

## Expected runtime on t3.large
- switch_proposals: ~2ms (14 rules, 0 held funds → early return)
- getFundsExtended: ~50ms (single scorecard join, ~500 rows)
- Total page: ~100ms server render
