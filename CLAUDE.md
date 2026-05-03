---
nimish-os: 1.0
project: atlas-os
domain: fintech              # fintech | restaurant | content | health | other
regime: [SEBI, DPDP]              # YAML list, e.g. [SEBI, DPDP] — drives skill auto-load
stack: [python, fastapi, postgres]                 # YAML list, e.g. [python, fastapi, postgres, react]
has_frontend: true   # true | false
scale: large                 # small | medium | large
---

# atlas-os

This file orients agents working on this project. Global engineering rules live at `~/.claude/CLAUDE.md`. Hooks fire on every edit regardless of mode (planned milestone, ad-hoc chat, exploration). The frontmatter above drives:
- regime-specific skill auto-load (Indian regulatory matrix from `~/forge-skills/<regime>/`)
- fintech context detection for hooks (no float on money, no PII in logs, FastAPI Decimal encoder)
- Design Protocol activation if `has_frontend: true`

## Project-specific notes

- Stack-specific decisions: see `decisions.jsonl` (append-only, hash-chained).
- ADRs: see `.ruflo/adr/` (managed by `ruflo-adr` plugin).
- Active milestone status: see `tasks.jsonl` if present, or run `npx ruflo hive-mind status`.

## What goes in this file (vs the global one)

- Project-only conventions (e.g. "we use Polars not pandas in this codebase")
- Project-only paths or entry points
- Project-only deferred work / known limitations

Do NOT duplicate global rules from `~/.claude/CLAUDE.md` here — they're already loaded.
