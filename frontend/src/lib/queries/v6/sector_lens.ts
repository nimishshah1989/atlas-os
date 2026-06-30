// src/lib/queries/v6/sector_lens.ts
// Native sector deep-dive lens data — all from foundation_staging:
//  - getSectorLensVector(): the 6-lens sector vector + breadth + dispersion (sector_lens_daily)
//  - getSectorStocks(): the sector's stocks with per-lens DECILES (cut within cap cohort,
//    universe-wide, the D27 way) + leadership badge + strength — feeds the 2x2s + within breadth
//  - getSectorFundamentals(): aggregate margins / D-E by sector vs the universe
//  - getSectorFundFlow(): delivery 30d/60d + up/down asymmetry + institutional flow by sector
import 'server-only'
import sql from '@/lib/db'
import { LEAD_DECILE } from '@/lib/queries/v6/stock_lens'
import { aggregateMargins, perConstituentMargins, type RawFin, type ConstituentFin } from '@/lib/v6/sectorFin'

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

// All sectors' lens vectors at the latest date, keyed by sector — for the /sectors scores table.
export async function getAllSectorLensVectors(): Promise<Record<string, SectorLensVector>> {
  const rows = await sql<Record<string, string>[]>`
    SELECT sector, technical, fundamental, valuation, catalyst, flow, policy,
           breadth_technical, breadth_fundamental, breadth_flow, dispersion, n_constituents
    FROM foundation_staging.sector_lens_daily
    WHERE date = (SELECT max(date) FROM foundation_staging.sector_lens_daily)
  `
  const n = (v: string | null) => (v == null ? null : Number(v))
  const out: Record<string, SectorLensVector> = {}
  for (const x of rows) {
    out[x.sector] = {
      technical: n(x.technical), fundamental: n(x.fundamental), valuation: n(x.valuation),
      catalyst: n(x.catalyst), flow: n(x.flow), policy: n(x.policy),
      breadth_technical: n(x.breadth_technical), breadth_fundamental: n(x.breadth_fundamental),
      breadth_flow: n(x.breadth_flow), dispersion: n(x.dispersion),
      n_constituents: x.n_constituents == null ? null : Number(x.n_constituents),
    }
  }
  return out
}

