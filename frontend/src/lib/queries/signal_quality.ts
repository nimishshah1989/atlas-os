// The lens IC journal — the measured answer to "do Atlas's scores precede returns?".
// One row per (lens, horizon, cap cohort, era), written by scripts/foundation/eval_signal.py.
//
// t_stat is DELIBERATELY NOT SELECTED. Every value in that column is inflated: 1,343 dates
// of 126-session overlapping windows is roughly 11 independent observations, not 1,343, so
// a t_stat of 32 is an artefact of the overlap. Not selecting it is the only way to be sure
// it never reaches a screen; the page says why in plain English instead.
import 'server-only'
import sql from '@/lib/db'

export type SignalRow = {
  lens: string
  horizon_d: number
  cohort: string
  era: string
  n_dates: number
  /** average cross-section size behind each date's IC */
  mean_n: number | null
  mean_ic: number | null
  hit_rate: number | null
  /** raw decile spread as a fraction. Corrupted on some rows — pass through displaySpread(). */
  mean_spread: number | null
  /** share of the cross-section that carried a cap band. v_stock_cap has no date
   *  dimension, so historical eras read ~0.59 and the missing 41% are non-randomly the
   *  names that later left the universe. Must be shown wherever a cap band is shown. */
  cap_coverage: number | null
  first_date: string
  last_date: string
}

export type SignalGrade = 'carries signal' | 'weak' | 'no evidence'

/** Three states, no fourth. A NULL IC is "no evidence", never a reading of zero — a cohort
 *  that is one tie block has no ordering to correlate. */
export function classifySignal(r: { mean_ic: number | null; hit_rate: number | null }): SignalGrade {
  if (r.mean_ic == null) return 'no evidence'
  const mag = Math.abs(r.mean_ic)
  if (mag >= 0.03 && r.hit_rate != null && r.hit_rate >= 0.55) return 'carries signal'
  if (mag >= 0.01) return 'weak'
  return 'no evidence'
}

/** The decile spread, or null where it is not reportable.
 *
 *  86 instruments carry 28,507 sub-₹1 close_adj rows before June 2024 — PRIVISCL reads
 *  ₹0.05 on 2020-03-23 with adj_factor = 1.0, so the raw close is wrong, not the
 *  adjustment. A single such row lands in a decile and drags the arithmetic mean: the
 *  composite/126d/wide/small cell reads +2811%. Rank-IC is immune (ranks do not care how
 *  far wrong a price is); the mean spread is not. Anything outside ±100% over a quarter is
 *  the defect, not a return, so it is withheld rather than printed. */
export function displaySpread(v: number | null): number | null {
  return v != null && Math.abs(v) < 1.0 ? v : null
}

export async function getSignalQuality(): Promise<SignalRow[]> {
  const rows = await sql<Record<string, string | null>[]>`
    SELECT lens, horizon_d, cohort, era, n_dates, mean_n, mean_ic, hit_rate,
           mean_spread, cap_coverage, first_date::text, last_date::text
    FROM atlas_foundation.atlas_signal_ic
    ORDER BY era, lens, horizon_d, cohort
  `
  const n = (v: string | null): number | null => (v == null ? null : Number(v))
  return rows.map((r) => ({
    lens: String(r.lens),
    horizon_d: Number(r.horizon_d),
    cohort: String(r.cohort),
    era: String(r.era),
    n_dates: Number(r.n_dates),
    mean_n: n(r.mean_n),
    mean_ic: n(r.mean_ic),
    hit_rate: n(r.hit_rate),
    mean_spread: n(r.mean_spread),
    cap_coverage: n(r.cap_coverage),
    first_date: String(r.first_date),
    last_date: String(r.last_date),
  }))
}
