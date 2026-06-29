// Relative bubble colour. Holdings-weighted lens scores (and the fund composite) cluster tightly
// in the ~40–55 band, so a fixed absolute cut (e.g. ≥60 green / <45 red) paints almost every fund
// and ETF red and zero green — the colour carries no signal. Instead colour by standing WITHIN the
// cohort shown: top quartile = pos (green), bottom quartile = neg (red), middle = neutral (grey).
// Self-calibrating, so it always shows a readable spread regardless of the absolute range.

export type Tone = 'pos' | 'neutral' | 'neg'

// 25th and 75th percentile of the finite values (nearest-rank). Returns [q25, q75].
export function quartileCuts(values: number[]): [number, number] {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b)
  if (v.length === 0) return [0, 0]
  const at = (p: number) => v[Math.min(v.length - 1, Math.max(0, Math.ceil(p * v.length) - 1))]
  return [at(0.25), at(0.75)]
}

// Tone for a value given the cohort's [lo, hi] quartile cuts. null → neutral (unscored).
export function relativeTone(value: number | null | undefined, lo: number, hi: number): Tone {
  if (value == null || !Number.isFinite(value)) return 'neutral'
  if (value >= hi) return 'pos'
  if (value < lo) return 'neg'
  return 'neutral'
}
