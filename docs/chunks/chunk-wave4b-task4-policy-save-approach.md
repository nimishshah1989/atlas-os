# Chunk: Wave 4B Task 4 — Policy Save API + Validate-on-Save

## Data scale
`atlas_portfolio_policy` is a configuration table: one house-default row + at most one row per portfolio. Expected < 100 rows total. No scale concerns.

## Approach

### `policy-validate.ts` — pure TS port of Python `validate_policy`
Direct port of the 9 rules from `atlas/intelligence/policy/policy.py`. All field values arrive from the DB as strings (postgres driver convention); comparisons use `Number()` for numeric fields and strict string equality for enum fields. Returns `string[]` of violation messages; empty = valid.

Numeric comparison convention:
- pct fields: stored as whole numbers (5 = 5%), compared as numbers
- rank fields: stored as fractions [0, 1], compared as numbers
- int fields (min_holdings, max_positions): compared as numbers
- hard_stop_pct: must be > 0

### `/api/policy/route.ts` — PATCH save handler
Pattern: matches `propose/route.ts` conventions exactly.

**Logic:**
1. Parse body: `{ portfolioId: string | null, changes: Partial<Record<fieldKey, value | null>> }`
2. Load current effective policy from DB (house row + portfolio override row if portfolioId set)
3. Apply `changes` onto the current effective policy to build a candidate full-policy object
4. Run `validatePolicy(candidate)` — if violations, return HTTP 400 with `{error_code, message}`, write nothing
5. If valid:
   - `portfolioId === null` → UPDATE the `is_house_default = TRUE` row, set only the changed columns
   - `portfolioId` set → UPSERT the portfolio row:
     - For each changed field with non-null value: set that column
     - For each changed field with null value (revert): SET column = NULL
     - If no override row exists yet and any non-null changes: INSERT a new row
     - If override row exists: UPDATE it
6. Return `{data: <new effective policy>}` by re-reading via the same two-query load

**SQL**: parameterized tagged-template `sql` (postgres driver), never f-strings. Dynamic column lists built from the validated `changes` keys, which are whitelisted against the 17-field `POLICY_FIELDS` constant.

## Wiki patterns checked
- `propose/route.ts` — exact match for envelope, force-dynamic, parameterized sql
- `policy-compliance.test.ts` — exact match for vitest mock structure

## Existing code reused
- `@/lib/db` sql tagged template (same mock pattern as propose-route.test.ts)
- `EffectivePolicy` type from `@/components/portfolio/PolicyPanel`
- The two SELECT queries from `policy.ts` (house + portfolio override)

## Edge cases
- `portfolioId === null` → house default path (UPDATE only; no INSERT)
- Portfolio with no existing override row + non-null changes → INSERT
- Portfolio with existing override row → UPDATE only
- Field change value `null` → SET column = NULL (revert to inherit)
- Validation on candidate (post-changes) not on changes alone
- `trailing_stop_pct` legitimately NULL — skip Rule 9 if null

## Expected runtime
< 10ms per request (3 parameterized SQL queries max on a tiny table)

## File-size budget
- `policy-validate.ts`: ~80 LOC (pure function + types)
- `/api/policy/route.ts`: ~180 LOC (well within 600 LOC limit)
- test file: ~250 LOC (within 800 LOC limit)
