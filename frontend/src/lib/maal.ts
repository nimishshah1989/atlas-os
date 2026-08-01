// The weekly model-portfolio book: how a Monday confirmation changes it, and what
// makes one publishable. Pure — the DB layer applies these at publish and stores
// the result; nothing is re-derived at read time.
//
// Weights fold in integer basis points: postgres returns numeric as strings and
// float percentages drift over months of trims (0.1 + 0.2 !== 0.3).

export const MAAL_CODES = ['leaders', 'passive', 'ind11'] as const
export type MaalCode = (typeof MAAL_CODES)[number]

export const MAAL_NAMES: Record<MaalCode, string> = {
  leaders: 'Multi Asset Alpha - Leaders',
  passive: 'Passive',
  ind11: 'India XI',
}

export const SELL_REASONS = ['Full size filled', 'Profit booking', 'Potential loss booking'] as const

export type BookPosition = {
  key: string // "stock:SYMBOL" | "etf:SYMBOL" — the search route's hit key
  symbol: string
  name: string
  sector: string | null
  weightPct: number
}

export type Call = {
  side: 'buy' | 'sell'
  key: string
  symbol: string
  name: string
  sector: string | null
  weightPct: number
  comment: string
  reasons: string[]
}

export type Problem = { code: string; message: string }

/**
 * Weights carry one decimal — the desk sizes in halves and whole percents, so a
 * second decimal is noise the FM has to read past. Applied server-side at save, so
 * what is stored and what is displayed can never disagree.
 */
export function round1(pct: number): number {
  return Math.round(pct * 10) / 10
}

/** Deep-dive page for a holding — no ticker on the board is dead text. */
export function instrumentHref(key: string): string {
  const [cls, symbol] = key.split(':')
  return cls === 'etf' ? `/etfs/${symbol}` : `/stocks/${symbol}`
}

/** How far below the cap a position still counts as maxed out (FM, 2026-07-30). */
export const CAP_TOLERANCE_PCT = 1

/**
 * The holdings that pre-fill the sell side: EVERY position the book actually holds,
 * heaviest first.
 *
 * It used to be only the cap-maxed names. That made sense when the book was a fold of
 * recommendations, but the book is now the real portfolio — and the FM's rule is that
 * whatever the portfolio holds at the end of the week is sellable. Filtering the list
 * would hide real positions from the person deciding what to sell. Cap-maxed names are
 * still surfaced, via atCapSymbols(), as a highlight rather than a filter.
 *
 * capPct is retained in the signature so callers need not change; the cap now drives
 * the highlight, not the list.
 */
export function sellCandidates(book: BookPosition[], _capPct: number): BookPosition[] {
  return [...book].sort(
    (a, b) => b.weightPct - a.weightPct || a.symbol.localeCompare(b.symbol),
  )
}

/**
 * Positions at, above, or within CAP_TOLERANCE_PCT of the book's max cap — highlighted
 * in the sell grid, not used to filter it. A capped position can only come down, so it
 * is a standing sell candidate worth drawing the eye to. A cap of 0 means "no cap set",
 * so nothing is flagged.
 */
export function atCapSymbols(book: BookPosition[], capPct: number): string[] {
  if (!(capPct > 0)) return []
  const floor = bps(capPct - CAP_TOLERANCE_PCT)
  return book.filter((p) => bps(p.weightPct) >= floor).map((p) => p.symbol)
}

/**
 * Normalise a DATE column to YYYY-MM-DD. postgres.js hands back a Date object,
 * and `String(date).slice(0, 10)` yields "Mon Jan 04" — which re-parses to the
 * wrong year. Always go through the UTC components.
 */
export function isoDate(v: Date | string): string {
  if (v instanceof Date) return v.toISOString().slice(0, 10)
  return v.slice(0, 10)
}

/**
 * The Monday a given day's report belongs to. Mon-Thu belong to the week already
 * running; Fri/Sat/Sun roll forward, because a Friday draft is for the Monday
 * that follows it. Date-only arithmetic in UTC — no timezone drift.
 */
