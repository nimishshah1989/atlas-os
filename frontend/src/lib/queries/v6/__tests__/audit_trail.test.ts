// frontend/src/lib/queries/v6/__tests__/audit_trail.test.ts
//
// 5 required test cases for audit_trail.ts:
//   1. Valid iid with active signal — full AuditTrail returned, all 7 sections
//      (section 6 always null as designed)
//   2. Valid iid no active cell — signal_call=null, cell_matches=[], rest populated
//   3. iid not in universe — universe.in_universe=false, query still completes
//   4. Specific as_of date in past — returns that date's snapshot
//   5. atlas_provenance_log empty — provenance=[] returned cleanly

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    cache: (fn: (...args: unknown[]) => unknown) => fn,
  }
})

// sqlMock: each call to sql`` returns whatever was queued via .mockResolvedValueOnce
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getAuditTrail, type AuditTrail } from '../audit_trail'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const IID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
const AS_OF = '2026-05-26'

// Section 1 — universe row (in-universe case)
const UNIVERSE_ROW = {
  instrument_id: IID,
  symbol: 'RELIANCE',
  sector: 'Energy',
  tier: 'Large',
  in_universe: true,
  universe_total: '727',
}

// Section 2 — conviction row
const CONVICTION_ROW = {
  cell_id: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
  cell_name: 'Large 12m POSITIVE',
  verdict: 'POSITIVE',
  confidence_unconditional: '0.6500',
  snapshot_date: AS_OF,
}

// Section 3 — signal call row (open)
const SIGNAL_CALL_ROW = {
  signal_call_id: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
  cell_id: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
  entry_date: '2026-05-20',
  entry_price: null,
  predicted_excess: '0.043000',
  rule_dsl: {
    operator: 'AND',
    conditions: [{ feature: 'log_med_tv_60d', gte: 16.5 }],
  },
}

// Section 4 — fired_predicates JSONB
const FIRED_PREDICATES = [
  {
    feature: 'log_med_tv_60d',
    op: '>=',
    threshold: 16.5,
    value: 16.92,
    satisfied: true,
  },
  {
    feature: 'volume_zscore_252d',
    op: '>=',
    threshold: 1.0,
    value: 1.14,
    satisfied: true,
  },
]

// Section 4 query row
const PREDICATES_ROW = {
  fired_predicates: FIRED_PREDICATES,
}

// Section 5 — regime rows (2 rows: current state 'Risk-On' for 3 days)
const REGIME_ROWS_STRIP = [
  { state: 'Risk-On', date: '2026-05-26' },
  { state: 'Risk-On', date: '2026-05-25' },
  { state: 'Risk-On', date: '2026-05-24' },
  { state: 'Elevated', date: '2026-05-23' },
]

const SIGNAL_REGIME_ROW = [{ cell_active_in_regime: true }]

// Section 7 — provenance row
const PROVENANCE_ROW = {
  run_id: 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
  output_table: 'atlas_scorecard_daily',
  actor: 'atlas.scorecard_writer',
  ts: '2026-05-25T08:47:08+05:30',
}

// ---------------------------------------------------------------------------
// Helper: queue mocks for all 6 queries in the standard full-data case.
// Order matches the Promise.all in getAuditTrail:
//   [0] resolveAsOf → atlas_conviction_daily MAX(snapshot_date) — only when as_of not provided
//   [1] fetchUniverse → atlas_universe_stocks
//   [2] fetchCellMatches → atlas_conviction_daily
//   [3] fetchSignalCall → atlas_signal_calls
//   [4] fetchPredicatesMet → atlas_conviction_daily.fired_predicates
//   [5a] fetchRegime → atlas_regime_daily strip
//   [5b] fetchRegime → atlas_signal_calls (cell_active_in_regime)
//   [6] fetchProvenance → atlas_provenance_log
// ---------------------------------------------------------------------------

function queueFullDataMocks() {
  // resolveAsOf is called first (sequentially), then Promise.all with 5+1 parallel queries
  // When as_of IS provided, resolveAsOf returns early without a DB call.
  // Queries fire in order: universe, cell_matches, signal_call, predicates, regime(×2), provenance
  sqlMock
    .mockResolvedValueOnce([UNIVERSE_ROW])           // fetchUniverse
    .mockResolvedValueOnce([CONVICTION_ROW])         // fetchCellMatches
    .mockResolvedValueOnce([SIGNAL_CALL_ROW])        // fetchSignalCall
    .mockResolvedValueOnce([PREDICATES_ROW])         // fetchPredicatesMet
    .mockResolvedValueOnce(REGIME_ROWS_STRIP)        // fetchRegime → regime strip
    .mockResolvedValueOnce(SIGNAL_REGIME_ROW)        // fetchRegime → signal_calls
    .mockResolvedValueOnce([PROVENANCE_ROW])         // fetchProvenance
}

