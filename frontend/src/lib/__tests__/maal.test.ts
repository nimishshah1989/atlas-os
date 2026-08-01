// Fold + validation for the MaaL Process.
// RULE #0: the starting book below is the FM's REAL Multi Asset Alpha model portfolio
// as sent to the desk (Goldbees 10 · Silverbees 5 · Divis 8 · Jana 8 · Pharmabees 8 ·
// HDFCSML250 12 · PPL 8 · Nykaa 8 · Biocon 8 · Welspun 8 · Lloyds 8 · MO Realty 8 =
// 99% invested, 1% cash). Every symbol, name and sector below was resolved against
// atlas_foundation.instrument_master (2026-07-30) — nothing here is invented.
import { describe, it, expect } from 'vitest'

import {
  foldBook,
  validateCalls,
  cashPct,
  cashMovement,
  mondayOf,
  isoDate,
  round1,
  sellCandidates,
  atCapSymbols,
  instrumentHref,
  type BookPosition,
  type Call,
} from '../maal'

// The FM's real book, verbatim.
const REAL_BOOK: BookPosition[] = [
  { key: 'etf:GOLDBEES', symbol: 'GOLDBEES', name: 'NIPPON INDIA ETF GOLD BEES', sector: 'Gold', weightPct: 10 },
  { key: 'etf:SILVERBEES', symbol: 'SILVERBEES', name: 'NIPPON INDIA SILVER ETF', sector: 'Silver', weightPct: 5 },
  { key: 'stock:DIVISLAB', symbol: 'DIVISLAB', name: "Divi's Laboratories Limited", sector: 'Pharma', weightPct: 8 },
  { key: 'stock:JSFB', symbol: 'JSFB', name: 'Jana Small Finance Bank Limited', sector: 'Banking', weightPct: 8 },
  { key: 'etf:PHARMABEES', symbol: 'PHARMABEES', name: 'NIPPON INDIA NIFTY PHARMA ETF', sector: 'Pharma', weightPct: 8 },
  { key: 'etf:HDFCSML250', symbol: 'HDFCSML250', name: 'HDFC NIFTY SMALLCAP 250 ETF', sector: 'Broad Index', weightPct: 12 },
  { key: 'stock:PPLPHARMA', symbol: 'PPLPHARMA', name: 'Piramal Pharma Limited', sector: 'Pharma', weightPct: 8 },
  { key: 'stock:NYKAA', symbol: 'NYKAA', name: 'FSN E-Commerce Ventures Limited', sector: 'Digital', weightPct: 8 },
  { key: 'stock:BIOCON', symbol: 'BIOCON', name: 'Biocon Limited', sector: 'Pharma', weightPct: 8 },
  { key: 'stock:WELSPUNLIV', symbol: 'WELSPUNLIV', name: 'Welspun Living Limited', sector: 'Consumer Durables', weightPct: 8 },
  { key: 'stock:LLOYDSENGG', symbol: 'LLOYDSENGG', name: 'LLOYDS ENGINEERING WORKS LIMITED', sector: 'Capital Goods', weightPct: 8 },
  { key: 'etf:MOREALTY', symbol: 'MOREALTY', name: 'MOTILAL OSWAL NIFTY REALTY ETF', sector: 'Realty', weightPct: 8 },
]

const buy = (over: Partial<Call> & Pick<Call, 'key' | 'weightPct'>): Call => ({
  side: 'buy',
  symbol: over.key.split(':')[1],
  name: over.key.split(':')[1],
  sector: null,
  comment: 'weight of evidence attached',
  reasons: [],
  ...over,
})

const sell = (over: Partial<Call> & Pick<Call, 'key' | 'weightPct'>): Call => ({
  side: 'sell',
  symbol: over.key.split(':')[1],
  name: over.key.split(':')[1],
  sector: null,
  comment: '',
  reasons: ['Profit booking'],
  ...over,
})

const weightOf = (book: BookPosition[], key: string) => book.find((p) => p.key === key)?.weightPct

