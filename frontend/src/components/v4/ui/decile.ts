// Atlas v4 — the calibrated D1→D10 perceptual ramp (coral → amber → mint).
// Used identically EVERYWHERE a decile appears (meter, ladder, sector/stock
// pages) so a decile's colour always means the same thing to the FM. The actual
// hexes are theme-scoped CSS vars (--decile-1..10 in globals.css) so the ramp
// reads on both the light and dark surfaces; here we just resolve the var name.

/** Theme-aware colour for a decile — for inline style on meters AND the decile
 *  figure, so the number and its meter always match. Empty/null → inset well. */
export function decileColor(d: number | null | undefined): string {
  if (d == null || d < 1) return 'var(--color-surface-inset)'
  return `var(--decile-${Math.min(10, Math.max(1, Math.round(d)))})`
}
