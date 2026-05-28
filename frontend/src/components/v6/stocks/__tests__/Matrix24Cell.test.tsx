// frontend/src/components/v6/stocks/__tests__/Matrix24Cell.test.tsx
import { describe, it, expect } from 'vitest'
import { getCellVariant } from '../Matrix24Cell'

describe('getCellVariant', () => {
  // POS variants
  it('returns pos-strong for count >= 15, sign POS', () => {
    expect(getCellVariant(15, 'POS')).toBe('pos-strong')
    expect(getCellVariant(22, 'POS')).toBe('pos-strong')
    expect(getCellVariant(100, 'POS')).toBe('pos-strong')
  })

  it('returns pos for count 8-14, sign POS', () => {
    expect(getCellVariant(8, 'POS')).toBe('pos')
    expect(getCellVariant(12, 'POS')).toBe('pos')
    expect(getCellVariant(14, 'POS')).toBe('pos')
  })

  it('returns pos-weak for count 1-7, sign POS', () => {
    expect(getCellVariant(1, 'POS')).toBe('pos-weak')
    expect(getCellVariant(4, 'POS')).toBe('pos-weak')
    expect(getCellVariant(7, 'POS')).toBe('pos-weak')
  })

  // NEG variants
  it('returns neg-strong for count >= 15, sign NEG', () => {
    expect(getCellVariant(15, 'NEG')).toBe('neg-strong')
    expect(getCellVariant(28, 'NEG')).toBe('neg-strong')
  })

  it('returns neg for count 8-14, sign NEG', () => {
    expect(getCellVariant(8, 'NEG')).toBe('neg')
    expect(getCellVariant(11, 'NEG')).toBe('neg')
    expect(getCellVariant(14, 'NEG')).toBe('neg')
  })

  it('returns neg-weak for count 1-7, sign NEG', () => {
    expect(getCellVariant(1, 'NEG')).toBe('neg-weak')
    expect(getCellVariant(5, 'NEG')).toBe('neg-weak')
    expect(getCellVariant(7, 'NEG')).toBe('neg-weak')
  })

  // Empty
  it('returns empty for count = 0 regardless of sign', () => {
    expect(getCellVariant(0, 'POS')).toBe('empty')
    expect(getCellVariant(0, 'NEG')).toBe('empty')
  })

  // Boundary: exactly 15
  it('boundary: count=15 is strong, count=14 is normal', () => {
    expect(getCellVariant(15, 'POS')).toBe('pos-strong')
    expect(getCellVariant(14, 'POS')).toBe('pos')
    expect(getCellVariant(15, 'NEG')).toBe('neg-strong')
    expect(getCellVariant(14, 'NEG')).toBe('neg')
  })

  // Boundary: exactly 8
  it('boundary: count=8 is normal, count=7 is weak', () => {
    expect(getCellVariant(8, 'POS')).toBe('pos')
    expect(getCellVariant(7, 'POS')).toBe('pos-weak')
    expect(getCellVariant(8, 'NEG')).toBe('neg')
    expect(getCellVariant(7, 'NEG')).toBe('neg-weak')
  })
})
