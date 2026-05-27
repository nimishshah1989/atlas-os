---
chunk: D.6
project: atlas-os
date: 2026-05-26
task: /v6/funds/[code] detail page
---

## Data scale
- atlas_fund_scorecard: ~1000 rows per snapshot_date (no full-table scan needed)
- atlas_universe_funds: ~450-500 rows (small, no issue)
- atlas_paper_portfolio: EMPTY at v6.0 launch (holdingState = null)
- atlas_mf_recommendation_daily: EMPTY at v6.0 launch (switchProposals = [])

## Chosen approach

1. page.tsx (≤250 LOC): RSC. Fetches getFundDetail(code) + getHoldingState(iid) + getSwitchProposalsForFund(code). Passes all as props to FundDetailClient.
2. FundDetailClient.tsx (≤500 LOC): 'use client'. Hero + 3-tab layout (Overview / Holdings / Audit).
3. FundHero.tsx (≤300 LOC): 'use client'. Grade chip + PortfolioBadge expanded + SwitchProposalsBanner + manager/AUM/expense metrics + thesis bullets.

## Fund detail query
getFundDetail(code): single SQL joining atlas_fund_scorecard + atlas_universe_funds + atlas_fund_metrics_daily for latest snapshot. Returns all sub_metrics JSONB fields surfaced.

## AuditTrailTab handling
AuditTrailTab is stock-centric (universe membership, cell matches, signal calls). For funds, this audit trail structure doesn't apply. Render a fund-flavored placeholder: "Audit trail for funds shows scorecard provenance. Full fund audit (holdings provenance, benchmark drift) will be added in v6.0 final (Task E.1). Stocks-first launch per methodology lock."
This avoids calling getAuditTrail() for a fund iid which would return meaningless stock-centric data.

## top_holdings shape
{instrument_id, symbol, weight_pct, verdict} — verdict ∈ {POSITIVE, NEUTRAL, NEGATIVE, null}

## Edge cases
- top_holdings null → "Holdings data not available"
- holdingState null → PortfolioBadge silently absent
- switchProposals [] → SwitchProposalsBanner renders nothing  
- sub_metrics null → metrics show "—"
- No snapshot data → 404 from page.tsx
