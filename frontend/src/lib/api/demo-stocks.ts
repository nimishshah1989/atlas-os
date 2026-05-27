// frontend/src/lib/api/demo-stocks.ts
//
// Demo stock universe with 4-tenure ConvictionTape per row. Used until
// /v1/screen.stocks is wired. Mix of Nifty 50 / 100 / 500 names across tiers
// and sectors; verdicts are plausible (positive bias for leaders, negative
// for laggards, mixed for mid-cap).

import type { ScreenStock, ConvictionVerdict, Tier, Tenure } from './v1'

type Mini = {
  iid: string
  symbol: string
  company_name: string
  sector: string
  tier: Tier
  mcap_cr: number
  rs_state: string
  stage: string
  pattern: 'all_pos' | 'pos_short_neg_long' | 'neg_short_pos_long' | 'all_neg' | 'mixed' | 'mid_pos'
  rets: [number, number, number, number] // 1m,3m,6m,12m
  rs_pctile_3m: number
  is_investable: boolean
}

const STOCKS: Mini[] = [
  { iid: 'INE002A01018', symbol: 'RELIANCE', company_name: 'Reliance Industries Ltd', sector: 'Energy', tier: 'Large', mcap_cr: 1900000, rs_state: 'Leader', stage: 'stage_2b', pattern: 'all_pos', rets: [0.042, 0.121, 0.184, 0.298], rs_pctile_3m: 0.87, is_investable: true },
  { iid: 'INE040A01034', symbol: 'HDFCBANK', company_name: 'HDFC Bank Ltd', sector: 'Banking', tier: 'Large', mcap_cr: 1320000, rs_state: 'Leader', stage: 'stage_2c', pattern: 'mid_pos', rets: [0.038, 0.094, 0.142, 0.198], rs_pctile_3m: 0.79, is_investable: true },
  { iid: 'INE467B01029', symbol: 'TCS', company_name: 'Tata Consultancy Services Ltd', sector: 'IT', tier: 'Large', mcap_cr: 1410000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'all_pos', rets: [0.029, 0.078, 0.124, 0.187], rs_pctile_3m: 0.76, is_investable: true },
  { iid: 'INE090A01021', symbol: 'ICICIBANK', company_name: 'ICICI Bank Ltd', sector: 'Banking', tier: 'Large', mcap_cr: 845000, rs_state: 'Leader', stage: 'stage_2b', pattern: 'mid_pos', rets: [0.041, 0.103, 0.156, 0.241], rs_pctile_3m: 0.74, is_investable: true },
  { iid: 'INE009A01021', symbol: 'INFY', company_name: 'Infosys Ltd', sector: 'IT', tier: 'Large', mcap_cr: 720000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'pos_short_neg_long', rets: [0.012, 0.078, 0.094, -0.024], rs_pctile_3m: 0.71, is_investable: true },
  { iid: 'INE018A01030', symbol: 'LT', company_name: 'Larsen & Toubro Ltd', sector: 'Capital Goods', tier: 'Large', mcap_cr: 460000, rs_state: 'Leader', stage: 'stage_2a', pattern: 'all_pos', rets: [0.058, 0.142, 0.231, 0.387], rs_pctile_3m: 0.92, is_investable: true },
  { iid: 'INE154A01025', symbol: 'ITC', company_name: 'ITC Ltd', sector: 'FMCG', tier: 'Large', mcap_cr: 540000, rs_state: 'Weak', stage: 'stage_3', pattern: 'neg_short_pos_long', rets: [-0.004, -0.021, -0.012, 0.084], rs_pctile_3m: 0.38, is_investable: false },
  { iid: 'INE062A01020', symbol: 'SBIN', company_name: 'State Bank of India', sector: 'Banking', tier: 'Large', mcap_cr: 685000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'mid_pos', rets: [0.022, 0.087, 0.121, 0.198], rs_pctile_3m: 0.68, is_investable: true },
  { iid: 'INE752E01010', symbol: 'POWERGRID', company_name: 'Power Grid Corporation Ltd', sector: 'Utilities', tier: 'Large', mcap_cr: 285000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'all_pos', rets: [0.031, 0.082, 0.144, 0.221], rs_pctile_3m: 0.78, is_investable: true },
  { iid: 'INE733E01010', symbol: 'NTPC', company_name: 'NTPC Ltd', sector: 'Utilities', tier: 'Large', mcap_cr: 340000, rs_state: 'Leader', stage: 'stage_2c', pattern: 'all_pos', rets: [0.047, 0.118, 0.187, 0.312], rs_pctile_3m: 0.85, is_investable: true },
  { iid: 'INE423A01024', symbol: 'ADANIENT', company_name: 'Adani Enterprises Ltd', sector: 'Conglomerate', tier: 'Large', mcap_cr: 380000, rs_state: 'Emerging', stage: 'stage_2a', pattern: 'mid_pos', rets: [0.061, 0.094, 0.118, 0.078], rs_pctile_3m: 0.62, is_investable: true },
  { iid: 'INE585B01010', symbol: 'MARUTI', company_name: 'Maruti Suzuki India Ltd', sector: 'Auto', tier: 'Large', mcap_cr: 360000, rs_state: 'Average', stage: 'stage_1', pattern: 'mixed', rets: [0.008, 0.024, 0.061, 0.124], rs_pctile_3m: 0.54, is_investable: true },
  { iid: 'INE237A01028', symbol: 'KOTAKBANK', company_name: 'Kotak Mahindra Bank Ltd', sector: 'Banking', tier: 'Large', mcap_cr: 360000, rs_state: 'Average', stage: 'stage_1', pattern: 'mixed', rets: [0.011, 0.034, 0.052, 0.087], rs_pctile_3m: 0.51, is_investable: true },
  { iid: 'INE021A01026', symbol: 'ASIANPAINT', company_name: 'Asian Paints Ltd', sector: 'Consumer Durables', tier: 'Large', mcap_cr: 285000, rs_state: 'Weak', stage: 'stage_3', pattern: 'neg_short_pos_long', rets: [-0.012, -0.034, -0.061, 0.024], rs_pctile_3m: 0.31, is_investable: false },
  { iid: 'INE001A01036', symbol: 'HDFCLIFE', company_name: 'HDFC Life Insurance Co Ltd', sector: 'Insurance', tier: 'Large', mcap_cr: 140000, rs_state: 'Average', stage: 'stage_1', pattern: 'mixed', rets: [0.018, 0.042, 0.071, 0.121], rs_pctile_3m: 0.56, is_investable: true },
  // Mid
  { iid: 'INE721A01013', symbol: 'PERSISTENT', company_name: 'Persistent Systems Ltd', sector: 'IT', tier: 'Mid', mcap_cr: 64000, rs_state: 'Leader', stage: 'stage_2b', pattern: 'all_pos', rets: [0.087, 0.187, 0.298, 0.487], rs_pctile_3m: 0.94, is_investable: true },
  { iid: 'INE591G01017', symbol: 'COFORGE', company_name: 'Coforge Ltd', sector: 'IT', tier: 'Mid', mcap_cr: 51000, rs_state: 'Leader', stage: 'stage_2b', pattern: 'all_pos', rets: [0.072, 0.162, 0.241, 0.392], rs_pctile_3m: 0.91, is_investable: true },
  { iid: 'INE04I401011', symbol: 'KPITTECH', company_name: 'KPIT Technologies Ltd', sector: 'IT', tier: 'Mid', mcap_cr: 42000, rs_state: 'Strong', stage: 'stage_2c', pattern: 'all_pos', rets: [0.054, 0.124, 0.187, 0.318], rs_pctile_3m: 0.84, is_investable: true },
  { iid: 'INE405E01023', symbol: 'TANLA', company_name: 'Tanla Platforms Ltd', sector: 'IT', tier: 'Mid', mcap_cr: 12000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'all_pos', rets: [0.047, 0.108, 0.158, 0.241], rs_pctile_3m: 0.78, is_investable: true },
  { iid: 'INE306R01017', symbol: 'INTELLECT', company_name: 'Intellect Design Arena Ltd', sector: 'IT', tier: 'Mid', mcap_cr: 11500, rs_state: 'Strong', stage: 'stage_2a', pattern: 'mid_pos', rets: [0.041, 0.094, 0.142, 0.187], rs_pctile_3m: 0.75, is_investable: true },
  { iid: 'INE628A01036', symbol: 'UPL', company_name: 'UPL Ltd', sector: 'Chemicals', tier: 'Mid', mcap_cr: 41000, rs_state: 'Emerging', stage: 'stage_2a', pattern: 'mid_pos', rets: [0.038, 0.074, 0.094, 0.121], rs_pctile_3m: 0.66, is_investable: true },
  { iid: 'INE242A01010', symbol: 'IOC', company_name: 'Indian Oil Corporation Ltd', sector: 'Energy', tier: 'Large', mcap_cr: 195000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'all_pos', rets: [0.041, 0.108, 0.164, 0.241], rs_pctile_3m: 0.74, is_investable: true },
  { iid: 'INE239A01016', symbol: 'NESTLEIND', company_name: 'Nestle India Ltd', sector: 'FMCG', tier: 'Large', mcap_cr: 245000, rs_state: 'Average', stage: 'stage_1', pattern: 'mixed', rets: [0.014, 0.031, 0.052, 0.094], rs_pctile_3m: 0.52, is_investable: true },
  { iid: 'INE935A01035', symbol: 'PERSISTENT', company_name: 'LIC India', sector: 'Insurance', tier: 'Large', mcap_cr: 380000, rs_state: 'Emerging', stage: 'stage_2a', pattern: 'mid_pos', rets: [0.034, 0.078, 0.121, 0.187], rs_pctile_3m: 0.68, is_investable: true },
  { iid: 'INE883A01011', symbol: 'CUMMINSIND', company_name: 'Cummins India Ltd', sector: 'Capital Goods', tier: 'Mid', mcap_cr: 78000, rs_state: 'Leader', stage: 'stage_2b', pattern: 'all_pos', rets: [0.071, 0.158, 0.241, 0.398], rs_pctile_3m: 0.89, is_investable: true },
  { iid: 'INE821I01022', symbol: 'IRCTC', company_name: 'Indian Railway Catering & Tourism', sector: 'Services', tier: 'Mid', mcap_cr: 68000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'all_pos', rets: [0.058, 0.124, 0.187, 0.241], rs_pctile_3m: 0.81, is_investable: true },
  { iid: 'INE357A01014', symbol: 'BIOCON', company_name: 'Biocon Ltd', sector: 'Pharma', tier: 'Mid', mcap_cr: 38000, rs_state: 'Average', stage: 'stage_1', pattern: 'mixed', rets: [0.024, 0.042, 0.061, 0.087], rs_pctile_3m: 0.48, is_investable: true },
  // Small
  { iid: 'INE343H01029', symbol: 'JBCHEPHARM', company_name: 'JB Chemicals & Pharmaceuticals', sector: 'Pharma', tier: 'Small', mcap_cr: 28000, rs_state: 'Leader', stage: 'stage_2b', pattern: 'all_pos', rets: [0.094, 0.218, 0.341, 0.521], rs_pctile_3m: 0.96, is_investable: true },
  { iid: 'INE002L01015', symbol: 'CYIENT', company_name: 'Cyient Ltd', sector: 'IT', tier: 'Small', mcap_cr: 21000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'mid_pos', rets: [0.061, 0.142, 0.218, 0.341], rs_pctile_3m: 0.83, is_investable: true },
  { iid: 'INE001K01018', symbol: 'NEWGEN', company_name: 'Newgen Software Technologies', sector: 'IT', tier: 'Small', mcap_cr: 15000, rs_state: 'Strong', stage: 'stage_2c', pattern: 'all_pos', rets: [0.077, 0.184, 0.298, 0.487], rs_pctile_3m: 0.88, is_investable: true },
  // Negatives
  { iid: 'INE079A01024', symbol: 'AMBUJACEM', company_name: 'Ambuja Cements Ltd', sector: 'Cement', tier: 'Large', mcap_cr: 124000, rs_state: 'Laggard', stage: 'stage_4', pattern: 'all_neg', rets: [-0.041, -0.094, -0.142, -0.187], rs_pctile_3m: 0.18, is_investable: false },
  { iid: 'INE066A01021', symbol: 'EICHERMOT', company_name: 'Eicher Motors Ltd', sector: 'Auto', tier: 'Large', mcap_cr: 110000, rs_state: 'Weak', stage: 'stage_3', pattern: 'neg_short_pos_long', rets: [-0.018, -0.041, -0.012, 0.087], rs_pctile_3m: 0.34, is_investable: false },
  { iid: 'INE007B01023', symbol: 'BPCL', company_name: 'Bharat Petroleum Corporation Ltd', sector: 'Energy', tier: 'Large', mcap_cr: 87000, rs_state: 'Average', stage: 'stage_1', pattern: 'mixed', rets: [0.012, 0.034, 0.058, 0.094], rs_pctile_3m: 0.54, is_investable: true },
  { iid: 'INE043D01016', symbol: 'JINDALSTEL', company_name: 'Jindal Steel & Power Ltd', sector: 'Metals', tier: 'Mid', mcap_cr: 76000, rs_state: 'Weak', stage: 'stage_4', pattern: 'all_neg', rets: [-0.031, -0.078, -0.124, -0.187], rs_pctile_3m: 0.22, is_investable: false },
  { iid: 'INE079J01017', symbol: 'ZEEL', company_name: 'Zee Entertainment Enterprises', sector: 'Media', tier: 'Mid', mcap_cr: 14000, rs_state: 'Laggard', stage: 'stage_4', pattern: 'all_neg', rets: [-0.081, -0.192, -0.281, -0.412], rs_pctile_3m: 0.12, is_investable: false },
  // Additional rows to fill out filterability
  { iid: 'INE192A01025', symbol: 'TATAMOTORS', company_name: 'Tata Motors Ltd', sector: 'Auto', tier: 'Large', mcap_cr: 285000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'mid_pos', rets: [0.041, 0.094, 0.142, 0.241], rs_pctile_3m: 0.72, is_investable: true },
  { iid: 'INE158A01026', symbol: 'HEROMOTOCO', company_name: 'Hero MotoCorp Ltd', sector: 'Auto', tier: 'Large', mcap_cr: 78000, rs_state: 'Average', stage: 'stage_1', pattern: 'mixed', rets: [0.018, 0.041, 0.068, 0.121], rs_pctile_3m: 0.49, is_investable: true },
  { iid: 'INE095A01012', symbol: 'INDUSINDBK', company_name: 'IndusInd Bank Ltd', sector: 'Banking', tier: 'Large', mcap_cr: 110000, rs_state: 'Average', stage: 'stage_1', pattern: 'mixed', rets: [0.024, 0.058, 0.094, 0.142], rs_pctile_3m: 0.58, is_investable: true },
  { iid: 'INE205A01025', symbol: 'VEDL', company_name: 'Vedanta Ltd', sector: 'Metals', tier: 'Large', mcap_cr: 175000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'all_pos', rets: [0.054, 0.118, 0.187, 0.298], rs_pctile_3m: 0.79, is_investable: true },
  { iid: 'INE628B01026', symbol: 'HINDPETRO', company_name: 'Hindustan Petroleum Corporation Ltd', sector: 'Energy', tier: 'Mid', mcap_cr: 78000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'mid_pos', rets: [0.034, 0.087, 0.142, 0.198], rs_pctile_3m: 0.71, is_investable: true },
  { iid: 'INE233A01035', symbol: 'GODREJCP', company_name: 'Godrej Consumer Products Ltd', sector: 'FMCG', tier: 'Mid', mcap_cr: 124000, rs_state: 'Average', stage: 'stage_1', pattern: 'mixed', rets: [0.014, 0.031, 0.052, 0.094], rs_pctile_3m: 0.51, is_investable: true },
  { iid: 'INE361B01024', symbol: 'DIVISLAB', company_name: 'Divi\'s Laboratories Ltd', sector: 'Pharma', tier: 'Large', mcap_cr: 175000, rs_state: 'Strong', stage: 'stage_2b', pattern: 'all_pos', rets: [0.041, 0.094, 0.158, 0.241], rs_pctile_3m: 0.74, is_investable: true },
]

