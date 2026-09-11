// The draft is a set of symbols per kind in the browser. What is under test is the contract the
// tray and the "+" rely on: a toggle is a toggle, kinds never mix, the limit refuses rather than
// truncates, and a broken or absent store reads as empty rather than throwing.
import { beforeEach, describe, expect, it } from 'vitest'
import { clearDraft, DRAFT_LIMIT, draftHref, isInDraft, readDraft, toggleDraft, writeDraft } from '../basketTray'

beforeEach(() => localStorage.clear())

describe('the draft basket', () => {
  it('starts empty', () => {
    expect(readDraft()).toEqual({ etf: [], stock: [] })
  })

  it('adds on the first toggle and removes on the second', () => {
    expect(toggleDraft('etf', 'SPY').etf).toEqual(['SPY'])
    expect(isInDraft('etf', 'SPY')).toBe(true)
    expect(toggleDraft('etf', 'SPY').etf).toEqual([])
    expect(isInDraft('etf', 'SPY')).toBe(false)
  })

  it('keeps the two kinds apart — a basket is one kind or the other', () => {
    toggleDraft('etf', 'SPY')
    toggleDraft('stock', 'AAPL')
    expect(readDraft()).toEqual({ etf: ['SPY'], stock: ['AAPL'] })
    expect(clearDraft('etf')).toEqual({ etf: [], stock: ['AAPL'] })
  })

  it('keeps insertion order, so the builder opens the names in the order they were picked', () => {
    for (const s of ['IWM', 'SPY', 'QQQ']) toggleDraft('etf', s)
    expect(readDraft().etf).toEqual(['IWM', 'SPY', 'QQQ'])
  })

  it('refuses a name past the limit rather than dropping an earlier one', () => {
    for (let i = 0; i < DRAFT_LIMIT; i += 1) toggleDraft('etf', `E${i}`)
    expect(toggleDraft('etf', 'ONEMORE').etf).toHaveLength(DRAFT_LIMIT)
    expect(isInDraft('etf', 'ONEMORE')).toBe(false)
  })

  it('reads a corrupt store as empty and never throws', () => {
    localStorage.setItem('atlas-global:basket-draft', '{not json')
    expect(readDraft()).toEqual({ etf: [], stock: [] })
    localStorage.setItem('atlas-global:basket-draft', JSON.stringify({ etf: ['ok', 'SPY', 42, 'BRK.B'], stock: 'nope' }))
    // lower-case and non-strings are not symbols; BRK.B is
    expect(readDraft()).toEqual({ etf: ['SPY', 'BRK.B'], stock: [] })
  })

  it('opens the builder through the same ?symbols= door a theme page uses', () => {
    writeDraft({ etf: ['URA', 'NLR'], stock: [] })
    expect(draftHref('etf')).toBe('/portfolios/new?symbols=URA%2CNLR&kind=etf')
  })
})
