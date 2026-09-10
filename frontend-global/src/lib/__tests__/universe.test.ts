// src/lib/__tests__/universe.test.ts — the label a fund wears when the board will not rank it.
//
// The reason strings below are the ones build_universe_snapshot.py actually wrote: measured on
// the live board on 2026-09-10, atlas_global.universe_snapshot held 2,975 below_floor, 711
// leveraged, 184 too_few_observations and 40 inverse against 1,749 rows with no reason at all.
import { describe, expect, it } from 'vitest'
import { whyNotOffered } from '@/lib/universe'

describe('why a measured fund is not an offered one', () => {
  it('names every reason the producer writes today', () => {
    expect(whyNotOffered('below_floor')).toBe('below the liquidity floor')
    expect(whyNotOffered('leveraged')).toBe('geared')
    expect(whyNotOffered('inverse')).toBe('inverse')
    expect(whyNotOffered('too_few_observations')).toBe('too little history')
  })

  it('says nothing about a fund the universe admits', () => {
    expect(whyNotOffered(null)).toBeNull()
    expect(whyNotOffered(undefined)).toBeNull()
    expect(whyNotOffered('')).toBeNull()
  })

  it('shows a rule it has never seen rather than hiding it behind "other"', () => {
    // A reason added to the producer must reach the reader on the day it is added, unlabelled but
    // legible — the alternative is a fund that silently drops out of every ranking with no cause
    // printed anywhere on the board.
    expect(whyNotOffered('price_history_suspect')).toBe('price history suspect')
  })
})