describe('instrumentHref — every ticker on the page is a link to its deep dive', () => {
  it('sends a stock to the stocks page', () => {
    expect(instrumentHref('stock:BIOCON')).toBe('/stocks/BIOCON')
  })

  it('sends an ETF to the ETFs page', () => {
    expect(instrumentHref('etf:GOLDBEES')).toBe('/etfs/GOLDBEES')
  })
})

describe('round1 — weights carry one decimal, which is all the desk needs', () => {
  it('keeps a weight that is already one decimal', () => {
    expect(round1(7.5)).toBe(7.5)
  })

  it('rounds a two-decimal entry to one', () => {
    expect(round1(7.46)).toBe(7.5)
    expect(round1(7.44)).toBe(7.4)
  })

  it('leaves whole numbers alone', () => {
    expect(round1(12)).toBe(12)
  })

  it('does not introduce float noise', () => {
    expect(round1(0.1 + 0.2)).toBe(0.3)
  })
})

describe('sellCandidates — everything the book actually holds is sellable', () => {
  it('offers every real holding, whatever the cap', () => {
    // The book is now the REAL portfolio, and the FM's rule is that whatever it holds
    // at the end of the week is sellable. Filtering would hide real positions from the
    // person deciding what to sell.
    expect(sellCandidates(REAL_BOOK, 12)).toHaveLength(REAL_BOOK.length)
  })

  it('offers every holding even when no cap has been set', () => {
    // Previously this returned nothing, which left the sell grid empty for any book
    // whose cap had not been configured yet.
    expect(sellCandidates(REAL_BOOK, 0)).toHaveLength(REAL_BOOK.length)
  })

  it('orders the heaviest position first', () => {
    const keys = sellCandidates(REAL_BOOK, 8).map((p) => p.symbol)
    expect(keys[0]).toBe('HDFCSML250')
    expect(keys[1]).toBe('GOLDBEES')
  })
})

describe('atCapSymbols — the cap highlights, it no longer filters', () => {
  it('flags nothing when no cap has been set', () => {
    expect(atCapSymbols(REAL_BOOK, 0)).toEqual([])
  })

  it('flags the position that is exactly at the cap', () => {
    // Leaders' cap is 12: HDFCSML250 sits exactly there.
    expect(atCapSymbols(REAL_BOOK, 12)).toEqual(['HDFCSML250'])
  })

  it('flags within 1% below the cap, not further', () => {
    // cap 9 => 8%+ qualifies (9-1); the 5% Silverbees must not.
    const flagged = atCapSymbols(REAL_BOOK, 9)
    expect(flagged).toContain('HDFCSML250') // 12, above cap
    expect(flagged).toContain('GOLDBEES') // 10, above cap
    expect(flagged).toContain('BIOCON') // 8, exactly cap-1
    expect(flagged).not.toContain('SILVERBEES') // 5, well under
  })
})

describe('isoDate — normalising what postgres hands back for a DATE column', () => {
  it('passes a plain YYYY-MM-DD string through', () => {
    expect(isoDate('1999-01-04')).toBe('1999-01-04')
  })

  it('keeps the calendar day of a Date object (String().slice() loses the year)', () => {
    expect(isoDate(new Date('1999-01-04T00:00:00Z'))).toBe('1999-01-04')
  })

  it('does not roll backwards for a timezone ahead of UTC', () => {
    expect(isoDate(new Date('2026-08-03T00:00:00Z'))).toBe('2026-08-03')
  })

  it('trims a full timestamp string to its date', () => {
    expect(isoDate('2026-08-03T18:30:00.000Z')).toBe('2026-08-03')
  })
})

describe('mondayOf — which week a report belongs to', () => {
  it('returns the same day for a Monday', () => {
    expect(mondayOf('2026-07-27')).toBe('2026-07-27')
  })

  it('returns the week that has started for a mid-week day', () => {
    expect(mondayOf('2026-07-29')).toBe('2026-07-27') // Wednesday
  })

  it('rolls a Friday draft forward to the Monday it is for', () => {
    // The FM drafts on Friday/Saturday for the Monday that follows.
    expect(mondayOf('2026-07-31')).toBe('2026-08-03') // Friday
    expect(mondayOf('2026-08-01')).toBe('2026-08-03') // Saturday
    expect(mondayOf('2026-08-02')).toBe('2026-08-03') // Sunday
  })

  it('crosses a month boundary correctly', () => {
    expect(mondayOf('2026-09-30')).toBe('2026-09-28') // Wednesday
  })
})