export type SectorStock = {
  symbol: string; name: string | null; cap: string
  d_tech: number | null; d_fund: number | null; d_cat: number | null; d_flow: number | null; d_val: number | null
  lead: number; strength: number | null
  ret_1d: number | null; ret_1w: number | null; ret_1m: number | null
  ret_3m: number | null; ret_6m: number | null; ret_12m: number | null
  rs_1m: number | null; rs_3m: number | null; rs_6m: number | null; rs_sector_3m: number | null
  liq_cr: number | null
  ff_weight: number | null // free-float weight within the sector (% of sector free-float market cap)
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
    sec_ret AS (  -- each sector's own NSE-index 3M return → real RS-vs-sector (stock 3M − sector-index 3M)
      SELECT sm.sector_name, max(aim.ret_3m::float) AS sret_3m
      FROM foundation_staging.atlas_sector_master sm
      JOIN foundation_staging.atlas_index_metrics_daily aim
        ON aim.index_code = sm.primary_nse_index
       AND aim.date = (SELECT max(date) FROM foundation_staging.atlas_index_metrics_daily)
      WHERE sm.is_active = true
      GROUP BY sm.sector_name
    ),
    liq AS (  -- ≈20-session avg traded value (₹ Cr)
      SELECT instrument_id, avg(close * volume) / 1e7 AS liq_cr
      FROM foundation_staging.ohlcv_stock
      WHERE date >= (SELECT d FROM latest) - INTERVAL '30 days' AND close > 0 AND volume > 0
      GROUP BY instrument_id
    ),
    j AS (
      SELECT l.instrument_id, im.symbol, im.name, im.sector, COALESCE(c.cap,'micro') AS cap,
             l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va,
             l.composite::float comp,
             td.ret_1d::float r1d, td.ret_1w::float r1w, td.ret_1m::float r1m,
             td.ret_3m::float r3m, td.ret_6m::float r6m, td.ret_12m::float r12m,
             td.rs_1m_n500::float rs1m, td.rs_3m_n500::float rs3m, td.rs_6m_n500::float rs6m
      FROM foundation_staging.atlas_lens_scores_daily l
      JOIN foundation_staging.instrument_master im ON im.instrument_id = l.instrument_id
      LEFT JOIN cap c ON c.instrument_id = l.instrument_id
      LEFT JOIN foundation_staging.technical_daily td
        ON td.instrument_id = l.instrument_id AND td.asset_class='stock'
        AND td.date = (SELECT d FROM latest)
      WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest)
    ),
    dec AS (
      SELECT instrument_id, symbol, name, sector, cap, t, f, ca, fl, va, comp, r1d, r1w, r1m, r3m, r6m, r12m, rs1m, rs3m, rs6m,
        CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_tech,
        CASE WHEN f  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(f  IS NULL) ORDER BY f)  END d_fund,
        CASE WHEN ca IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(ca IS NULL) ORDER BY ca) END d_cat,
        CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow,
        CASE WHEN va IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(va IS NULL) ORDER BY va) END d_val,
        CASE WHEN comp IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(comp IS NULL) ORDER BY comp) END d_composite
      FROM j
    ),
    ff AS (  -- free-float market cap = market cap × non-promoter, non-ESOP share (concentration view).
             -- Shareholding required (INNER) so no name gets a fabricated 100%-free-float weight.
             -- (equity_marketcap union was tried + verified a no-op for the scored universe — the
             -- uncovered names lack market cap in EVERY source, not just screener_ratios.)
      SELECT mc.instrument_id,
        mc.market_cap * (100 - sh.promoter_pct - COALESCE(sh.employee_trusts_pct,0)) / 100.0 AS ff_mcap
      FROM (SELECT DISTINCT ON (instrument_id) instrument_id, market_cap FROM foundation_staging.screener_ratios
            WHERE market_cap IS NOT NULL ORDER BY instrument_id, as_of DESC NULLS LAST) mc
      JOIN (SELECT DISTINCT ON (instrument_id) instrument_id, promoter_pct, employee_trusts_pct
            FROM foundation_staging.lens_shareholding WHERE promoter_pct IS NOT NULL
            ORDER BY instrument_id, period_end DESC) sh ON sh.instrument_id = mc.instrument_id
    )
    SELECT d.symbol, d.name, d.cap, d.d_tech, d.d_fund, d.d_cat, d.d_flow, d.d_val,
      d.r1d, d.r1w, d.r1m, d.r3m, d.r6m, d.r12m, d.rs1m, d.rs3m, d.rs6m,
      (d.r3m - sr.sret_3m) AS rs_sector_3m, liq.liq_cr,
      (COALESCE((d.d_composite>=10)::int,0)) AS lead,  -- LEADER = top decile (D10) of composite within cap cohort (one rule; 0/1)
      ((COALESCE(d.d_tech,0)+COALESCE(d.d_flow,0))::float
        / NULLIF((d.d_tech IS NOT NULL)::int+(d.d_flow IS NOT NULL)::int,0)) AS strength,
      -- free-float weight WITHIN this sector: the window runs after the sector WHERE, so it sums the sector only
      round((100.0 * ff.ff_mcap / NULLIF(sum(ff.ff_mcap) OVER (), 0))::numeric, 2) AS ff_weight
    FROM dec d
    LEFT JOIN sec_ret sr ON sr.sector_name = d.sector
    LEFT JOIN liq ON liq.instrument_id = d.instrument_id
    LEFT JOIN ff ON ff.instrument_id = d.instrument_id
    WHERE d.sector = ${sector}
    ORDER BY strength DESC NULLS LAST
  `
  const n = (v: string | null) => (v == null ? null : Number(v))
  return rows.map(r => ({
    symbol: r.symbol, name: r.name, cap: r.cap,
    d_tech: n(r.d_tech), d_fund: n(r.d_fund), d_cat: n(r.d_cat), d_flow: n(r.d_flow), d_val: n(r.d_val),
    lead: Number(r.lead ?? 0), strength: n(r.strength),
    ret_1d: n(r.r1d), ret_1w: n(r.r1w), ret_1m: n(r.r1m),
    ret_3m: n(r.r3m), ret_6m: n(r.r6m), ret_12m: n(r.r12m),
    rs_1m: n(r.rs1m), rs_3m: n(r.rs3m), rs_6m: n(r.rs6m), rs_sector_3m: n(r.rs_sector_3m),
    liq_cr: n(r.liq_cr), ff_weight: n(r.ff_weight),
  }))
}

export type SectorFundamentals = {
  n: number; ebitda_margin: number | null; net_margin: number | null; pct_profitable: number | null
  u_ebitda_margin: number | null; u_net_margin: number | null; u_pct_profitable: number | null
  constituents: ConstituentFin[] // per-stock margins — the within-sector drill
}

// Revenue-WEIGHTED sector margins (Σebitda/Σrevenue), computed from raw components via the
// tested pure aggregator — NOT a simple average of per-stock ratios (which a single
// tiny-revenue loss-maker wrecked, pushing the universe negative). debt/equity dropped:
// debt_equity_ratio is ~99.5% null in the feed, so it was a near-empty column. % profitable
// (share of constituents with PAT>0) replaces it — robust and a real sector-health read.
// Scoped to the SCORED constituents (the same set as the rest of the page — the "N
// constituents" header and the constituents table), so the drill count matches everywhere;
// universe = the full scored universe (Nifty 500), apples-to-apples with sector RS/deciles.
export async function getSectorFundamentals(sector: string): Promise<SectorFundamentals | null> {
  const r = await sql<Record<string, string>[]>`
    WITH ld AS (SELECT max(date) d FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'),
    scored AS (SELECT instrument_id FROM foundation_staging.atlas_lens_scores_daily
               WHERE asset_class='stock' AND date=(SELECT d FROM ld)),
    latest_fin AS (
      SELECT DISTINCT ON (fq.instrument_id) fq.instrument_id,
             fq.ebitda::float ebitda, fq.revenue::float revenue, fq.pat::float pat
      FROM foundation_staging.financials_quarterly fq
      WHERE fq.consolidated ORDER BY fq.instrument_id, fq.period_end DESC
    )
    SELECT im.symbol, im.sector, lf.ebitda, lf.revenue, lf.pat
    FROM foundation_staging.instrument_master im
    JOIN scored sc ON sc.instrument_id = im.instrument_id
    JOIN latest_fin lf ON lf.instrument_id = im.instrument_id
    WHERE im.asset_class='stock' AND im.sector IS NOT NULL
  `
  const num = (v: string | null) => (v == null ? null : Number(v))
  const all: RawFin[] = r.map((x) => ({ symbol: x.symbol, ebitda: num(x.ebitda), revenue: num(x.revenue), pat: num(x.pat) }))
  const sectorRows = r.filter((x) => x.sector === sector).map((x): RawFin => ({ symbol: x.symbol, ebitda: num(x.ebitda), revenue: num(x.revenue), pat: num(x.pat) }))
  const sec = aggregateMargins(sectorRows)
  if (sec.n === 0) return null
  const uni = aggregateMargins(all)
  return {
    n: sec.n, ebitda_margin: sec.ebitda_margin, net_margin: sec.net_margin, pct_profitable: sec.pct_profitable,
    u_ebitda_margin: uni.ebitda_margin, u_net_margin: uni.net_margin, u_pct_profitable: uni.pct_profitable,
    constituents: perConstituentMargins(sectorRows),
  }
}

export type ConstituentFlow = {
  symbol: string; deliv_30d: number | null; deliv_60d: number | null; updown: number | null; flow_inst: number | null
}
export type SectorFundFlow = {
  n: number; deliv_30d: number | null; deliv_60d: number | null; updown: number | null; flow_inst: number | null
  u_deliv_30d: number | null; u_deliv_60d: number | null; u_updown: number | null; u_flow_inst: number | null
  constituents: ConstituentFlow[] // per-stock flow — the within-sector drill
}

// Delivery / flow are equal-weighted means across constituents (each is already a
// normalised 0–100 per-stock value, so equal-weighting is the right breadth read — unlike
// margins, which must be revenue-weighted). Also returns the per-constituent rows so the
// table can drill into "which names drive the sector number". Scoped to the SCORED
// constituents (same set as the rest of the page), so counts match everywhere.
export async function getSectorFundFlow(sector: string): Promise<SectorFundFlow | null> {
  const r = await sql<Record<string, string>[]>`
    WITH dl AS (SELECT max(date) d FROM foundation_staging.delivery_daily),
    jl AS (SELECT max(date) d FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'),
    scored AS (SELECT instrument_id, flow_institutional FROM foundation_staging.atlas_lens_scores_daily
               WHERE asset_class='stock' AND date=(SELECT d FROM jl))
    SELECT im.symbol, im.sector, d.delivery_avg_30d::float a30, d.delivery_avg_60d::float a60,
           d.delivery_updown_asym::float ud, sc.flow_institutional::float fi
    FROM foundation_staging.instrument_master im
    JOIN scored sc ON sc.instrument_id = im.instrument_id
    LEFT JOIN foundation_staging.delivery_daily d ON d.instrument_id = im.instrument_id AND d.date=(SELECT d FROM dl)
    WHERE im.asset_class='stock' AND im.sector IS NOT NULL
  `
  const num = (v: string | null) => (v == null ? null : Number(v))
  const mean = (xs: (number | null)[]) => {
    const v = xs.filter((x): x is number => x != null)
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
  }
  const sectorRows = r.filter((x) => x.sector === sector)
  if (sectorRows.length === 0) return null
  const col = (rows: Record<string, string>[], k: string) => mean(rows.map((x) => num(x[k])))
  const constituents: ConstituentFlow[] = sectorRows
    .map((x) => ({ symbol: x.symbol, deliv_30d: num(x.a30), deliv_60d: num(x.a60), updown: num(x.ud), flow_inst: num(x.fi) }))
    .sort((a, b) => (b.deliv_30d ?? -Infinity) - (a.deliv_30d ?? -Infinity))
  return {
    n: sectorRows.length,
    deliv_30d: col(sectorRows, 'a30'), deliv_60d: col(sectorRows, 'a60'),
    updown: col(sectorRows, 'ud'), flow_inst: col(sectorRows, 'fi'),
    u_deliv_30d: col(r, 'a30'), u_deliv_60d: col(r, 'a60'), u_updown: col(r, 'ud'), u_flow_inst: col(r, 'fi'),
    constituents,
  }
}
