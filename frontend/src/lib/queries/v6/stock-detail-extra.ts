// frontend/src/lib/queries/v6/stock-detail-extra.ts
//
// Extra queries for the redesigned stock detail page:
//   getConvictionWithSignals  — atlas_stock_conviction_daily row + contributing_signals JSONB
//   getSectorContextForStock  — sector_state + breadth + sector rank + stock rank in sector
//   getMarketRegime           — latest regime_state from atlas_market_regime_daily
//
// All return graceful nulls/empty on missing data so the page degrades cleanly.

import 'server-only'
import sql from '@/lib/db'
import type { ContributingSignal } from '@/components/v6/stock-detail/ConvictionDecompositionPanel'

// ─── Conviction with contributing_signals JSONB ───────────────────────────────

export interface ConvictionWithSignals {
  conviction_score: number | null
  confidence_label: string | null
  backing_ic: number | null
  tier: string | null
  signals: ContributingSignal[]
}

interface RawConvictionRow {
  conviction_score: string | null
  confidence_label: string | null
  backing_ic: string | null
  tier: string | null
  contributing_signals: unknown
}

function parseSignalsBlob(blob: unknown): ContributingSignal[] {
  if (!blob) return []
  // JSONB can come back as already-parsed object or as a string.
  let parsed: unknown = blob
  if (typeof blob === 'string') {
    try {
      parsed = JSON.parse(blob)
    } catch {
      return []
    }
  }
  if (!parsed || typeof parsed !== 'object') return []
  // Two known shapes:
  //  (1) Array of {name, weight, contribution}
  //  (2) Object map { signal_name: {weight, contribution} } or { signal_name: contribution }
  if (Array.isArray(parsed)) {
    return parsed.flatMap((s): ContributingSignal[] => {
      if (!s || typeof s !== 'object') return []
      const row = s as Record<string, unknown>
      const name = typeof row.name === 'string' ? row.name : null
      const weight = typeof row.weight === 'number' ? row.weight : typeof row.weight === 'string' ? parseFloat(row.weight) : null
      const contribution = typeof row.contribution === 'number' ? row.contribution : typeof row.contribution === 'string' ? parseFloat(row.contribution) : null
      if (!name || weight == null || contribution == null) return []
      return [{ name, weight, contribution }]
    })
  }
  const obj = parsed as Record<string, unknown>
  return Object.entries(obj).flatMap(([name, value]): ContributingSignal[] => {
    if (typeof value === 'number') return [{ name, weight: 1, contribution: value }]
    if (value && typeof value === 'object') {
      const v = value as Record<string, unknown>
      const weight = typeof v.weight === 'number' ? v.weight : typeof v.weight === 'string' ? parseFloat(v.weight) : 1
      const contribution = typeof v.contribution === 'number' ? v.contribution : typeof v.contribution === 'string' ? parseFloat(v.contribution) : null
      if (contribution == null) return []
      return [{ name, weight, contribution }]
    }
    return []
  })
}

function parseNum(v: string | null): number | null {
  if (v == null) return null
  const n = parseFloat(v)
  return Number.isNaN(n) ? null : n
}

export async function getConvictionWithSignals(instrumentId: string): Promise<ConvictionWithSignals | null> {
  try {
    const rows = await sql<RawConvictionRow[]>`
      SELECT
        conviction_score::text   AS conviction_score,
        confidence_label,
        backing_ic::text         AS backing_ic,
        tier,
        contributing_signals
      FROM foundation_staging.atlas_stock_conviction_daily
      WHERE instrument_id = ${instrumentId}::uuid
      ORDER BY date DESC
      LIMIT 1
    `
    if (rows.length === 0) return null
    const r = rows[0]
    return {
      conviction_score: parseNum(r.conviction_score),
      confidence_label: r.confidence_label,
      backing_ic: parseNum(r.backing_ic),
      tier: r.tier,
      signals: parseSignalsBlob(r.contributing_signals),
    }
  } catch {
    return null
  }
}

// ─── Sector context ───────────────────────────────────────────────────────────

export interface SectorContext {
  sector_state: string | null
  breadth: number | null
  sector_rank: number | null
  total_sectors: number | null
  stock_rank_in_sector: number | null
  sector_size: number | null
}

interface SectorContextRow {
  sector_state: string | null
  breadth: string | null
  sector_rank: string | null
  total_sectors: string | null
  stock_rank: string | null
  sector_size: string | null
}

