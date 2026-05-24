import { describe, it, expect } from 'vitest'
import { ordinal } from '../ordinal'

describe('ordinal()', () => {
  it('1 → 1st', () => expect(ordinal(1)).toBe('1st'))
  it('2 → 2nd', () => expect(ordinal(2)).toBe('2nd'))
  it('3 → 3rd', () => expect(ordinal(3)).toBe('3rd'))
  it('4 → 4th', () => expect(ordinal(4)).toBe('4th'))
  it('11 → 11th (special case)', () => expect(ordinal(11)).toBe('11th'))
  it('12 → 12th (special case)', () => expect(ordinal(12)).toBe('12th'))
  it('13 → 13th (special case)', () => expect(ordinal(13)).toBe('13th'))
  it('21 → 21st', () => expect(ordinal(21)).toBe('21st'))
  it('22 → 22nd', () => expect(ordinal(22)).toBe('22nd'))
  it('23 → 23rd', () => expect(ordinal(23)).toBe('23rd'))
  it('52 → 52nd', () => expect(ordinal(52)).toBe('52nd'))
  it('53 → 53rd', () => expect(ordinal(53)).toBe('53rd'))
  it('100 → 100th', () => expect(ordinal(100)).toBe('100th'))
  it('101 → 101st', () => expect(ordinal(101)).toBe('101st'))
  it('111 → 111th (special case)', () => expect(ordinal(111)).toBe('111th'))
  it('112 → 112th (special case)', () => expect(ordinal(112)).toBe('112th'))
  it('113 → 113th (special case)', () => expect(ordinal(113)).toBe('113th'))
})
