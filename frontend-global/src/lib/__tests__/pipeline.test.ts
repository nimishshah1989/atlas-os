// The catalogue's two contracts: every served table names a step that exists, and a step's colour
// follows its last run and its cadence. The runs below are shapes, not market data.
import { describe, expect, it } from 'vitest'
import { STEP_BY_KEY, STEPS, stepRag, TABLES } from '../pipeline'

describe('the catalogue', () => {
  it('names a real step for every served table', () => {
    for (const [table, t] of Object.entries(TABLES)) expect(STEP_BY_KEY[t.step], `${table} → ${t.step}`).toBeDefined()
  })
  it('gives every step a job, a consequence, and a stage', () => {
    for (const s of STEPS) {
      expect(s.does.length).toBeGreaterThan(40)
      expect(s.ifItFails.length).toBeGreaterThan(20)
    }
    expect(new Set(STEPS.map((s) => s.key)).size).toBe(STEPS.length)
  })
})

describe('a step’s colour', () => {
  const now = new Date('2026-09-11T03:00:00Z')
  const nightly = STEP_BY_KEY.ingest_prices
  const weekly = STEP_BY_KEY.ingest_nport
  const run = (status: string, hoursAgo: number) => ({
    status,
    started_at: new Date(now.getTime() - hoursAgo * 3_600_000),
    ended_at: new Date(now.getTime() - hoursAgo * 3_600_000),
  })

  it('is grey with no run, red on failure, amber while running', () => {
    expect(stepRag(nightly, undefined, now)).toBe('grey')
    expect(stepRag(nightly, run('failed', 2), now)).toBe('red')
    expect(stepRag(nightly, { ...run('running', 0), ended_at: null }, now)).toBe('amber')
  })
  it('is green inside the cadence window and amber outside it', () => {
    expect(stepRag(nightly, run('success', 2), now)).toBe('green')
    expect(stepRag(nightly, run('success', 40), now)).toBe('amber')
    expect(stepRag(weekly, run('success', 40), now)).toBe('green')
    expect(stepRag(weekly, run('success', 9 * 24), now)).toBe('amber')
  })
})
