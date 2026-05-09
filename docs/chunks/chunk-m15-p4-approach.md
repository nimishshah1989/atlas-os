# M15 Phase 4 — Rule-Based Portfolio Builder Approach

## Summary

Build the Rule-Based tab for `/portfolios/new`, including catalog lib, 4 small components, RuleBuilderForm, server action extension, narrative renderer improvement, and Vitest tests.

## Data scale
No DB queries — frontend-only forms. State values are small enums (5-7 items each). Backend validated via `_rule_allowlist.py`.

## Files to create/modify

**Create:**
- `frontend/src/lib/rule-catalogs.ts` — enum catalogs mirroring Python allowlist
- `frontend/src/components/strategy/RuleCard.tsx` — card with enable toggle
- `frontend/src/components/strategy/StateMultiSelect.tsx` — chip-based checkbox group
- `frontend/src/components/strategy/BreadthGateSlider.tsx` — slider row per breadth gate
- `frontend/src/components/strategy/RuleBuilderForm.tsx` — composes full form (allow-large if needed)
- `frontend/src/__tests__/portfolios/rule-catalogs.test.ts`
- `frontend/src/__tests__/portfolios/RuleCard.test.tsx`
- `frontend/src/__tests__/portfolios/StateMultiSelect.test.tsx`
- `frontend/src/__tests__/portfolios/BreadthGateSlider.test.tsx`
- `frontend/src/__tests__/portfolios/RuleBuilderForm.test.tsx`

**Extend:**
- `frontend/src/app/portfolios/new/actions.ts` — add `createRuleBasedPortfolio`
- `frontend/src/app/portfolios/new/page.tsx` — wire RuleBuilderForm in rule-based tab
- `frontend/src/app/portfolios/[id]/CompositionView.tsx` — improved narrative renderer
- `frontend/src/__tests__/portfolios/actions.test.ts` — extend with rule-based action tests

## Approach

1. Catalogs: direct 1:1 mirror of Python frozensets as `as const` arrays
2. RuleCard: simple wrapper with `enabled` prop → opacity-50 + pointer-events-none on body
3. StateMultiSelect: horizontal chip group using Set<string>, toggle on click — mirrors EditGatePolicyModal pattern
4. BreadthGateSlider: null = off (no slider shown), number = slider visible; fmt determines display
5. RuleBuilderForm: `useState` with full FormState object; submit strips disabled rules; allow-large marker if exceeds 600 LOC
6. Server action: mirrors createStaticPortfolio pattern; POST to `/api/portfolios/rule-based`; response has `strategy_id`
7. Narrative: expanded RuleBasedComposition with all 6 filter types + breadth + sizing/rebalance metadata
8. Page: replace placeholder div with `<RuleBuilderForm />`

## Edge cases

- Empty state filter → yellow banner warning (no instruments will match)
- 400 from backend (allowlist violation) → inline error at form top
- 409 (concurrent backtest) → toast text
- All filters disabled → config will be near-empty; still valid for backend (backend runs with no filters = all instruments)
- Breadth gate null values are dropped from payload (not sent to backend)

## Tokens used
`bg-paper`, `border-paper-rule`, `text-ink-{primary,secondary,tertiary}`, `text-signal-{pos,neg,warn}`, `bg-accent`, `font-{serif,sans,mono}`, `rounded-[2px]`

## Expected runtime
Pure frontend — no compute. Tests run in <10s via Vitest + jsdom.
