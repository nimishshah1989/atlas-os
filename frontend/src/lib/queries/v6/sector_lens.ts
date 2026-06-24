// src/lib/queries/v6/sector_lens.ts
// Native sector deep-dive lens data — all from foundation_staging:
//  - getSectorLensVector(): the 6-lens sector vector + breadth + dispersion (sector_lens_daily)
//  - getSectorStocks(): the sector's stocks with per-lens DECILES (cut within cap cohort,
//    universe-wide, the D27 way) + leadership badge + strength — feeds the 2x2s + within breadth
//  - getSectorFundamentals(): aggregate margins / D-E by sector vs the universe
//  - getSectorFundFlow(): delivery 30d/60d + up/down asymmetry + institutional flow by sector
import 'server-only'
import sql from '@/lib/db'

export type SectorLensVector = {
  technical: number | null; fundamental: number | null; valuation: number | null
  catalyst: number | null; flow: number | null; policy: number | null
  breadth_technical: number | null; breadth_fundamental: number | null; breadth_flow: number | null
  dispersion: number | null; n_constituents: number | null
}

export async function getSectorLensVector(sector: string): Promise<SectorLensVector | null> {
  const r = await sql<Record<string, string>[]>`
    SELECT technical, fundamental, valuation, catalyst, flow, policy,
           breadth_technical, breadth_fundamental, breadth_flow, dispersion, n_constituents
    FROM foundation_staging.sector_lens_daily
    WHERE sector = ${sector} ORDER BY date DESC LIMIT 1
  `
  if (r.length === 0) return null
  const n = (v: string | null) => (v == null ? null : Number(v))
  const x = r[0]
  return {
    technical: n(x.technical), fundamental: n(x.fundamental), valuation: n(x.valuation),
    catalyst: n(x.catalyst), flow: n(x.flow), policy: n(x.policy),
    breadth_technical: n(x.breadth_technical), breadth_fundamental: n(x.breadth_fundamental),
    breadth_flow: n(x.breadth_flow), dispersion: n(x.dispersion),
    n_constituents: x.n_constituents == null ? null : Number(x.n_constituents),
  }
}

export type SectorStock = {
  symbol: string; name: string | null; cap: string
  d_tech: number | null; d_fund: number | null; d_cat: number | null; d_flow: number | null; d_val: number | null
  lead: number; strength: number | null
}

// Deciles cut WITHIN cap cohort across the whole universe (D27), then filtered to the sector.
// ntile partitions by (cap, score-is-null) so nulls form their own bucket and are nulled out.
// The cohort is the FULL cap universe (no sector filter on `j`) so a stock's decile is identical
// here and on the /stocks list + detail; the sector filter is applied after ntile (final WHERE).
export async function getSectorStocks(sector: string): Promise<SectorStock[]> {
  const rows = await sql<Record<string, string>[]>`
    WITH latest AS (
      SELECT max(date) d FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'
    ),
    cap AS (
      SELECT instrument_id,
        CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
             WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
             WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
      FROM foundation_staging.de_index_constituents
      WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
      GROUP BY instrument_id
    ),
    j AS (
      SELECT l.instrument_id, im.symbol, im.name, im.sector, COALESCE(c.cap,'micro') AS cap,
             l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va
      FROM foundation_staging.atlas_lens_scores_daily l
      JOIN foundation_staging.instrument_master im ON im.instrument_id = l.instrument_id
      LEFT JOIN cap c ON c.instrument_id = l.instrument_id
      WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest)
    ),
    dec AS (
      SELECT symbol, name, sector, cap, t, f, ca, fl, va,
        CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_tech,
        CASE WHEN f  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(f  IS NULL) ORDER BY f)  END d_fund,
        CASE WHEN ca IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(ca IS NULL) ORDER BY ca) END d_cat,
        CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow,
        CASE WHEN va IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(va IS NULL) ORDER BY va) END d_val
      FROM j
    )
    SELECT symbol, name, cap, d_tech, d_fund, d_cat, d_flow, d_val,
      (COALESCE((d_tech=10)::int,0) + COALESCE((d_fund=10)::int,0) + COALESCE((d_cat=10)::int,0) + COALESCE((d_flow=10)::int,0)) AS lead,
      ((COALESCE(d_tech,0)+COALESCE(d_fund,0)+COALESCE(d_cat,0)+COALESCE(d_flow,0))::float
        / NULLIF((d_tech IS NOT NULL)::int+(d_fund IS NOT NULL)::int+(d_cat IS NOT NULL)::int+(d_flow IS NOT NULL)::int,0)) AS strength
    FROM dec WHERE sector = ${sector}
    ORDER BY strength DESC NULLS LAST
  `
  const n = (v: string | null) => (v == null ? null : Number(v))
  return rows.map(r => ({
    symbol: r.symbol, name: r.name, cap: r.cap,
    d_tech: n(r.d_tech), d_fund: n(r.d_fund), d_cat: n(r.d_cat), d_flow: n(r.d_flow), d_val: n(r.d_val),
    lead: Number(r.lead ?? 0), strength: n(r.strength),
  }))
}