export function mondayOf(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`)
  const dow = d.getUTCDay() // 0 Sun … 6 Sat
  const shift = dow === 0 ? 1 : dow >= 5 ? 8 - dow : 1 - dow
  d.setUTCDate(d.getUTCDate() + shift)
  return d.toISOString().slice(0, 10)
}

const bps = (p: number) => Math.round(p * 100)
const pct = (b: number) => b / 100

/** Invested weight left over as cash. Negative means over-allocated — validate first. */
export function cashPct(book: BookPosition[]): number {
  return pct(10000 - book.reduce((sum, p) => sum + bps(p.weightPct), 0))
}

/**
 * Apply one week's calls to the book. A buy SETS its instrument's target weight
 * (the FM states where the position should end up, not how much to add); a sell
 * SUBTRACTS the trimmed weight and drops the position when it reaches zero.
 */
export function foldBook(prior: BookPosition[], calls: Call[]): BookPosition[] {
  const held = new Map(prior.map((p) => [p.key, { ...p, weightPct: bps(p.weightPct) }]))

  for (const c of calls) {
    const existing = held.get(c.key)
    if (c.side === 'buy') {
      held.set(c.key, {
        key: c.key,
        symbol: c.symbol,
        name: c.name,
        sector: c.sector ?? existing?.sector ?? null,
        weightPct: bps(c.weightPct),
      })
      continue
    }
    if (!existing) continue
    const left = existing.weightPct - bps(c.weightPct)
    if (left <= 0) held.delete(c.key)
    else held.set(c.key, { ...existing, weightPct: left })
  }

  return [...held.values()]
    .map((p) => ({ ...p, weightPct: pct(p.weightPct) }))
    .sort((a, b) => b.weightPct - a.weightPct || a.symbol.localeCompare(b.symbol))
}

/**
 * Everything that would make this week unpublishable. Empty array = publishable.
 * Runs server-side at publish against the stored book, so a stale editor tab
 * cannot slip a sell past a position that is no longer there.
 */
export function validateCalls(prior: BookPosition[], calls: Call[]): Problem[] {
  const problems: Problem[] = []
  const held = new Map(prior.map((p) => [p.key, bps(p.weightPct)]))
  const seen = new Set<string>()
  const buys = new Set(calls.filter((c) => c.side === 'buy').map((c) => c.key))

  for (const c of calls) {
    const at = c.symbol
    // Per side: the same name twice on one side is a slip; on both sides it is
    // the both_sides violation below, which is the more useful thing to say.
    if (seen.has(`${c.side}:${c.key}`)) {
      problems.push({ code: 'duplicate_instrument', message: `${at} is listed twice on the ${c.side} side` })
      continue
    }
    seen.add(`${c.side}:${c.key}`)

    if (c.side === 'sell' && buys.has(c.key)) {
      problems.push({ code: 'both_sides', message: `${at} is on both the buy and the sell side` })
    }
    if (!(c.weightPct > 0)) {
      problems.push({ code: 'bad_weight', message: `${at} needs a weight above 0%` })
    }
    if (c.side === 'buy' && c.comment.trim() === '') {
      problems.push({ code: 'missing_rationale', message: `${at} needs a rationale` })
    }
    if (c.side === 'sell') {
      if (c.reasons.length === 0) {
        problems.push({ code: 'missing_reason', message: `${at} needs at least one reason` })
      }
      const heldBps = held.get(c.key)
      if (heldBps === undefined) {
        problems.push({ code: 'sell_not_held', message: `${at} is not in the portfolio` })
      } else if (bps(c.weightPct) > heldBps) {
        problems.push({
          code: 'sell_exceeds_held',
          message: `${at} sell of ${c.weightPct}% exceeds the ${pct(heldBps)}% held`,
        })
      }
    }
  }

  if (problems.length === 0) {
    const cash = cashPct(foldBook(prior, calls))
    if (cash < 0) {
      problems.push({
        code: 'over_allocated',
        message: `the resulting book would be ${(100 - cash).toFixed(2)}% invested — over 100%`,
      })
    }
  }
  return problems
}

/**
 * What the editor banner narrates: where the cash goes this week. `freed` and
 * `deployed` are GROSS — a week that sells 12% and redeploys 8% must read that
 * way, not as a bare 4% net swing. A buy stating a lower target than currently
 * held is a reduction, so it frees rather than deploys.
 */
export function cashMovement(prior: BookPosition[], calls: Call[]) {
  const held = new Map(prior.map((p) => [p.key, bps(p.weightPct)]))
  let freedBps = 0
  let deployedBps = 0

  for (const c of calls) {
    const now = held.get(c.key) ?? 0
    if (c.side === 'sell') {
      freedBps += Math.min(bps(c.weightPct), now)
      continue
    }
    const delta = bps(c.weightPct) - now
    if (delta >= 0) deployedBps += delta
    else freedBps += -delta
  }

  return {
    before: cashPct(prior),
    after: cashPct(foldBook(prior, calls)),
    freed: pct(freedBps),
    deployed: pct(deployedBps),
  }
}
