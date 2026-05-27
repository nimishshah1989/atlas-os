# F.0 Audit Template · v6 Page vs Mockup

**Audit date:** 2026-05-27
**Live URL:** https://atlas.jslwealth.in/<route>
**Mockup file:** ~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/<mockup>.html
**Verdict:** clean | minor | major

## Section presence

| Section (from mockup) | One-line spec | Live status | Notes |
|---|---|---|---|
| Nav / Topbar | Sticky 56px bar: Atlas brand + 8-item nav + data-as-of timestamp | present / partial / absent | ... |

## Token compliance

- [ ] Only paper/ink/signal Tailwind classes? → list violations OR "clean"
- [ ] No inline hex colors / rgba()? → list OR "clean"
- [ ] Source Serif 4 / Inter / JetBrains Mono fonts only? → confirm

## Component reuse

- [ ] Page imports from `frontend/src/components/v6/`? → list components used
- [ ] Any inline JSX that should be a v6 component? → list with file:line

## Data correctness

- [ ] Page renders real values (not `—` placeholders) for all major fields? → list NULL fields if any
- [ ] No synthetic-looking data (round numbers, identical rows)?

## Per-gap closure plan

1. **<gap title>** — file(s) to touch: `<path>`; change: <what to do>
