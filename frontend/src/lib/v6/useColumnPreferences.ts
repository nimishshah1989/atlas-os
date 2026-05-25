// frontend/src/lib/v6/useColumnPreferences.ts
//
// Per-page column visibility hook for v6 data tables.
// SSR-safe: initial render uses `defaults`; useEffect patches in LS preference
// after hydration so there is no server/client mismatch.
//
// LS key format: `v6.columns.<pageKey>`

'use client'

import { useState, useCallback, useEffect } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

export type ColumnGroup =
  | 'returns'
  | 'risk'
  | 'technicals'
  | 'atlas'
  | 'benchmarks'

// ── LS helpers ───────────────────────────────────────────────────────────────

function readLS(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeLS(key: string, value: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Storage unavailable (private browsing, quota exceeded). Ignore.
  }
}

// ── Hook ─────────────────────────────────────────────────────────────────────

/**
 * Manages visible column list for a named page.
 *
 * @param pageKey   Unique key per table/page — namespaces LS under `v6.columns.<pageKey>`
 * @param defaults  Column keys visible by default (initial render + reset target)
 *
 * @returns `visible` — ordered array of visible column keys (SSR = defaults)
 *          `setVisible` — replace visible list and persist to LS
 *          `reset` — restore to `defaults` and clear LS entry
 */
export function useColumnPreferences<T extends string>(
  pageKey: string,
  defaults: T[],
): {
  visible: T[]
  setVisible: (cols: T[]) => void
  reset: () => void
} {
  const lsKey = `v6.columns.${pageKey}`

  // SSR-safe: start with defaults; hydration effect reads LS and patches in.
  const [visible, setVisibleState] = useState<T[]>(defaults)

  useEffect(() => {
    const raw = readLS(lsKey)
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as T[]
        if (Array.isArray(parsed) && parsed.length > 0) {
          setVisibleState(parsed)
        }
      } catch {
        // Corrupt LS value — silently keep defaults.
      }
    }
  // Run only when pageKey or defaults reference changes (i.e. on mount per page).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lsKey])

  const setVisible = useCallback(
    (cols: T[]) => {
      setVisibleState(cols)
      writeLS(lsKey, JSON.stringify(cols))
    },
    [lsKey],
  )

  const reset = useCallback(() => {
    setVisibleState(defaults)
    // Remove the LS entry so a future mount also starts from defaults.
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem(lsKey)
      } catch {
        // Ignore.
      }
    }
  // `defaults` is an array — including it would fire on every render if the
  // caller passes an inline literal. Intentionally omitted; the hook is
  // stable per `pageKey` (same semantics as persistence.ts pattern).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lsKey])

  return { visible, setVisible, reset }
}
