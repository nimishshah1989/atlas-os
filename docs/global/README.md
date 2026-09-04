# Global Atlas — docs

The US-market sibling platform: S&P 500 stocks + US-listed ETFs, schema `atlas_global`, its own board (`frontend-global/`).

- [plan.md](plan.md) — the approved plan (2026-09-04): decisions, architecture, schema, orchestration, methodology, phases and their definition-of-done gates. **The versioned source of truth.**
- [data-sources.md](data-sources.md) — every feed with its cadence, fallback and gate; the Alpaca paper-only caveat; the SIP gate protocol and its result log.
- Methodology — lives inside [plan.md](plan.md) ("Methodology spec — metrics, lenses, weights") until Phase 3 splits it out as `methodology.md`.
- [ADR-0006](../adr/0006-second-schema-atlas-global.md) — why a second schema: one schema per market, zero cross-schema references, the modulith context and its four subtree edges.
- [frontend-design.md](frontend-design.md) — the board's design language, capabilities and pages (proposal for FM sign-off; nothing in `frontend-global/` is built until it is signed off).
- Not yet written: `taxonomy.md` (Phase 2, FM-reviewed) and `runbook.md` (Phase 1, once the orchestrators are croned).

Rules that apply verbatim from India: rule #0 (no synthetic or derived data — gates assert on real produced rows), one schema per market (`scripts/ops/schema_gate.py --market global`), no hardcoded methodology numbers (`atlas_global.atlas_thresholds`).
