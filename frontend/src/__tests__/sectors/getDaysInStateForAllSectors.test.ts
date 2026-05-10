import { describe, it, expect, vi } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({
  default: vi.fn(),
}))

import { type DaysInStateRow } from '@/lib/queries/sectors'

describe('DaysInStateRow shape', () => {
  it('type has sector_name and days_in_state fields', () => {
    const row: DaysInStateRow = { sector_name: 'Banking', days_in_state: 45 }
    expect(row.sector_name).toBe('Banking')
    expect(row.days_in_state).toBe(45)
  })
})
