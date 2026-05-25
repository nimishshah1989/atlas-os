# Chunk A.3 — ColumnChooser + useColumnPreferences hook

## Summary
Three new files: a React hook for SSR-safe localStorage persistence, a modal component with 5 grouped column categories, and a test suite covering all 6 acceptance criteria.

## Approach

### useColumnPreferences.ts
- Generic over `T extends string` (column key union type)
- `pageKey` namespaces LS key to `v6.columns.<pageKey>`
- SSR-safe: `useState(defaults)` on initial render; `useEffect` patches in LS value on mount (no SSR mismatch)
- Returns `{ visible: T[], setVisible, reset }`
- No external deps — pure React hooks

### ColumnChooser.tsx
- No Radix Dialog available in package.json (only `@radix-ui/react-tooltip`) — use portal + focus trap pattern
- `createPortal` from `react-dom` for z-index isolation
- Esc key closes via `useEffect` + `keydown` listener
- Outside-click closes via `mousedown` listener on `document`
- Focus trap: `useRef` on modal, `focus()` on open, restore on close
- Settings gear icon trigger (top-right of table)
- 5 grouped checkbox sections: Returns / Risk / Technicals / Atlas signals / Benchmarks
- "Reset to default" button calls `reset()` from hook
- DESIGN.md tokens: `bg-paper`, `border-paper-rule`, `text-ink-primary`, `text-ink-secondary`, `bg-signal-pos/10` for checked state

### ColumnChooser.test.tsx
- 6 test cases:
  1. per-page key isolation (two instances with different pageKeys don't share state)
  2. reset restores defaults
  3. persistence to localStorage on toggle
  4. modal opens on settings-icon click
  5. modal closes on Esc keydown
  6. modal closes on outside-click; aria-modal + role="dialog" a11y

## Constraints
- LOC budget: hook ≤200, component ≤200, tests ≤300
- TypeScript strict; exports `ColumnGroup` discriminated union
- No emoji; DESIGN.md tokens only

## Edge cases
- `defaults` empty array: all groups hidden; reset restores empty
- `localStorage` unavailable (SSR, private browsing): silently falls back to defaults
- Multiple ColumnChoosers on same page with same `pageKey`: they sync (intentional — same page = same preference)

## Expected runtime
Pure frontend unit tests — sub-1s on any machine.