function patternToTape(pattern: Mini['pattern']): Record<Tenure, ConvictionVerdict> {
  const make = (d: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL', ic: number, rc: number, top: string | null): ConvictionVerdict => ({
    direction: d, ic, rule_count: rc, top_rule_id: top,
  })
  switch (pattern) {
    case 'all_pos':
      return {
        '1m': make('POSITIVE', 0.041, 2, 'QM_L1m_align3'),
        '3m': make('POSITIVE', 0.058, 3, 'QM_L3m_align3_lowvol'),
        '6m': make('POSITIVE', 0.064, 2, 'SRL2_L6m_rk90_sc5'),
        '12m': make('POSITIVE', 0.052, 1, 'LE_L12m_vz252_10'),
      }
    case 'pos_short_neg_long':
      return {
        '1m': make('POSITIVE', 0.038, 2, 'QM_L1m_align3'),
        '3m': make('POSITIVE', 0.041, 2, 'QM_L3m_align3_lowvol'),
        '6m': make('NEUTRAL', 0.0, 0, null),
        '12m': make('NEGATIVE', -0.024, 1, 'WQ_L12m_dvol'),
      }
    case 'neg_short_pos_long':
      return {
        '1m': make('NEGATIVE', -0.018, 1, 'OE_L1m_roc126'),
        '3m': make('NEGATIVE', -0.012, 1, 'DVA_L3m_dd'),
        '6m': make('NEUTRAL', 0.0, 0, null),
        '12m': make('POSITIVE', 0.024, 1, 'DV_L12m_rebound'),
      }
    case 'all_neg':
      return {
        '1m': make('NEGATIVE', -0.034, 1, 'OE_L1m_roc126'),
        '3m': make('NEGATIVE', -0.061, 2, 'SDR_L3m_secrnk'),
        '6m': make('NEGATIVE', -0.094, 2, 'SBD_L6m_secrnk18'),
        '12m': make('NEGATIVE', -0.121, 3, 'SDR_L12m_secrnk28'),
      }
    case 'mid_pos':
      return {
        '1m': make('NEUTRAL', 0.0, 0, null),
        '3m': make('POSITIVE', 0.054, 2, 'SRL_L3m_topsector'),
        '6m': make('POSITIVE', 0.061, 2, 'SRL2_L6m_rk90_sc5'),
        '12m': make('POSITIVE', 0.041, 1, 'LE_L12m_vz252_10'),
      }
    case 'mixed':
    default:
      return {
        '1m': make('NEUTRAL', 0.0, 0, null),
        '3m': make('NEUTRAL', 0.0, 0, null),
        '6m': make('POSITIVE', 0.024, 1, 'SRL_L3m_topsector'),
        '12m': make('NEUTRAL', 0.0, 0, null),
      }
  }
}

function hydrate(m: Mini): ScreenStock {
  return {
    iid: m.iid,
    symbol: m.symbol,
    company_name: m.company_name,
    sector: m.sector,
    tier: m.tier,
    mcap_inr: m.mcap_cr * 1e7, // crore → INR
    rs_state: m.rs_state,
    stage: m.stage,
    conviction_tape: patternToTape(m.pattern),
    ret_1m: m.rets[0],
    ret_3m: m.rets[1],
    ret_6m: m.rets[2],
    ret_12m: m.rets[3],
    rs_pctile_3m: m.rs_pctile_3m,
    is_investable: m.is_investable,
  }
}

export function getDemoStocks(params: { tier?: Tier; sector?: string; limit?: number } = {}): ScreenStock[] {
  let out = STOCKS.map(hydrate)
  if (params.tier) out = out.filter(s => s.tier === params.tier)
  if (params.sector) out = out.filter(s => s.sector === params.sector)
  if (params.limit && params.limit > 0) out = out.slice(0, params.limit)
  return out
}
