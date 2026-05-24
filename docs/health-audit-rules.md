# Standing guardrails from 2026-05 health audit

Learnings from the first full codebase health pass. Each rule maps to a bug
category found in the audit — treat them as patterns to watch for.

CLAUDE.md points here; the rules below are part of the engineering baseline
that applies to every PR.

## Compute pipeline rules

- **`load_thresholds()` returns `dict[str, Decimal]`.** All compute functions
  that accept thresholds must type-hint them as `Mapping[str, Decimal]` not
  `dict[str, float]`. When using threshold values in arithmetic with floats
  (e.g. `/100.0`), cast first: `float(thresholds["key"]) / 100.0`.

- **Division guards on all ratio columns.** Any `x / y` where `y` comes from
  benchmark or external data must use `.replace(0, pd.NA)` to guard zero
  denominators. Holiday runs and early history produce zero vols → `inf` risk
  states. Pattern: `stock_col / bench_col.replace(0, pd.NA)`.

- **`np.select` ordering is conservative-first.** When conditions overlap at
  threshold edges, the more-restrictive/negative state must appear first.
  "Avoid before Underweight before Overweight", "Below Trend before High before
  Elevated". First-match-wins — wrong order silently overrides the right state.

- **NAV gaps must be logged before filling.** Never call `ffill()` or
  `fillna()` on NAV/price series without first counting and logging gap rows.
  Pattern: `if na_count := df["close"].isna().sum(): log.warning("nav_gaps", count=int(na_count)); df["close"] = df["close"].ffill()`.

- **VIX NaN requires per-condition guards.** Missing VIX must not silently
  force the regime to a non-Risk-On state. Use `vix_valid = vix.notna()` and
  gate conditions: `is_risk_on = ... & (~vix_valid | (vix < threshold))`.

- **No SQL f-strings without `# noqa: S608` with justification.** Global S608
  suppression was removed. Every SQL f-string must have a per-line noqa with a
  reason explaining why the identifier is safe (constant, whitelist-validated,
  schema-introspected — never user input).

## Frontend rules

- **No `SELECT *` on time-series tables.** Enumerate exact columns matching
  the TypeScript type. `SELECT *` on a 30-column regime table breaks silently
  if columns are added/removed.

- **No `parseFloat()` on financial Decimal fields.** Use `Number()` for
  display-only coefficients (deployment multiplier). For anything stored as
  money, keep as string and format at display time.

- **No non-null assertions (`!`) on nullable DB fields.** Use optional
  chaining (`?.`) with `?? '0'` fallback. The assertion produces `NaN%` in
  the UI when the field is NULL — which is valid DB state for new funds.

## Architectural red flags

- **`atlas.api.*` must not import from `atlas.simulation.*` internals.** Use
  the simulation context's public `__init__.py` exports only.

- **Fake 202 responses must not persist `status='running'`.** Either spawn
  the subprocess or return `status='queued'` with no DB row. A running row
  that never completes permanently blocks the 30-min concurrency guard.

- **Auth middleware must exist before shipping M6.** Current
  `atlas/api/__init__.py` has no Supabase JWT middleware. All M6 API routes
  must be behind `get_current_user` dependency before going to production.