describe('cashPct', () => {
  it('reports the FM real book as 1% cash', () => {
    expect(cashPct(REAL_BOOK)).toBe(1)
  })

  it('reports an empty book as fully in cash', () => {
    expect(cashPct([])).toBe(100)
  })
})

describe('foldBook — buys SET the target weight', () => {
  it('sets a new name at its stated weight', () => {
    const out = foldBook(REAL_BOOK, [buy({ key: 'stock:CDSL', weightPct: 6 })])
    expect(weightOf(out, 'stock:CDSL')).toBe(6)
  })

  it('replaces the weight of an already-held name rather than adding to it', () => {
    // Divis is held at 8. A buy stated as 12 means "target 12", not 8+12.
    const out = foldBook(REAL_BOOK, [buy({ key: 'stock:DIVISLAB', weightPct: 12 })])
    expect(weightOf(out, 'stock:DIVISLAB')).toBe(12)
  })

  it('leaves every untouched position exactly as it was', () => {
    const out = foldBook(REAL_BOOK, [buy({ key: 'stock:CDSL', weightPct: 6 })])
    expect(weightOf(out, 'etf:HDFCSML250')).toBe(12)
    expect(weightOf(out, 'etf:GOLDBEES')).toBe(10)
  })
})

describe('foldBook — sells SUBTRACT the trimmed weight', () => {
  it('trims a position by the stated weight', () => {
    const out = foldBook(REAL_BOOK, [sell({ key: 'etf:HDFCSML250', weightPct: 4 })])
    expect(weightOf(out, 'etf:HDFCSML250')).toBe(8)
  })

  it('removes the position entirely when the full held weight is sold', () => {
    const out = foldBook(REAL_BOOK, [sell({ key: 'etf:GOLDBEES', weightPct: 10 })])
    expect(weightOf(out, 'etf:GOLDBEES')).toBeUndefined()
  })

  it('frees the sold weight into cash', () => {
    const out = foldBook(REAL_BOOK, [sell({ key: 'etf:GOLDBEES', weightPct: 10 })])
    expect(cashPct(out)).toBe(11)
  })
})

describe('foldBook — arithmetic is exact at 2 decimals', () => {
  it('does not drift when thirds are repeatedly trimmed', () => {
    // 8 → 7.67 → 7.34 → 7.01 in exact basis points; float folding drifts here.
    let book = REAL_BOOK
    for (let i = 0; i < 3; i++) book = foldBook(book, [sell({ key: 'stock:BIOCON', weightPct: 0.33 })])
    expect(weightOf(book, 'stock:BIOCON')).toBe(7.01)
  })

  it('exits at exactly zero when trims sum to the held weight', () => {
    let book = foldBook(REAL_BOOK, [sell({ key: 'stock:NYKAA', weightPct: 7.5 })])
    expect(weightOf(book, 'stock:NYKAA')).toBe(0.5)
    book = foldBook(book, [sell({ key: 'stock:NYKAA', weightPct: 0.5 })])
    expect(weightOf(book, 'stock:NYKAA')).toBeUndefined()
  })
})