export async function getSectorContextForStock(
  sectorName: string,
  instrumentId: string,
): Promise<SectorContext | null> {
  try {
    const rows = await sql<SectorContextRow[]>`
      WITH latest_sector_date AS (
        SELECT MAX(date) AS d FROM foundation_staging.atlas_sector_states_daily
      ),
      sector_today AS (
        -- bottomup_rs_3m_nifty500 lives on atlas_sector_metrics_daily, NOT on
        -- atlas_sector_states_daily. Selecting it from states threw, and the
        -- caller's catch swallowed it -> every stock showed "Sector state
        -- unavailable" despite sector_state being populated. Join for the rank.
        SELECT
          s.sector_name,
          s.sector_state,
          (s.participation_rs_pct::numeric / 100.0)::text AS breadth,
          ROW_NUMBER() OVER (ORDER BY m.bottomup_rs_3m_nifty500 DESC NULLS LAST)::text AS sector_rank,
          COUNT(*) OVER ()::text AS total_sectors
        FROM foundation_staging.atlas_sector_states_daily s
        LEFT JOIN foundation_staging.atlas_sector_metrics_daily m
          ON m.sector_name = s.sector_name AND m.date = s.date
        WHERE s.date = (SELECT d FROM latest_sector_date)
      ),
      latest_metric_date AS (
        SELECT MAX(date) AS d FROM foundation_staging.atlas_stock_metrics_daily
      ),
      stock_ranks AS (
        SELECT
          m.instrument_id,
          ROW_NUMBER() OVER (PARTITION BY u.sector ORDER BY m.rs_pctile_3m DESC NULLS LAST)::text AS stock_rank,
          COUNT(*) OVER (PARTITION BY u.sector)::text AS sector_size
        FROM foundation_staging.atlas_stock_metrics_daily m
        JOIN foundation_staging.instrument_master u ON u.instrument_id = m.instrument_id AND u.is_active
        WHERE m.date = (SELECT d FROM latest_metric_date) AND u.sector = ${sectorName}
      )
      SELECT
        st.sector_state, st.breadth, st.sector_rank, st.total_sectors,
        sr.stock_rank, sr.sector_size
      FROM sector_today st
      LEFT JOIN stock_ranks sr ON sr.instrument_id = ${instrumentId}::uuid
      WHERE st.sector_name = ${sectorName}
      LIMIT 1
    `
    if (rows.length === 0) return null
    const r = rows[0]
    return {
      sector_state: r.sector_state,
      breadth: parseNum(r.breadth),
      sector_rank: r.sector_rank ? parseInt(r.sector_rank, 10) : null,
      total_sectors: r.total_sectors ? parseInt(r.total_sectors, 10) : null,
      stock_rank_in_sector: r.stock_rank ? parseInt(r.stock_rank, 10) : null,
      sector_size: r.sector_size ? parseInt(r.sector_size, 10) : null,
    }
  } catch {
    return null
  }
}

// ─── Market regime ────────────────────────────────────────────────────────────

export async function getMarketRegime(): Promise<string | null> {
  try {
    const rows = await sql<{ regime_state: string | null }[]>`
      SELECT regime_state::text
      FROM foundation_staging.atlas_market_regime_daily
      ORDER BY date DESC
      LIMIT 1
    `
    return rows[0]?.regime_state ?? null
  } catch {
    return null
  }
}

// ─── Gate thresholds from atlas_thresholds ───────────────────────────────────
//
// Per CLAUDE.md "Methodology thresholds live in foundation_staging.atlas_thresholds, loaded
// via atlas.db.load_thresholds()". We mirror the backend convention so the
// frontend gate display stays consistent with the backend gate computation
// when thresholds are tuned in the DB.

export interface GateThresholds {
  /** RS percentile minimum — failure threshold for the strength gate. 0..1 scale. */
  rsPctileMinThreshold: number
  /** Extension maximum — failure threshold for the risk gate. 0..1 fraction. */
  extensionMaxThreshold: number
}

const DEFAULT_GATE_THRESHOLDS: GateThresholds = {
  rsPctileMinThreshold: 0.5,
  extensionMaxThreshold: 0.4,
}

export async function getGateThresholds(): Promise<GateThresholds> {
  try {
    const rows = await sql<{ key: string; value: string | null }[]>`
      SELECT key, value::text
      FROM foundation_staging.atlas_thresholds
      WHERE key IN ('rs_pctile_min_pct', 'risk_extension_high_min_pct')
    `
    const map = new Map(rows.map(r => [r.key, r.value]))
    const rsPctRaw = map.get('rs_pctile_min_pct')
    const extPctRaw = map.get('risk_extension_high_min_pct')
    // Values stored as whole-number percents (e.g. 40 = 40%). Convert to fraction.
    const rsPctileMinThreshold = rsPctRaw != null
      ? Number.parseFloat(rsPctRaw) / 100
      : DEFAULT_GATE_THRESHOLDS.rsPctileMinThreshold
    const extensionMaxThreshold = extPctRaw != null
      ? Number.parseFloat(extPctRaw) / 100
      : DEFAULT_GATE_THRESHOLDS.extensionMaxThreshold
    return {
      rsPctileMinThreshold: Number.isFinite(rsPctileMinThreshold) ? rsPctileMinThreshold : DEFAULT_GATE_THRESHOLDS.rsPctileMinThreshold,
      extensionMaxThreshold: Number.isFinite(extensionMaxThreshold) ? extensionMaxThreshold : DEFAULT_GATE_THRESHOLDS.extensionMaxThreshold,
    }
  } catch {
    return DEFAULT_GATE_THRESHOLDS
  }
}
