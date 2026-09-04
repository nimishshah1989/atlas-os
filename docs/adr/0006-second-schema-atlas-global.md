# 0006 — A second schema, `atlas_global`, for the US market

- **Status:** Accepted (2026-09-04)
- **Context chunk:** Global Atlas — the US-market sibling platform (`docs/global/plan.md`)
- **Amends:** CLAUDE.md architectural rule #1 ("Single schema") → "one schema per market,
  zero cross-schema references"

## Context

Atlas has been a one-schema system since the consolidation recorded in
`docs/table-census.md`: every read and write goes to `atlas_foundation`, and
`scripts/ops/schema_gate.py` proves it mechanically by counting references to any other
schema in the live code paths. That rule was earned. The census (§6) records how the
multi-schema Atlas before it rotted: the same daily metrics lived in both `atlas.*` and
`foundation_staging.*`, the mirror between them had been broken since 2026-06-25 while the
board kept serving a stale Market Pulse, and market-regime was computed in three schemas at
once. Every cross-schema read was a place where two copies of one fact could disagree
with nobody watching.

A US platform already existed in that world and was dropped. FM decision D7 (census §4b–4c)
removed the `us_atlas` schema — 16 tables (`instruments`, `stock_ohlcv`,
`atlas_stock_metrics_daily`, `atlas_etf_metrics_daily`, `atlas_thresholds`, …) fed nightly by
Stooq crons (`us_stocks_daily.py`, `us_daily.py`, `stooq_daily_update.py`) — and its
`global_atlas` twin (11 tables), because their producers fed only orphan `us-*` routes:
compute with no consumer. The schema split did not cause that failure; the missing consumer
did. But the census also shows what a second schema costs when it is allowed to read across.

The FM now wants a second platform in the same repo — S&P 500 stocks + US-listed ETFs,
separate URL, separate UI, its own scoring methodology, baskets as the product. It needs USD
money columns, an `America/New_York` trading day, a calendar anchored on SPY bars instead of
NIFTY 50, its own `atlas_thresholds`, and its own DB role for a Vercel-hosted frontend. The
question this ADR answers is where its tables live and what the two markets may share.

## Decision 1 — `atlas_global` in the same Supabase project; one schema per market; zero cross-schema references

The US market gets its own schema, `atlas_global`, in the existing Supabase project. Rule #1
becomes: **every market owns exactly one schema, and no code path names another market's
schema.** A file in the India tree may not mention `atlas_global.`; a file in the global tree
may not mention `atlas_foundation.` (nor the dropped `atlas.`, `us_atlas.`, `global_atlas.`,
`mfwatch.`, `public.`). Reuse between the markets happens in Python, on pure code — never
through a query that crosses the boundary.

The schema is served by a dedicated role, `atlas_global_app`, with SELECT on all of
`atlas_global` and DML only on the tables the board writes (`basket_*`,
`etf_classification_override`, `atlas_thresholds` + audit, `app_user`, `chat_*`). It has no
grants on `atlas_foundation`, and the India role gets none on `atlas_global` — Postgres
enforces the rule as well as the gate.

*Rejected: a `market` column in `atlas_foundation`.* Every India table, index, view,
freshness rule and query would need a discriminator, and every one of them is a place to
forget it. The India board is prod today; touching every table it reads to add a market it
never shows is risk with no return. The two markets also differ in shape, not only in value:
INR vs USD, IST vs ET, NIFTY 50 vs SPY as the calendar, 21 sectors vs a three-level taxonomy,
ETFs rolled up from stocks vs ETFs as the product.

*Rejected: a separate Supabase project.* It doubles the operational surface — credentials,
backups, poolers, Auth configuration, pg_cron — for a product the same FM runs from the same
box and the same repo, and it makes the one thing that legitimately is shared (the
deploy/health tooling) harder. The isolation we need is the schema boundary plus roles,
which the same project gives us.

## Decision 2 — `atlas.global_market` is a bounded context with four explicit subtree edges

The US compute lives in a new modulith context, `atlas/global_market/` (the natural name,
`atlas/global`, is a Python keyword). `scripts/hooks/check_module_boundaries.py` lists it in
`CONTEXTS`, so the default rule applies from the first file: no imports of another context's
internals. Before this change the hook skipped the package entirely — packages outside
`CONTEXTS` are not checked at all.

