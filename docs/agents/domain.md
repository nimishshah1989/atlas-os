# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root (if it exists)
- **`.ruflo/adr/`** — Architecture Decision Records, managed by the `ruflo-adr` plugin. Read ADRs that touch the area you're about to work in. (Note: this repo uses `.ruflo/adr/` rather than the default `docs/adr/` because the `ruflo-adr` plugin owns drift detection and indexing there.)
- **`decisions.jsonl`** at the repo root — append-only, hash-chained log of substantive engineering decisions. Lighter-weight than ADRs; scan recent entries for context that hasn't been promoted to an ADR yet.

If `CONTEXT.md` doesn't exist, **proceed silently**. Don't flag its absence; don't suggest creating it upfront. The producer skill (`/grill-with-docs`) creates it lazily when terms actually get resolved.

## File structure

Single-context repo. atlas-os is a modular monolith ("modulith") — each top-level package under `atlas/` is a bounded context (e.g. `atlas.api`, `atlas.compute`, `atlas.simulation`, `atlas.intelligence`, `atlas.agents`), but they share one root `CONTEXT.md` and one ADR directory rather than per-context glossaries.

```
/
├── CONTEXT.md                  ← root glossary (created lazily)
├── decisions.jsonl             ← append-only decision log
├── .ruflo/adr/                 ← Architecture Decision Records
└── atlas/
    ├── api/
    ├── compute/
    ├── simulation/
    ├── intelligence/
    ├── agents/
    └── primitives/             ← shared kernel
```

If the project later promotes any bounded context to having its own glossary, add a `CONTEXT-MAP.md` at the root and per-context `CONTEXT.md` files under `atlas/<context>/`, then update this file to multi-context.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/grill-with-docs`).

## Flag ADR conflicts

If your output contradicts an existing ADR in `.ruflo/adr/`, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_

The `ruflo-adr` plugin runs drift detection on commits, so contradictions are also caught at the hook layer — but surfacing them in the moment is faster than waiting for the hook to bite.
