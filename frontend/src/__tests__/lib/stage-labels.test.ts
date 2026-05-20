// Tests for src/lib/stage-labels.ts
// Covers STAGE_LABEL map, INSTRUMENT_UNIVERSE_LABEL map,
// stageLabel() helper, instrumentUniverseLabel() helper.

import { describe, it, expect } from 'vitest'
import { stageLabel, instrumentUniverseLabel, STAGE_LABEL, INSTRUMENT_UNIVERSE_LABEL } from '@/lib/stage-labels'

describe('STAGE_LABEL map (A3)', () => {
  it('contains all expected stage keys', () => {
    expect(STAGE_LABEL.stage_1).toBe('Stage 1 Base')
    expect(STAGE_LABEL.stage_2a).toBe('Stage 2A')
    expect(STAGE_LABEL.stage_2b).toBe('Stage 2B')
    expect(STAGE_LABEL.stage_2c).toBe('Stage 2C')
    expect(STAGE_LABEL.stage_3).toBe('Stage 3 Top')
    expect(STAGE_LABEL.stage_4).toBe('Stage 4 Decline')
    expect(STAGE_LABEL.uninvestable).toBe('Uninvestable')
  })
})

describe('INSTRUMENT_UNIVERSE_LABEL map (A3)', () => {
  it('contains all expected universe keys', () => {
    expect(INSTRUMENT_UNIVERSE_LABEL.direct_equity).toBe('Direct Equity')
    expect(INSTRUMENT_UNIVERSE_LABEL.etf).toBe('ETF')
    expect(INSTRUMENT_UNIVERSE_LABEL.mutual_fund).toBe('Mutual Fund')
    expect(INSTRUMENT_UNIVERSE_LABEL.mixed).toBe('Mixed')
  })
})

describe('stageLabel() helper', () => {
  it('translates known stage strings', () => {
    expect(stageLabel('stage_1')).toBe('Stage 1 Base')
    expect(stageLabel('stage_4')).toBe('Stage 4 Decline')
    expect(stageLabel('uninvestable')).toBe('Uninvestable')
  })

  it('returns "—" for null/undefined', () => {
    expect(stageLabel(null)).toBe('—')
    expect(stageLabel(undefined)).toBe('—')
  })

  it('falls back to the raw string for unknown values', () => {
    expect(stageLabel('some_unknown_state')).toBe('some_unknown_state')
  })
})

describe('instrumentUniverseLabel() helper', () => {
  it('translates known universe strings', () => {
    expect(instrumentUniverseLabel('direct_equity')).toBe('Direct Equity')
    expect(instrumentUniverseLabel('mutual_fund')).toBe('Mutual Fund')
  })

  it('returns "—" for null/undefined', () => {
    expect(instrumentUniverseLabel(null)).toBe('—')
    expect(instrumentUniverseLabel(undefined)).toBe('—')
  })

  it('falls back to the raw string for unknown values', () => {
    expect(instrumentUniverseLabel('some_universe')).toBe('some_universe')
  })
})
