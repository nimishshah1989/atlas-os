import { describe, it, expect } from 'vitest'
import {
  formatIC,
  formatICSigned,
  formatQ,
  formatFricAdj,
  formatGatePass,
  icTier,
  icTierClasses,
  buildCellId,
  parseCellId,
} from '../format-cell'

describe('format-cell helpers', () => {
  describe('formatIC', () => {
    it('renders 3-decimal magnitude', () => {
      expect(formatIC(0.05823)).toBe('0.058')
      expect(formatIC(-0.05823)).toBe('-0.058')
    })
    it('returns em-dash for null/NaN', () => {
      expect(formatIC(null)).toBe('—')
      expect(formatIC(undefined)).toBe('—')
      expect(formatIC(NaN)).toBe('—')
    })
  })

  describe('formatICSigned', () => {
    it('adds + sign to positives', () => {
      expect(formatICSigned(0.058)).toBe('+0.058')
      expect(formatICSigned(-0.058)).toBe('-0.058')
    })
  })

  describe('formatFricAdj', () => {
    it('renders signed percent with 1 decimal', () => {
      expect(formatFricAdj(0.148)).toBe('+14.8%')
      expect(formatFricAdj(-0.024)).toBe('-2.4%')
      expect(formatFricAdj(null)).toBe('—')
    })
  })

  describe('formatGatePass', () => {
    it('renders fraction', () => {
      expect(formatGatePass(8, 12)).toBe('8 / 12')
    })
    it('em-dash if either side is null', () => {
      expect(formatGatePass(null, 12)).toBe('—')
      expect(formatGatePass(8, null)).toBe('—')
    })
  })

  describe('formatQ', () => {
    it('renders 3 decimals', () => {
      expect(formatQ(0.0123)).toBe('0.012')
    })
  })

  describe('icTier', () => {
    it('classifies by IC magnitude', () => {
      expect(icTier(0.06)).toBe('high')
      expect(icTier(0.03)).toBe('mid')
      expect(icTier(0.01)).toBe('low')
      expect(icTier(-0.05)).toBe('neg')
      expect(icTier(null)).toBe('empty')
    })
  })

  describe('icTierClasses', () => {
    it('returns a non-empty class bundle for every tier', () => {
      for (const t of ['high', 'mid', 'low', 'neg', 'empty'] as const) {
        expect(icTierClasses(t).length).toBeGreaterThan(10)
      }
    })
  })

  describe('cell id round-trip', () => {
    it('builds and parses cleanly', () => {
      const id = buildCellId('Large', '3m', 'POSITIVE')
      expect(id).toBe('Large-3m-POSITIVE')
      const parsed = parseCellId(id)
      expect(parsed).toEqual({ tier: 'Large', tenure: '3m', direction: 'POSITIVE' })
    })
    it('returns null for malformed input', () => {
      expect(parseCellId('garbage')).toBeNull()
      expect(parseCellId('Large-3m')).toBeNull()
      expect(parseCellId('XL-3m-POSITIVE')).toBeNull()
    })
  })
})
