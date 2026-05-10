import 'server-only'
import sql from '@/lib/db'

export type SectorFundRow = {
  mstar_id: string
  scheme_name: string
  amc: string
  category_name: string
  broad_category: string
  sector_weight_pct: string | null
  sector_rank: number
  data_as_of: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
  realized_vol_63: string | null
  drawdown_ratio_252: string | null
  nav_state: string | null
  composition_state: string | null
  holdings_state: string | null
  recommendation: string | null
  performance_gate: boolean | null
  sectors_gate: boolean | null
  stocks_gate: boolean | null
  market_gate: boolean | null
  entry_trigger: boolean | null
  exit_trigger: boolean | null
}

export async function getSectorFunds(
  sectorName: string,
  limit = 30,
): Promise<SectorFundRow[]> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error(`limit must be between 1 and 100, got: ${limit}`)
  }
  return sql<SectorFundRow[]>`
    WITH latest_holdings AS (
      SELECT mstar_id, MAX(as_of_date) AS as_of_date
      FROM public.de_mf_holdings
      GROUP BY mstar_id
    ),
    sector_weights AS (
      SELECT
        h.mstar_id,
        COALESCE(u.sector, 'Unknown') AS sector,
        SUM(h.weight_pct)             AS sector_weight_pct
      FROM public.de_mf_holdings h
      JOIN latest_holdings lh ON h.mstar_id = lh.mstar_id AND h.as_of_date = lh.as_of_date
      LEFT JOIN atlas.atlas_universe_stocks u
        ON u.instrument_id = h.instrument_id AND u.effective_to IS NULL
      WHERE u.sector IS NOT NULL
      GROUP BY h.mstar_id, u.sector
    ),
    ranked_sectors AS (
      SELECT
        mstar_id,
        sector,
        sector_weight_pct,
        RANK() OVER (PARTITION BY mstar_id ORDER BY sector_weight_pct DESC) AS sector_rank
      FROM sector_weights
    ),
    qualifying AS (
      SELECT mstar_id, sector_weight_pct::text AS sector_weight_pct, sector_rank::int AS sector_rank
      FROM ranked_sectors
      WHERE sector = ${sectorName} AND sector_rank <= 3
    )
    SELECT
      uf.mstar_id,
      uf.scheme_name,
      uf.amc,
      uf.category_name,
      uf.broad_category,
      q.sector_weight_pct,
      q.sector_rank,
      (SELECT MAX(nav_date)::text FROM atlas.atlas_fund_metrics_daily) AS data_as_of,
      fm.ret_1m::text           AS ret_1m,
      fm.ret_3m::text           AS ret_3m,
      fm.ret_6m::text           AS ret_6m,
      fm.ret_12m::text          AS ret_12m,
      fm.rs_pctile_3m::text     AS rs_pctile_3m,
      fm.realized_vol_63::text  AS realized_vol_63,
      fm.drawdown_ratio_252::text AS drawdown_ratio_252,
      fs.nav_state,
      fs.composition_state,
      fs.holdings_state,
      fd.recommendation,
      fd.performance_gate,
      fd.sectors_gate,
      fd.stocks_gate,
      fd.market_gate,
      fd.entry_trigger,
      fd.exit_trigger
    FROM qualifying q
    JOIN atlas.atlas_universe_funds uf ON uf.mstar_id = q.mstar_id
    LEFT JOIN atlas.atlas_fund_metrics_daily fm
      ON fm.mstar_id = uf.mstar_id
      AND fm.nav_date = (SELECT MAX(nav_date) FROM atlas.atlas_fund_metrics_daily)
    LEFT JOIN atlas.atlas_fund_states_daily fs
      ON fs.mstar_id = uf.mstar_id
      AND fs.date = (SELECT MAX(date) FROM atlas.atlas_fund_states_daily)
    LEFT JOIN atlas.atlas_fund_decisions_daily fd
      ON fd.mstar_id = uf.mstar_id
      AND fd.date = (SELECT MAX(date) FROM atlas.atlas_fund_decisions_daily)
    ORDER BY q.sector_weight_pct DESC NULLS LAST, fm.rs_pctile_3m DESC NULLS LAST
    LIMIT ${limit}
  `
}