// ---------------------------------------------------------------------------
// 1. Valid iid with active signal — full AuditTrail returned
// ---------------------------------------------------------------------------

describe('getAuditTrail — valid iid with active signal', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns complete AuditTrail with all 7 sections (section 6 null)', async () => {
    queueFullDataMocks()

    const result = await getAuditTrail(IID, AS_OF)

    expect(result).not.toBeNull()
    const trail = result as AuditTrail

    // Section 1
    expect(trail.universe.iid).toBe(IID)
    expect(trail.universe.in_universe).toBe(true)
    expect(trail.universe.universe_total).toBe(727)
    expect(trail.universe.cap_tier).toBe('Large')
    expect(trail.universe.sector).toBe('Energy')
    expect(trail.universe.as_of_date).toBe(AS_OF)

    // Section 2
    expect(trail.cell_matches).toHaveLength(1)
    expect(trail.cell_matches[0].action).toBe('POSITIVE')
    expect(trail.cell_matches[0].confidence_unconditional).toBe('0.6500')
    expect(trail.cell_matches[0].triggered_at).toBe(AS_OF)

    // Section 3
    expect(trail.signal_call).not.toBeNull()
    expect(trail.signal_call!.signal_call_id).toBe('dddddddd-dddd-dddd-dddd-dddddddddddd')
    expect(trail.signal_call!.entry_date).toBe('2026-05-20')
    expect(trail.signal_call!.predicted_excess).toBe('0.043000')
    expect(trail.signal_call!.rule_dsl).toEqual(SIGNAL_CALL_ROW.rule_dsl)

    // Section 4
    expect(trail.predicates_met).toHaveLength(2)
    expect(trail.predicates_met[0].predicate_text).toBe('log_med_tv_60d >= 16.5')
    expect(trail.predicates_met[0].actual_value).toBe('16.92')
    expect(trail.predicates_met[0].satisfied).toBe(true)
    expect(trail.predicates_met[0].translation).toContain('turnover')
    expect(trail.predicates_met[1].satisfied).toBe(true)

    // Section 5
    expect(trail.regime).not.toBeNull()
    expect(trail.regime!.state).toBe('Risk-On')
    expect(trail.regime!.days_in_regime).toBe(3)
    expect(trail.regime!.cell_active_in_regime).toBe(true)
    expect(trail.regime!.deployment_multiplier).toBe('1.0')

    // Section 6 — always null in v6.0
    expect(trail.cross_rule_check).toBeNull()

    // Section 7
    expect(trail.provenance).toHaveLength(1)
    expect(trail.provenance[0].table_name).toBe('atlas_scorecard_daily')
    expect(trail.provenance[0].source).toBe('atlas.scorecard_writer')
    expect(trail.provenance[0].run_id).toBe('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee')
  })
})

// ---------------------------------------------------------------------------
// 2. Valid iid, no active cell — signal_call=null, cell_matches=[]
// ---------------------------------------------------------------------------

