'use client'
// Resolve v4 design tokens to concrete hex for libraries that need real colour
// values (Recharts/Lightweight take SVG attrs, not CSS vars). Re-reads when the
// day/night toggle flips data-theme on <html>, so charts recolour live. Returns
// null until mounted — callers fall back to a neutral default for first paint.
import { useEffect, useState } from 'react'

export type ThemeTokens = {
  grid: string
  rule: string
  tick: string
  label: string
  panel: string
  surface: string
  txt1: string
  txt2: string
  pos: string
  neg: string
  warn: string
  brand: string
  decile: (d: number | null | undefined) => string
}

function read(): ThemeTokens {
  const cs = getComputedStyle(document.documentElement)
  const v = (n: string) => cs.getPropertyValue(n).trim()
  const ramp = Array.from({ length: 10 }, (_, i) => v(`--decile-${i + 1}`))
  return {
    grid: v('--color-edge-hair'),
    rule: v('--color-edge-rule'),
    tick: v('--color-txt-3'),
    label: v('--color-txt-2'),
    panel: v('--color-surface-panel'),
    surface: v('--color-surface-base'),
    txt1: v('--color-txt-1'),
    txt2: v('--color-txt-2'),
    pos: v('--color-sig-pos'),
    neg: v('--color-sig-neg'),
    warn: v('--color-sig-warn'),
    brand: v('--color-brand'),
    decile: (d) => (d == null || d < 1 ? v('--color-surface-inset') : ramp[Math.min(10, Math.max(1, Math.round(d))) - 1]),
  }
}

export function useThemeTokens(): ThemeTokens | null {
  const [tokens, setTokens] = useState<ThemeTokens | null>(null)
  useEffect(() => {
    setTokens(read())
    const obs = new MutationObserver(() => setTokens(read()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [])
  return tokens
}