describe('cashMovement — what the editor banner tells the FM', () => {
  it('reports gross sold and gross deployed, not just the net swing', () => {
    // Biocon held 8 → target 10 deploys 2. CDSL is new at 6, deploys 6.
    // Divis trims 4, Nykaa exits 8 — 12 freed. Cash: 1 + 12 - 8 = 5.
    const m = cashMovement(REAL_BOOK, [
      buy({ key: 'stock:BIOCON', weightPct: 10 }),
      buy({ key: 'stock:CDSL', weightPct: 6 }),
      sell({ key: 'stock:DIVISLAB', weightPct: 4 }),
      sell({ key: 'stock:NYKAA', weightPct: 8 }),
    ])
    expect(m.freed).toBe(12)
    expect(m.deployed).toBe(8)
    expect(m.before).toBe(1)
    expect(m.after).toBe(5)
  })

  it('counts a trim down of a held name as freeing cash, not deploying it', () => {
    // A "buy" stating a LOWER target than held is really a reduction.
    const m = cashMovement(REAL_BOOK, [buy({ key: 'etf:HDFCSML250', weightPct: 9 })])
    expect(m.deployed).toBe(0)
    expect(m.freed).toBe(3)
  })

  it('balances exactly when buys consume everything the sells free', () => {
    const m = cashMovement(REAL_BOOK, [
      sell({ key: 'etf:GOLDBEES', weightPct: 10 }),
      buy({ key: 'stock:CDSL', weightPct: 10 }),
    ])
    expect(m.freed).toBe(10)
    expect(m.deployed).toBe(10)
    expect(m.after).toBe(m.before)
  })
})

describe('validateCalls', () => {
  it('accepts a well-formed week', () => {
    expect(
      validateCalls(REAL_BOOK, [
        buy({ key: 'stock:CDSL', weightPct: 6 }),
        sell({ key: 'etf:GOLDBEES', weightPct: 10 }),
      ]),
    ).toEqual([])
  })

  it('rejects the same instrument on both sides', () => {
    const problems = validateCalls(REAL_BOOK, [
      buy({ key: 'stock:BIOCON', weightPct: 10 }),
      sell({ key: 'stock:BIOCON', weightPct: 8 }),
    ])
    expect(problems.map((p) => p.code)).toContain('both_sides')
    expect(problems[0].message).toContain('BIOCON')
  })

  it('rejects a sell larger than the position actually held', () => {
    const problems = validateCalls(REAL_BOOK, [sell({ key: 'stock:NYKAA', weightPct: 9 })])
    expect(problems.map((p) => p.code)).toEqual(['sell_exceeds_held'])
    expect(problems[0].message).toContain('8')
  })

  it('rejects a sell of something not held', () => {
    const problems = validateCalls(REAL_BOOK, [sell({ key: 'stock:ATHER', weightPct: 3 })])
    expect(problems.map((p) => p.code)).toEqual(['sell_not_held'])
  })

  it('rejects a week whose resulting book would exceed 100%', () => {
    // 99% invested + a 2% new name = 101%.
    const problems = validateCalls(REAL_BOOK, [buy({ key: 'stock:CDSL', weightPct: 2 })])
    expect(problems.map((p) => p.code)).toEqual(['over_allocated'])
  })

  it('allows a buy funded by a same-week sell', () => {
    expect(
      validateCalls(REAL_BOOK, [
        sell({ key: 'etf:GOLDBEES', weightPct: 10 }),
        buy({ key: 'stock:CDSL', weightPct: 10 }),
      ]),
    ).toEqual([])
  })

  it('rejects a buy with no rationale', () => {
    const problems = validateCalls(REAL_BOOK, [buy({ key: 'stock:CDSL', weightPct: 1, comment: '  ' })])
    expect(problems.map((p) => p.code)).toContain('missing_rationale')
  })

  it('rejects a sell with no reason ticked', () => {
    const problems = validateCalls(REAL_BOOK, [sell({ key: 'etf:GOLDBEES', weightPct: 10, reasons: [] })])
    expect(problems.map((p) => p.code)).toContain('missing_reason')
  })

  it('rejects a non-positive weight', () => {
    const problems = validateCalls(REAL_BOOK, [buy({ key: 'stock:CDSL', weightPct: 0 })])
    expect(problems.map((p) => p.code)).toContain('bad_weight')
  })

  it('rejects the same instrument listed twice on one side', () => {
    const problems = validateCalls(REAL_BOOK, [
      buy({ key: 'stock:CDSL', weightPct: 0.5 }),
      buy({ key: 'stock:CDSL', weightPct: 0.5 }),
    ])
    expect(problems.map((p) => p.code)).toContain('duplicate_instrument')
  })
})
