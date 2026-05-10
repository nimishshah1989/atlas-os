import { describe, it, expect } from 'vitest'

function matrixQuadrant(rs: number, participation: number): string {
  const right = rs > 0
  const top   = participation > 0.5
  if (right && top)  return 'Leaders'
  if (!right && top) return 'Recovering'
  if (right && !top) return 'Narrowing'
  return 'Laggards'
}

function rrgQuadrant(rs: number, meanRS: number, momentum: number): string {
  const right = (rs - meanRS) > 0
  const top   = momentum > 0
  if (right && top)  return 'Leading'
  if (right && !top) return 'Weakening'
  if (!right && top) return 'Improving'
  return 'Lagging'
}

describe('matrixQuadrant', () => {
  it('classifies Leaders correctly', () => {
    expect(matrixQuadrant(0.1, 0.6)).toBe('Leaders')
  })
  it('classifies Recovering correctly', () => {
    expect(matrixQuadrant(-0.1, 0.6)).toBe('Recovering')
  })
  it('classifies Narrowing correctly', () => {
    expect(matrixQuadrant(0.1, 0.4)).toBe('Narrowing')
  })
  it('classifies Laggards correctly', () => {
    expect(matrixQuadrant(-0.1, 0.4)).toBe('Laggards')
  })
})

describe('rrgQuadrant', () => {
  it('classifies Leading correctly', () => {
    expect(rrgQuadrant(0.2, 0.1, 0.05)).toBe('Leading')
  })
  it('classifies Weakening correctly', () => {
    expect(rrgQuadrant(0.2, 0.1, -0.05)).toBe('Weakening')
  })
  it('classifies Improving correctly', () => {
    expect(rrgQuadrant(0.05, 0.1, 0.05)).toBe('Improving')
  })
  it('classifies Lagging correctly', () => {
    expect(rrgQuadrant(0.05, 0.1, -0.05)).toBe('Lagging')
  })
})