describe('getAuditTrail — valid iid, no active cell', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns signal_call=null and cell_matches=[] when no active signal', async () => {
    sqlMock
      .mockResolvedValueOnce([UNIVERSE_ROW])   // fetchUniverse
      .mockResolvedValueOnce([])               // fetchCellMatches (empty)
      .mockResolvedValueOnce([])               // fetchSignalCall (empty)
      .mockResolvedValueOnce([])               // fetchPredicatesMet (empty)
      .mockResolvedValueOnce(REGIME_ROWS_STRIP) // fetchRegime strip
      .mockResolvedValueOnce([])               // fetchRegime signal_calls
      .mockResolvedValueOnce([])               // fetchProvenance (empty)

    const result = await getAuditTrail(IID, AS_OF)

    expect(result).not.toBeNull()
    const trail = result as AuditTrail

    expect(trail.universe.in_universe).toBe(true)
    expect(trail.cell_matches).toEqual([])
    expect(trail.signal_call).toBeNull()
    expect(trail.predicates_met).toEqual([])
    expect(trail.regime).not.toBeNull()
    expect(trail.regime!.cell_active_in_regime).toBe(true) // default when no signal row
    expect(trail.provenance).toEqual([])
    expect(trail.cross_rule_check).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 3. iid not in universe — universe.in_universe=false
// ---------------------------------------------------------------------------

describe('getAuditTrail — iid not in universe', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns in_universe=false but query still completes', async () => {
    // fetchUniverse uses a single LEFT JOIN query — returns one row with in_universe=false
    const NOT_IN_UNIVERSE_ROW = {
      instrument_id: IID,
      sector: 'Unknown',
      tier: 'Large',
      in_universe: false,
      universe_total: '727',
    }
    sqlMock
      .mockResolvedValueOnce([NOT_IN_UNIVERSE_ROW]) // fetchUniverse (single query)
      .mockResolvedValueOnce([])                    // fetchCellMatches
      .mockResolvedValueOnce([])                    // fetchSignalCall
      .mockResolvedValueOnce([])                    // fetchPredicatesMet
      .mockResolvedValueOnce([])                    // fetchRegime strip (empty)
      .mockResolvedValueOnce([])                    // fetchRegime signal_calls
      .mockResolvedValueOnce([])                    // fetchProvenance

    const result = await getAuditTrail(IID, AS_OF)

    expect(result).not.toBeNull()
    const trail = result as AuditTrail

    expect(trail.universe.in_universe).toBe(false)
    expect(trail.universe.iid).toBe(IID)
    expect(trail.universe.universe_total).toBe(727)
    expect(trail.universe.cap_tier).toBe('Large')  // default
    expect(trail.universe.sector).toBe('Unknown')  // default
    expect(trail.cross_rule_check).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 4. Specific as_of date in past — returns that date's snapshot
// ---------------------------------------------------------------------------

describe('getAuditTrail — specific as_of date in past', () => {
  beforeEach(() => sqlMock.mockReset())

  it('uses the provided as_of date rather than resolving latest', async () => {
    const PAST_DATE = '2026-03-15'
    const PAST_CONVICTION_ROW = {
      ...CONVICTION_ROW,
      snapshot_date: PAST_DATE,
      verdict: 'NEGATIVE',
    }

    sqlMock
      .mockResolvedValueOnce([UNIVERSE_ROW])
      .mockResolvedValueOnce([PAST_CONVICTION_ROW])
      .mockResolvedValueOnce([])               // no open signal call on that date
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { state: 'Risk-Off', date: PAST_DATE },
      ])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])

    const result = await getAuditTrail(IID, PAST_DATE)

    expect(result).not.toBeNull()
    const trail = result as AuditTrail

    // universe snapshot uses the provided date
    expect(trail.universe.as_of_date).toBe(PAST_DATE)
    // conviction verdict from that date
    expect(trail.cell_matches[0]?.action).toBe('NEGATIVE')
    // regime from that date
    expect(trail.regime?.state).toBe('Risk-Off')
    expect(trail.signal_call).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 5. atlas_provenance_log empty — provenance=[] returned cleanly
// ---------------------------------------------------------------------------

describe('getAuditTrail — provenance log empty', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns provenance=[] when atlas_provenance_log has no rows', async () => {
    sqlMock
      .mockResolvedValueOnce([UNIVERSE_ROW])
      .mockResolvedValueOnce([CONVICTION_ROW])
      .mockResolvedValueOnce([SIGNAL_CALL_ROW])
      .mockResolvedValueOnce([PREDICATES_ROW])
      .mockResolvedValueOnce(REGIME_ROWS_STRIP)
      .mockResolvedValueOnce(SIGNAL_REGIME_ROW)
      .mockResolvedValueOnce([])              // provenance log empty

    const result = await getAuditTrail(IID, AS_OF)

    expect(result).not.toBeNull()
    const trail = result as AuditTrail

    expect(trail.provenance).toEqual([])
    // rest of the audit trail is still populated
    expect(trail.universe.in_universe).toBe(true)
    expect(trail.cell_matches).toHaveLength(1)
    expect(trail.signal_call).not.toBeNull()
    expect(trail.regime).not.toBeNull()
    expect(trail.cross_rule_check).toBeNull()
  })
})
