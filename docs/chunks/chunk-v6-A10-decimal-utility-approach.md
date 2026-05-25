# Chunk A.10 — Decimal Transport Utility + Lint Gate

## Problem
postgres-js stringifies `NUMERIC` columns as `string`. Recharts/D3 chart props
expect `number`. Without an explicit conversion boundary, charts silently render
at width 0 (Recharts treats the string as `NaN`, produces no bar/line).

## Data scale
No DB query needed — this is a pure TypeScript utility with zero DB interaction.

## Chosen approach
1. Create `frontend/src/lib/v6/decimal.ts` — thin, no-dependency utility that
   wraps the conversion once and throws on invalid input (fast-fail, not silent NaN).
2. `Intl.NumberFormat` for INR formatting (global, zero deps).
3. Percentage functions accept the raw decimal fraction (e.g., `0.183`) and
   multiply by 100 for display — consistent with how Postgres stores returns.
4. Patch `frontend/.eslintrc.json` with a `no-restricted-syntax` AST-selector
   rule that fires on `Number(x)` call expressions where the callee is the
   built-in `Number`. Because we cannot do type-narrowing in ESLint without
   full type-aware linting (which requires `parserOptions.project`), the rule
   applies a path-scoped `overrides` block to `src/components/v6/**` and
   `src/lib/queries/v6/**` so it only fires where Decimal strings are expected.
   The rule message proposes `toNumber(x)` from `@/lib/v6/decimal`.

## Existing code reused
- `frontend/src/lib/format-inr.ts` — consulted for `Intl.NumberFormat` locale
  and lakh/crore formatting pattern. NOT imported (v6 utility is standalone to
  avoid v1→v6 coupling).
- `frontend/src/lib/__tests__/format-cell.test.ts` — consulted for test structure.

## Wiki patterns checked
- `~/.forge/knowledge/wiki/index.md` — N/A (no forge wiki in this project).
- Existing `format-number.ts` uses `Number(raw)` pattern — the new rule will
  fire on this file if it were in-scope, but it is NOT in `components/v6/**`
  or `lib/queries/v6/**`, so no false positives.

## Edge cases
- `toNumber(null)` → `null` (pass-through, not 0)
- `toNumber(undefined)` → `null` (same)
- `toNumber("not-a-number")` → `TypeError` (NOT `NaN`) — fast-fail
- `toNumber("")` → `TypeError` (empty string is not valid)
- `toNumber("  123  ")` → `123` (trimmed, valid)
- `formatINR(null)` → `"—"` (em-dash sentinel)
- `formatPct` and `signedPct` accept decimal fraction (0.183 → 18.3%)
- Compact INR: `₹1.25 Cr` uses 1-decimal rounding for crore, `₹12.5 L` for lakh

## ESLint approach
`.eslintrc.json` currently uses `"extends": "next/core-web-vitals"`.
The `eslint.config.mjs` exists but is the flat-config format; the project uses
the legacy `.eslintrc.json` as the primary config for Next.js.
Adding `overrides` in `.eslintrc.json` with `no-restricted-syntax` is the
correct approach — no new plugins needed.

## Expected runtime
Vitest: <100ms (pure function, no I/O).
