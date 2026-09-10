// src/lib/basketDraft.ts — the pure half of "create a basket": parse and validate what the form
// sent, against the thresholds the database holds. No I/O, no floats on money or weights.
//
// WEIGHTS ARE INTEGERS HERE. A percentage typed as "33.33" becomes 333,300 micro-fractions
// (1e-6 of capital), the sum must be exactly 1,000,000 and the thresholds are compared in the
// same units — so "33.33 + 33.33 + 33.34" is 100 and "33.3 × 3" is not, with no float ever
// deciding. basket_constituents.target_weight_frac (numeric(12,8)) receives the fraction as a
// decimal STRING ("0.333300"), which is also what the marker and the gate read (Σ = 1 exactly).
//
// Σ MUST BE 100. The DDL and the plan define the constituents as "fractions summing to 1"
// (06_baskets.sql; a Σ=1 trigger is planned), validate_baskets check G asserts it nightly, and
// a basket saved at 90% would fail that gate every night. So the remainder is not cash by
// choice; cash is only the rounding residue of fractional fills. India's builder allowed ≤100
// with the rest in cash — a different data model (params.weights), deliberately not ported.

export type DraftInput = {
  name: string
  kind: string
  capital: string
  rows: { symbol: string; weightPct: string }[]
}

/** What the create action hands back to the form: the reasons, any notes, and what was typed. */
export type FormState = { errors: string[]; notes: string[]; values: DraftInput }

/** The three M2 thresholds the builder needs, as atlas_thresholds NUMERIC strings. */
export type DraftLimits = {
  defaultCapitalUsd: string
  maxPositionFrac: string
  minWeightFrac: string
}

export type DraftRow = { symbol: string; weightMicro: number }

export type ParsedDraft = {
  name: string
  kind: 'etf' | 'stock'
  /** Whole dollars, as a digits-only string (basket_master.initial_capital numeric(18,2)). */
  capital: string
  rows: DraftRow[]
}

export type ResolvedInstrument = {
  instrument_id: string
  symbol: string
  asset_class: 'etf' | 'stock'
  name: string | null
  is_active: boolean
  fractionable: boolean | null
}

export type Constituent = { instrument_id: string; symbol: string; weight_frac: string }

export type Parsed = { ok: true; draft: ParsedDraft } | { ok: false; errors: string[] }
export type Checked =
  | { ok: true; constituents: Constituent[]; notes: string[] }
  | { ok: false; errors: string[] }

export const KINDS = ['etf', 'stock'] as const
const MICRO = 1_000_000
const NAME_MIN = 2
const NAME_MAX = 80
const PCT_RE = /^\d{1,3}(\.\d{1,4})?$/
const DOLLARS_RE = /^\d{1,12}$/
const SYMBOL_RE = /^[A-Z0-9.\-$]{1,12}$/
const DECIMAL_RE = /^\d+(\.\d+)?$/

/** "33.33" (percent, ≤ 4 dp) → 333300 micro-fractions; null when malformed. */
export function pctToMicro(pct: string): number | null {
  const s = pct.trim()
  if (!PCT_RE.test(s)) return null
  const [i, f = ''] = s.split('.')
  return Number(i) * 10_000 + Number(f.padEnd(4, '0'))
}

/** An atlas_thresholds fraction ("0.250000") → 250000 micro-fractions. Throws on a malformed row. */
export function fracToMicro(frac: string): number {
  const s = frac.trim()
  if (!DECIMAL_RE.test(s)) throw new TypeError(`Not a decimal fraction: ${JSON.stringify(frac)}`)
  const [i, f = ''] = s.split('.')
  return Number(i) * MICRO + Number(f.padEnd(6, '0').slice(0, 6))
}

/** 333300 → "0.333300" — the numeric(12,8) literal the row stores. */
export function microToFrac(micro: number): string {
  return `${Math.floor(micro / MICRO)}.${String(micro % MICRO).padStart(6, '0')}`
}

/** Whole dollars from a threshold NUMERIC ("100000.000000") for the ≥ comparison, as BigInt. */
function wholeDollars(numeric: string): bigint {
  const s = numeric.trim()
  if (!DECIMAL_RE.test(s)) throw new TypeError(`Not a decimal amount: ${JSON.stringify(numeric)}`)
  return BigInt(s.split('.')[0])
}

