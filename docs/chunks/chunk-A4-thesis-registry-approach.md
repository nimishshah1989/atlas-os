---
chunk: A4
project: atlas-os
date: 2026-05-26
status: planned
---

# Task A.4 — Thesis registry (19 archetypes) — Approach

## Problem
Build `frontend/src/lib/eli5/thesis.ts` — a pure-function library with no React imports
that maps `(archetype, cap_tier, tenure, direction, is_held, features) → ThesisBullets`.

## Data scale
No DB access needed — this is a pure function library operating on passed-in feature values.

## Chosen approach
Split per 600-LOC rule:
- `thesis-data.ts` — JSON-shaped archetype bullet templates (data only)
- `thesis.ts` — thin renderer: resolves placeholders, derives action verb, returns ThesisBullets

## Wiki patterns checked
- CONTEXT.md cell-state vocabulary: POSITIVE/NEUTRAL/NEGATIVE → display labels via ownership
- design-application.md §4: 19 archetype table with slugs and lead lines
- existing eli5-registry.ts: archetype ELI5 entries (source of truth for archetype names)

## Existing code reused
- Archetype slug names from `frontend/src/lib/eli5-registry.ts`
- Test pattern from `frontend/src/lib/__tests__/policy-entry-filter.test.ts`

## 19 archetypes (from design-application.md §4)
1. sector_relative_leadership (POSITIVE)
2. quality_momentum (POSITIVE)
3. bab_low_beta (POSITIVE)
4. mean_reversion (POSITIVE — dip buy)
5. liquidity_expansion (POSITIVE)
6. inflection (POSITIVE)
7. consolidation_breakout (POSITIVE)
8. structural (POSITIVE)
9. deep_value (POSITIVE)
10. low_vol_carry (POSITIVE)
11. breakout_with_pullback (POSITIVE)
12. idio_high_RS (POSITIVE)
13. obv_thrust (POSITIVE)
14. mean_reversion_overbought (NEGATIVE — was TRIM, now SELL per CONTEXT.md)
15. distribution (NEGATIVE)
16. volatility_spike (NEUTRAL/NEGATIVE — WATCH)
17. breakdown (NEGATIVE)
18. sector_drag (NEGATIVE)
19. sector_breakdown (NEGATIVE)

## Display-label derivation (CONTEXT.md authoritative)
| Cell state | is_held=false | is_held=true |
|---|---|---|
| POSITIVE | BUY | ACCUMULATE |
| NEUTRAL | WATCH | HOLD |
| NEGATIVE | AVOID | SELL |

NOTE: TRIM is NOT used — CONTEXT.md replaced it with SELL.

## Edge cases
- NEUTRAL direction with is_held → HOLD; without → WATCH
- Unknown archetype → throws Error (fail fast)
- Missing optional features → use sensible defaults in templates (e.g., "your sector")
- Placeholders in templates use `{{key}}` syntax resolved from features Record

## File split plan
- `thesis-data.ts`: archetype bullet templates as typed constants (~350 LOC)
- `thesis.ts`: types + generateThesis() renderer + placeholder resolver (~150 LOC)
- `__tests__/thesis.test.ts`: 76+ parameterized cases (~500 LOC)
- `tests/fixtures/thesis_archetype_keywords.json`: keyword fixtures for all 19 archetypes

## Expected runtime
Pure function, no DB. Tests run in <1s.
