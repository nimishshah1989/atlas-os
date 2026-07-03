// frontend/src/lib/queries/sector_index_rs.ts
//
// Index-level sector returns for the market-pulse relative-return grid and the
// 1-day column on the sectors heatmap (Page 04).
//
// Unlike mv_sector_cards (bottom-up, constituent-aggregated returns starting at
// 1W), this reads the NSE *sector index* directly so we get a true 1-day return
// and an apples-to-apples comparison against a base index.
//
// Source:
//   atlas_foundation.atlas_sector_master       — sector_name → primary_nse_index (active)
//   atlas_foundation.atlas_index_metrics_daily — index_code, ret_1d/1w/1m/3m/6m/12m (latest)
//
// Returns are decimal fractions (0.0034 = +0.34%), same convention as the rest
// of the v6 surface — multiply by 100 only at display time.
//
// Relative value (sector vs base) is computed in the client component so the
// base toggle (Nifty 50 / Nifty 500) needs no refetch.

import 'server-only'
import sql from '@/lib/db'
import { toNumber } from '@/lib/decimal'

// ── Types ───────────────────────────────────────────────────────────────────

export type RsWindow = '1d' | '1w' | '1m' | '3m' | '6m' | '12m'

export type WindowRet = {
  ret_1d: number | null
  ret_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
}

export type SectorIndexRet = {
  sector_name: string
  nse_index_code: string
  ret: WindowRet
}

export type BaseKey = 'NIFTY 50' | 'NIFTY 500'

export type SectorIndexRsPayload = {
  sectors: SectorIndexRet[]
  bases: Record<BaseKey, WindowRet>
  as_of: string | null
}

const ZERO_WINDOW: WindowRet = {
  ret_1d: null, ret_1w: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
}

// ── Query ───────────────────────────────────────────────────────────────────

type RawRow = {
  index_code: string
  sector_name: string | null
  ret_1d: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  date: string
}

function toWindow(r: RawRow): WindowRet {
  return {
    ret_1d: toNumber(r.ret_1d),
    ret_1w: toNumber(r.ret_1w),
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
  }
}

/**
 * Latest index-level returns for every active sector index, plus the two base
 * indices used for relative comparison — fetched in a single round trip.
 *
 * Rows with a sector_name are sector tiles (a sector index can join >1 sector,
 * e.g. Energy + Power both map to NIFTY ENERGY). Rows for the base indices are
 * always included; bases are read by index_code regardless of any sector join.
 */
export async function getSectorIndexRs(): Promise<SectorIndexRsPayload> {
  const rows = await sql<RawRow[]>`
    SELECT
      im.index_code,
      sm.sector_name,
      im.ret_1d::text,
      im.ret_1w::text,
      im.ret_1m::text,
      im.ret_3m::text,
      im.ret_6m::text,
      im.ret_12m::text,
      im.date::text
    FROM atlas_foundation.atlas_index_metrics_daily im
    LEFT JOIN atlas_foundation.atlas_sector_master sm
      ON sm.primary_nse_index = im.index_code
     AND sm.is_active = true
     AND LOWER(sm.sector_name) NOT LIKE '%conglomerate%'
    WHERE im.date = (SELECT MAX(date) FROM atlas_foundation.atlas_index_metrics_daily)
      AND (sm.sector_name IS NOT NULL OR im.index_code IN ('NIFTY 50', 'NIFTY 500'))
    ORDER BY sm.sector_name NULLS LAST
  `

  const baseByCode = new Map(
    rows
      .filter((r) => r.index_code === 'NIFTY 50' || r.index_code === 'NIFTY 500')
      .map((r) => [r.index_code, toWindow(r)]),
  )

  const sectors: SectorIndexRet[] = rows
    .filter((r) => r.sector_name != null)
    .map((r) => ({
      sector_name: r.sector_name as string,
      nse_index_code: r.index_code,
      ret: toWindow(r),
    }))

  return {
    sectors,
    bases: {
      'NIFTY 50': baseByCode.get('NIFTY 50') ?? ZERO_WINDOW,
      'NIFTY 500': baseByCode.get('NIFTY 500') ?? ZERO_WINDOW,
    },
    as_of: rows[0]?.date ?? null,
  }
}

// ── RS ratio series (sector index ÷ Nifty 50) ───────────────────────────────
//
// Powers the RS ratio charts on the sector detail page. Computed from raw daily
// index closes (public.de_index_prices) so it renders in our own TradingView
// Lightweight Charts — no dependency on TradingView's data-gated public widget.

export type RatioPoint = { time: string; value: number }

export type SectorRatioSeries = {
  sector_name: string
  index_code: string | null
  daily: RatioPoint[]
}

/**
 * Daily ratio series of a sector's NSE index divided by Nifty 50, full history.
 * Returns an empty series when the sector has no mapped index or no overlap.
 */
export async function getSectorRatioSeries(sectorName: string): Promise<SectorRatioSeries> {
  const rows = await sql<Array<{ date: string; index_code: string; ratio: string }>>`
    SELECT s.date::text AS date, s.index_code, (s.close / n.close)::text AS ratio
    FROM atlas_foundation.index_prices s
    JOIN atlas_foundation.index_prices n
      ON n.date = s.date AND n.index_code = 'NIFTY 50'
    WHERE s.index_code = (
      SELECT primary_nse_index FROM atlas_foundation.atlas_sector_master
      WHERE sector_name = ${sectorName} AND is_active = true
      LIMIT 1
    )
      AND n.close > 0
      AND s.close > 0
    ORDER BY s.date
  `

  return {
    sector_name: sectorName,
    index_code: rows[0]?.index_code ?? null,
    daily: rows
      .map((r) => ({ time: r.date, value: toNumber(r.ratio) }))
      .filter((p): p is RatioPoint => p.value != null && Number.isFinite(p.value)),
  }
}
