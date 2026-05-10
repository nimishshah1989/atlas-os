import { describe, it, expect } from 'vitest'
import { buildSegments } from '@/lib/state-segment-utils'

describe('buildSegments', () => {
  it('returns empty array for empty input', () => {
    expect(buildSegments([])).toEqual([])
  })

  it('returns single segment for uniform state', () => {
    const rows = [
      { date: new Date('2024-01-01'), state: 'Risk-On' },
      { date: new Date('2024-01-02'), state: 'Risk-On' },
      { date: new Date('2024-01-03'), state: 'Risk-On' },
    ]
    const result = buildSegments(rows)
    expect(result).toHaveLength(1)
    expect(result[0].state).toBe('Risk-On')
    expect(result[0].days).toBe(3)
  })

  it('splits on state change', () => {
    const rows = [
      { date: new Date('2024-01-01'), state: 'Risk-On' },
      { date: new Date('2024-01-02'), state: 'Risk-On' },
      { date: new Date('2024-01-03'), state: 'Cautious' },
      { date: new Date('2024-01-04'), state: 'Cautious' },
    ]
    const result = buildSegments(rows)
    expect(result).toHaveLength(2)
    expect(result[0].state).toBe('Risk-On')
    expect(result[0].days).toBe(2)
    expect(result[1].state).toBe('Cautious')
    expect(result[1].days).toBe(2)
  })

  it('total days across all segments equals input row count', () => {
    const rows = [
      { date: new Date('2024-01-01'), state: 'A' },
      { date: new Date('2024-01-02'), state: 'B' },
      { date: new Date('2024-01-03'), state: 'A' },
    ]
    const result = buildSegments(rows)
    const total = result.reduce((s, seg) => s + seg.days, 0)
    expect(total).toBe(rows.length)
  })

  it('startDate and endDate are set correctly', () => {
    const rows = [
      { date: new Date('2024-01-01'), state: 'Risk-On' },
      { date: new Date('2024-01-05'), state: 'Cautious' },
    ]
    const result = buildSegments(rows)
    expect(result[0].startDate).toEqual(new Date('2024-01-01'))
    expect(result[0].endDate).toEqual(new Date('2024-01-01'))
    expect(result[1].startDate).toEqual(new Date('2024-01-05'))
  })
})
