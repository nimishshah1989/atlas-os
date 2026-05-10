import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({
  default: vi.fn(),
}))

import { type PlaybookEntry } from '@/lib/queries/sectors'

describe('PlaybookEntry shape', () => {
  it('has required fields', () => {
    const entry: PlaybookEntry = {
      event_id: 'covid-crash-2020',
      event_label: 'COVID',
      event_description: 'COVID-19 crash',
      start_date: '2020-02-20',
      end_date: '2020-03-23',
      leaders: [{ sector_name: 'Pharma', avg_rs: 0.12 }],
      laggards: [{ sector_name: 'Banking', avg_rs: -0.08 }],
    }
    expect(entry.event_id).toBe('covid-crash-2020')
    expect(entry.leaders[0].sector_name).toBe('Pharma')
    expect(entry.laggards[0].avg_rs).toBe(-0.08)
  })

  it('leaders and laggards are arrays', () => {
    const entry: PlaybookEntry = {
      event_id: 'x', event_label: 'X', event_description: 'X',
      start_date: '2020-01-01', end_date: '2020-01-31',
      leaders: [], laggards: [],
    }
    expect(Array.isArray(entry.leaders)).toBe(true)
    expect(Array.isArray(entry.laggards)).toBe(true)
  })
})