Four imports are allowed by module *prefix* (`ALLOWED_SUBTREE_EDGES`), because they are the
pure, I/O-free pieces the plan reuses verbatim:

| Edge | Why |
|---|---|
| `atlas.global_market → atlas.lenses.compute` | the pure scorers (`score_technical`, `score_fundamental`, `score_valuation`: dict in, dict out). `atlas.lenses.data` and `atlas.lenses.pipeline` read `atlas_foundation` and stay forbidden |
| `atlas.global_market → atlas.compute.signal_eval` | rank-IC / decile-spread math for `/methodology/signal` |
| `atlas.global_market → atlas.compute._session` | `open_compute_session` (statement_timeout reset on the pooled connection) |
| `atlas.global_market → atlas.portfolio.engine` | buy-and-hold replay for basket NAV (M2) — one accounting truth, not a second engine |

A subtree edge is narrower than a context edge in `ALLOWED_EDGES`: it names the module
prefix, so widening it is a visible diff.

*Rejected: widening `SHARED_KERNEL`.* The kernel is `atlas.primitives`, `atlas.db`,
`atlas.config`, `atlas.preflight`. Adding `atlas.lenses.compute` there would let every
context import the scorers, which is a bigger decision than this platform needs.

## Decision 3 — what the global tree reuses from India, and how

Reuse is by import (pure code) or by copy (I/O code with a schema baked in); never by a
cross-schema read.

- **Import unchanged:** `atlas.lenses.compute.{technical,fundamental,valuation}`;
  `atlas.compute.signal_eval`; `atlas.compute._session`; `atlas.portfolio.engine`;
  `scripts/foundation/technicals.py`; `scripts/foundation/universe_core.members`
  (`floor_inr` is just a `Decimal`); the `scripts/foundation/_db` helpers, re-exported
  through `scripts/global_market/_gdb.py` with `SCHEMA = "atlas_global"` and an
  `eod_cutoff()` at 17:00 ET.
- **Shared kernel, parameterised:** `atlas.db.get_engine(session_tz)` — one pool per
  session timezone, `lru_cache` keyed by it; India callers still call `get_engine()` and get
  IST. `atlas.db.load_thresholds(schema=...)` validates against
  `_VALID_SCHEMAS = {atlas_foundation, atlas_global}`. `atlas.config.MARKETS` carries each
  market's schema, timezone, close hour, calendar anchor, currency and history start.
- **Copy + US parameters:** `compute_composite` → `blend()` (parity-tested on real
  `atlas_foundation` rows); `validate_lenses.py` → `validate_global.py` (same `Gate`
  class); `freshness_guard.py` + the producer-registry test; `write_health_snapshot.py`;
  the `atlas_daily.sh` step/gate/runfile/Telegram shape.
- **Not reused:** `atlas.lenses.data`, `atlas.lenses.pipeline`, the NIFTY 50 calendar
  adapter, the India catalyst keyword taxonomy, `cap_cohort.py` (SEBI ranks) — each has
  India's schema or India's market baked in.

## Consequences

- **`schema_gate.py` is a two-tree gate.** India's live-file lists keep their meaning and
  gain `atlas_global` in the forbidden set; a global tree (`scripts/global_market/**`,
  `atlas/global_market/**`, `frontend-global/src/lib/queries/**`, globbed so the gate runs
  before the tree exists) forbids `atlas_foundation.` and the dropped schemas.
  `--market india|global|all`; `--count` unchanged; exit 1 on any hit.
- **`_VALID_SCHEMAS` names only live schemas.** `atlas`, `us_atlas`, `global_atlas` — dead
  since D7 — are gone from the allowlist, so a stale caller fails loudly instead of querying
  a schema that no longer exists. `tests/unit/test_load_thresholds_callers.py` now passes
  `atlas_foundation` (and is marked `unit`, so CI actually runs it).
- **CI runs both trees** (`Schema gate (india)`, `Schema gate (global)` in
  `lint-types-tests`), so a cross-schema reference cannot merge.
- **Two engines per process where both markets run.** Each is a small pool (`POOL_SIZE` +
  `MAX_OVERFLOW`); the global nightly runs at 01:00 UTC and the India one at 10:30 UTC, so
  they do not contend for the session pooler.
- **The D7 lesson is carried forward, not the schema.** Every global producer names the
  board surface that reads it in the same phase (`docs/global/plan.md`, Orchestration). A
  schema is allowed to exist only while something renders it.