export type SectorFundamentals = {
  n: number; ebitda_margin: number | null; net_margin: number | null; debt_equity: number | null
  u_ebitda_margin: number | null; u_net_margin: number | null; u_debt_equity: number | null
}

export async function getSectorFundamentals(sector: string): Promise<SectorFundamentals | null> {
  const r = await sql<Record<string, string>[]>`
    WITH latest_fin AS (
      SELECT DISTINCT ON (fq.instrument_id) fq.instrument_id,
             fq.ebitda_margin::float em, fq.net_margin::float nm, fq.debt_equity_ratio::float de
      FROM foundation_staging.financials_quarterly fq
      WHERE fq.consolidated ORDER BY fq.instrument_id, fq.period_end DESC
    ),
    joined AS (
      SELECT im.sector, lf.em, lf.nm, lf.de
      FROM foundation_staging.instrument_master im JOIN latest_fin lf ON lf.instrument_id = im.instrument_id
      WHERE im.asset_class='stock' AND im.sector IS NOT NULL
    )
    SELECT
      count(*) FILTER (WHERE sector = ${sector}) AS n,
      avg(em) FILTER (WHERE sector = ${sector}) AS ebitda_margin,
      avg(nm) FILTER (WHERE sector = ${sector}) AS net_margin,
      avg(de) FILTER (WHERE sector = ${sector}) AS debt_equity,
      avg(em) AS u_ebitda_margin, avg(nm) AS u_net_margin, avg(de) AS u_debt_equity
    FROM joined
  `
  if (r.length === 0 || Number(r[0].n) === 0) return null
  const n = (v: string | null) => (v == null ? null : Number(v))
  const x = r[0]
  return {
    n: Number(x.n), ebitda_margin: n(x.ebitda_margin), net_margin: n(x.net_margin), debt_equity: n(x.debt_equity),
    u_ebitda_margin: n(x.u_ebitda_margin), u_net_margin: n(x.u_net_margin), u_debt_equity: n(x.u_debt_equity),
  }
}

export type SectorFundFlow = {
  n: number; deliv_30d: number | null; deliv_60d: number | null; updown: number | null; flow_inst: number | null
  u_deliv_30d: number | null; u_updown: number | null
}

export async function getSectorFundFlow(sector: string): Promise<SectorFundFlow | null> {
  const r = await sql<Record<string, string>[]>`
    WITH dl AS (SELECT max(date) d FROM foundation_staging.delivery_daily),
    jl AS (SELECT max(date) d FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'),
    joined AS (
      SELECT im.sector, d.delivery_avg_30d::float a30, d.delivery_avg_60d::float a60,
             d.delivery_updown_asym::float ud, l.flow_institutional::float fi
      FROM foundation_staging.instrument_master im
      JOIN foundation_staging.delivery_daily d ON d.instrument_id = im.instrument_id AND d.date=(SELECT d FROM dl)
      LEFT JOIN foundation_staging.atlas_lens_scores_daily l
        ON l.instrument_id = im.instrument_id AND l.date=(SELECT d FROM jl) AND l.asset_class='stock'
      WHERE im.asset_class='stock' AND im.sector IS NOT NULL
    )
    SELECT
      count(*) FILTER (WHERE sector = ${sector}) AS n,
      avg(a30) FILTER (WHERE sector = ${sector}) AS deliv_30d,
      avg(a60) FILTER (WHERE sector = ${sector}) AS deliv_60d,
      avg(ud)  FILTER (WHERE sector = ${sector}) AS updown,
      avg(fi)  FILTER (WHERE sector = ${sector}) AS flow_inst,
      avg(a30) AS u_deliv_30d, avg(ud) AS u_updown
    FROM joined
  `
  if (r.length === 0 || Number(r[0].n) === 0) return null
  const n = (v: string | null) => (v == null ? null : Number(v))
  const x = r[0]
  return {
    n: Number(x.n), deliv_30d: n(x.deliv_30d), deliv_60d: n(x.deliv_60d), updown: n(x.updown),
    flow_inst: n(x.flow_inst), u_deliv_30d: n(x.u_deliv_30d), u_updown: n(x.u_updown),
  }
}
