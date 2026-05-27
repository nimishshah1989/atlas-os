# Audit: <ROUTE>

**Audited:** 2026-05-16
**Route:** `<ROUTE>` (e.g., `/stocks/AAPL`)
**File:** `frontend/src/app/<path>/page.tsx`
**Screenshot:** `../screenshots/<slug>.png`
**Score:** __/20

---

## What this page shows

One paragraph describing what the user sees and what the page is for.
This grounds every reviewer who reads the audit.

---

## Per-dimension scoring

### 1. Clickability — _/2
What's broken / what's good. Cite specific elements.

### 2. Navigation — _/2
### 3. Tooltips — _/2
### 4. Toggled detail — _/2
### 5. Timestamps — _/2
### 6. Wasted space — _/2
### 7. Consistency — _/2
### 8. Hardcoded values — _/2
### 9. IA & hierarchy — _/2
### 10. Responsive — _/2

---

## Findings (line items)

### F-N — <short title> [P0|P1|P2|P3]

**Where:** Specific element / screenshot region / file:line.
**Issue:** What's wrong, observably.
**User impact:** What the user actually experiences as a result.
**Suggested fix:** One-paragraph fix direction (not a full diff).
**Related code:** `frontend/src/components/.../...tsx:NNN`

---

## What works well

Things to KEEP. Don't regress these when fixing other items.

---

## Cross-page patterns

Anything observed here that's likely repeated on other pages (so the
cross-cutting roll-up can pick it up at the end).