export function parseDraft(input: DraftInput, limits: DraftLimits): Parsed {
  const errors: string[] = []
  const name = input.name.trim().replace(/\s+/g, ' ')
  if (name.length < NAME_MIN || name.length > NAME_MAX)
    errors.push(`Name must be ${NAME_MIN}–${NAME_MAX} characters.`)

  const kind = input.kind.trim() as ParsedDraft['kind']
  if (!KINDS.includes(kind)) errors.push(`Kind must be one of ${KINDS.join(', ')}.`)

  const capital = input.capital.trim().replace(/[,\s]/g, '')
  const floorDollars = wholeDollars(limits.defaultCapitalUsd)
  if (!DOLLARS_RE.test(capital)) errors.push('Capital must be a whole number of dollars.')
  else if (BigInt(capital) < floorDollars)
    errors.push(`Capital must be at least $${floorDollars.toLocaleString('en-US')} (basket_default_capital_usd).`)

  const cap = fracToMicro(limits.maxPositionFrac)
  const floor = fracToMicro(limits.minWeightFrac)
  const rows: DraftRow[] = []
  const seen = new Set<string>()
  const filled = input.rows.filter((r) => r.symbol.trim() !== '' || r.weightPct.trim() !== '')
  if (filled.length === 0) errors.push('Add at least one constituent.')
  for (const r of filled) {
    const symbol = r.symbol.trim().toUpperCase()
    if (!SYMBOL_RE.test(symbol)) {
      errors.push(`"${r.symbol.trim() || '(blank)'}" is not a symbol.`)
      continue
    }
    if (seen.has(symbol)) {
      errors.push(`${symbol} is listed twice.`)
      continue
    }
    seen.add(symbol)
    const micro = pctToMicro(r.weightPct)
    if (micro === null || micro <= 0) {
      errors.push(`${symbol}: weight must be a percentage with at most four decimals.`)
      continue
    }
    if (micro < floor) errors.push(`${symbol}: weight ${r.weightPct.trim()}% is below the ${microToPct(floor)}% floor (basket_min_weight_frac).`)
    if (micro > cap) errors.push(`${symbol}: weight ${r.weightPct.trim()}% is above the ${microToPct(cap)}% cap (basket_max_position_pct).`)
    rows.push({ symbol, weightMicro: micro })
  }
  const total = rows.reduce((s, r) => s + r.weightMicro, 0)
  if (filled.length > 0 && rows.length === filled.length && total !== MICRO)
    errors.push(`Weights sum to ${microToPct(total)}%; they must sum to exactly 100%.`)

  if (errors.length) return { ok: false, errors }
  return { ok: true, draft: { name, kind, capital, rows } }
}

/** 333300 → "33.33" (trailing zeros trimmed), for messages only. */
export function microToPct(micro: number): string {
  const whole = Math.floor(micro / 10_000)
  const frac = String(micro % 10_000).padStart(4, '0').replace(/0+$/, '')
  return frac ? `${whole}.${frac}` : String(whole)
}

/** Equal weights for `n` names, in micro-fractions, summing to EXACTLY 1,000,000.
 *
 *  Three names cannot be weighted equally in a fixed-point world: 333,333 × 3 is 999,999 and the
 *  basket is a micro-fraction short of itself, which the Σ=1 trigger on `basket_constituents`
 *  refuses outright. So the remainder is given to the FIRST row rather than dropped or spread —
 *  one name carries 33.3334% and the arithmetic closes. Which row gets it is arbitrary and
 *  therefore stated: the first, because a seeded basket arrives strongest-first and the extra
 *  micro-fraction belongs on the name the FM already ranked highest.
 *
 *  These are a STARTING POINT the FM edits, not a recommendation. Equal weight says nothing about
 *  conviction; it says "I have not decided yet", which is the honest state of a basket that was
 *  seeded from a list one click ago. */
export function equalWeights(n: number): number[] {
  if (n <= 0) return []
  const each = Math.floor(MICRO / n)
  const weights = Array.from({ length: n }, () => each)
  weights[0] += MICRO - each * n
  return weights
}

/** A comma-separated `?symbols=` list → the builder's rows, equal-weighted and de-duplicated.
 *  Anything that is not a plausible symbol is dropped rather than carried into the form as a row
 *  the action will only refuse later. */
export function seedRows(param: string | null | undefined, limit = 50): { symbol: string; weightPct: string }[] {
  const symbols = [
    ...new Set(
      (param ?? '')
        .split(',')
        .map((s) => s.trim().toUpperCase())
        .filter((s) => SYMBOL_RE.test(s)),
    ),
  ].slice(0, limit)
  return equalWeights(symbols.length).map((w, i) => ({ symbol: symbols[i], weightPct: microToPct(w) }))
}

/** The draft against what instrument_master says: every symbol must resolve to ONE active
 *  instrument of the basket's kind. A non-fractionable name is allowed with a note — the
 *  book is paper, and `fractional_ready` is a flag in the plan, not a refusal. */
export function checkResolved(draft: ParsedDraft, resolved: ResolvedInstrument[]): Checked {
  const errors: string[] = []
  const notes: string[] = []
  const bySymbol = new Map<string, ResolvedInstrument[]>()
  for (const r of resolved) {
    const list = bySymbol.get(r.symbol) ?? []
    list.push(r)
    bySymbol.set(r.symbol, list)
  }
  const constituents: Constituent[] = []
  for (const row of draft.rows) {
    const hits = (bySymbol.get(row.symbol) ?? []).filter((h) => h.is_active)
    if (hits.length === 0) {
      errors.push(`${row.symbol}: not an active instrument on this board.`)
      continue
    }
    if (hits.length > 1) {
      errors.push(`${row.symbol}: resolves to ${hits.length} active instruments — the directory is inconsistent.`)
      continue
    }
    const hit = hits[0]
    if (hit.asset_class !== draft.kind) {
      errors.push(`${row.symbol} is ${hit.asset_class === 'etf' ? 'an ETF' : 'a stock'}; this is a ${draft.kind} basket.`)
      continue
    }
    if (hit.fractionable === false) notes.push(`${row.symbol} is not fractionable at the broker; the paper book holds it fractionally.`)
    constituents.push({ instrument_id: hit.instrument_id, symbol: hit.symbol, weight_frac: microToFrac(row.weightMicro) })
  }
  if (errors.length) return { ok: false, errors }
  return { ok: true, constituents, notes }
}
