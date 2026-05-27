// frontend/src/lib/api/demo-misc.ts
//
// Demo fixtures for ETFs, Funds, Sectors, MarketRegime. Used until
// /v1/* endpoints land. Plausible Indian universe + the Atlas v6 cells
// signal pattern.

import type { ScreenEtf, ScreenFund, ScreenSector, MarketRegime, ConvictionTape, ConvictionVerdict } from './v1'

function posTape(strong = true): ConvictionTape {
  const ic = strong ? 0.062 : 0.038
  const make = (rc: number, top: string | null): ConvictionVerdict => ({
    direction: 'POSITIVE', ic, rule_count: rc, top_rule_id: top,
  })
  return {
    '1m': make(2, 'QM_L1m_align3'),
    '3m': make(3, 'QM_L3m_align3_lowvol'),
    '6m': make(2, 'SRL2_L6m_rk90_sc5'),
    '12m': make(1, 'LE_L12m_vz252_10'),
  }
}

function neutralTape(): ConvictionTape {
  const v: ConvictionVerdict = { direction: 'NEUTRAL', ic: 0.0, rule_count: 0, top_rule_id: null }
  return { '1m': v, '3m': v, '6m': v, '12m': v }
}

export function getDemoEtfs(): ScreenEtf[] {
  return [
    { iid: 'NIFTYBEES', ticker: 'NIFTYBEES', name: 'Nippon India ETF Nifty 50 BeES', category: 'Large-cap Index', aum_inr: 38000e7, conviction_tape: posTape(true), ret_1m: 0.024, ret_3m: 0.078, ret_6m: 0.124, ret_12m: 0.187, rs_state: 'Strong' },
    { iid: 'BANKBEES', ticker: 'BANKBEES', name: 'Nippon India ETF Nifty Bank BeES', category: 'Banking', aum_inr: 12000e7, conviction_tape: posTape(true), ret_1m: 0.031, ret_3m: 0.094, ret_6m: 0.158, ret_12m: 0.241, rs_state: 'Leader' },
    { iid: 'JUNIORBEES', ticker: 'JUNIORBEES', name: 'Nippon India ETF Junior BeES', category: 'Mid-cap Index', aum_inr: 4200e7, conviction_tape: posTape(true), ret_1m: 0.042, ret_3m: 0.118, ret_6m: 0.187, ret_12m: 0.298, rs_state: 'Leader' },
    { iid: 'GOLDBEES', ticker: 'GOLDBEES', name: 'Nippon India ETF Gold BeES', category: 'Commodities', aum_inr: 9800e7, conviction_tape: neutralTape(), ret_1m: 0.008, ret_3m: 0.024, ret_6m: 0.058, ret_12m: 0.124, rs_state: 'Average' },
    { iid: 'NIFTYIETF', ticker: 'NIFTYIETF', name: 'ICICI Prudential Nifty ETF', category: 'Large-cap Index', aum_inr: 14000e7, conviction_tape: posTape(false), ret_1m: 0.022, ret_3m: 0.074, ret_6m: 0.118, ret_12m: 0.181, rs_state: 'Strong' },
    { iid: 'PSUBNKBEES', ticker: 'PSUBNKBEES', name: 'Nippon India ETF PSU Bank BeES', category: 'PSU Banking', aum_inr: 1800e7, conviction_tape: posTape(true), ret_1m: 0.054, ret_3m: 0.142, ret_6m: 0.218, ret_12m: 0.341, rs_state: 'Leader' },
    { iid: 'ITBEES', ticker: 'ITBEES', name: 'Nippon India ETF IT BeES', category: 'IT', aum_inr: 880e7, conviction_tape: posTape(true), ret_1m: 0.018, ret_3m: 0.061, ret_6m: 0.121, ret_12m: 0.198, rs_state: 'Strong' },
    { iid: 'CONSUMBEES', ticker: 'CONSUMBEES', name: 'Nippon India ETF Consumption', category: 'Consumer', aum_inr: 540e7, conviction_tape: neutralTape(), ret_1m: 0.012, ret_3m: 0.034, ret_6m: 0.058, ret_12m: 0.094, rs_state: 'Average' },
  ]
}

export function getDemoFunds(): ScreenFund[] {
  return [
    { iid: 'F100001', code: '100001', name: 'Parag Parikh Flexi Cap Fund', category: 'Flexi Cap', aum_inr: 65000e7, style_box: { size: 'Large', style: 'Blend' }, conviction_tape: posTape(true), ret_1m: 0.024, ret_3m: 0.072, ret_6m: 0.124, ret_12m: 0.214, rs_state: 'Strong' },
    { iid: 'F100002', code: '100002', name: 'Mirae Asset Large Cap Fund', category: 'Large Cap', aum_inr: 38000e7, style_box: { size: 'Large', style: 'Growth' }, conviction_tape: posTape(true), ret_1m: 0.021, ret_3m: 0.064, ret_6m: 0.118, ret_12m: 0.198, rs_state: 'Strong' },
    { iid: 'F100003', code: '100003', name: 'HDFC Mid-Cap Opportunities Fund', category: 'Mid Cap', aum_inr: 48000e7, style_box: { size: 'Mid', style: 'Growth' }, conviction_tape: posTape(true), ret_1m: 0.034, ret_3m: 0.094, ret_6m: 0.158, ret_12m: 0.298, rs_state: 'Leader' },
    { iid: 'F100004', code: '100004', name: 'Axis Small Cap Fund', category: 'Small Cap', aum_inr: 16000e7, style_box: { size: 'Small', style: 'Growth' }, conviction_tape: posTape(false), ret_1m: 0.042, ret_3m: 0.108, ret_6m: 0.184, ret_12m: 0.341, rs_state: 'Leader' },
    { iid: 'F100005', code: '100005', name: 'ICICI Prudential Value Discovery Fund', category: 'Value', aum_inr: 32000e7, style_box: { size: 'Large', style: 'Value' }, conviction_tape: posTape(false), ret_1m: 0.018, ret_3m: 0.054, ret_6m: 0.094, ret_12m: 0.158, rs_state: 'Average' },
    { iid: 'F100006', code: '100006', name: 'SBI Bluechip Fund', category: 'Large Cap', aum_inr: 42000e7, style_box: { size: 'Large', style: 'Blend' }, conviction_tape: posTape(false), ret_1m: 0.019, ret_3m: 0.058, ret_6m: 0.108, ret_12m: 0.187, rs_state: 'Strong' },
    { iid: 'F100007', code: '100007', name: 'Kotak Emerging Equity Fund', category: 'Mid Cap', aum_inr: 38000e7, style_box: { size: 'Mid', style: 'Blend' }, conviction_tape: posTape(true), ret_1m: 0.031, ret_3m: 0.087, ret_6m: 0.142, ret_12m: 0.241, rs_state: 'Strong' },
    { iid: 'F100008', code: '100008', name: 'Nippon India Small Cap Fund', category: 'Small Cap', aum_inr: 51000e7, style_box: { size: 'Small', style: 'Blend' }, conviction_tape: posTape(true), ret_1m: 0.044, ret_3m: 0.114, ret_6m: 0.192, ret_12m: 0.341, rs_state: 'Leader' },
    { iid: 'F100009', code: '100009', name: 'DSP Equity Opportunities Fund', category: 'Large & Mid Cap', aum_inr: 11000e7, style_box: { size: 'Mid', style: 'Growth' }, conviction_tape: posTape(false), ret_1m: 0.026, ret_3m: 0.078, ret_6m: 0.128, ret_12m: 0.214, rs_state: 'Strong' },
    { iid: 'F100010', code: '100010', name: 'Quant Active Fund', category: 'Multi Cap', aum_inr: 8500e7, style_box: { size: 'Mid', style: 'Growth' }, conviction_tape: posTape(true), ret_1m: 0.038, ret_3m: 0.108, ret_6m: 0.187, ret_12m: 0.341, rs_state: 'Leader' },
  ]
}

export function getDemoSectors(): ScreenSector[] {
  const base = [
    ['Banking', 'Overweight', 0.71, 'Normal', 0.82, 0.024, 0.091, 'Leading'],
    ['IT', 'Overweight', 0.64, 'Low', 0.79, 0.018, 0.084, 'Leading'],
    ['Energy', 'Overweight', 0.58, 'Normal', 0.73, 0.031, 0.072, 'Leading'],
    ['Capital Goods', 'Overweight', 0.55, 'Normal', 0.69, 0.028, 0.078, 'Leading'],
    ['Pharma', 'Overweight', 0.52, 'Normal', 0.65, 0.022, 0.061, 'Leading'],
    ['Utilities', 'Overweight', 0.49, 'Normal', 0.62, 0.025, 0.058, 'Improving'],
    ['Conglomerate', 'Overweight', 0.48, 'Normal', 0.61, 0.034, 0.072, 'Improving'],
    ['Auto', 'Neutral', 0.41, 'Elevated', 0.54, 0.002, 0.011, 'Weakening'],
    ['Metals', 'Neutral', 0.39, 'Elevated', 0.51, 0.011, 0.024, 'Weakening'],
    ['Cement', 'Neutral', 0.38, 'Normal', 0.48, 0.008, 0.018, 'Weakening'],
    ['Insurance', 'Neutral', 0.37, 'Low', 0.46, 0.014, 0.031, 'Lagging'],
    ['Consumer Durables', 'Neutral', 0.36, 'Normal', 0.44, -0.004, 0.011, 'Weakening'],
    ['Chemicals', 'Neutral', 0.35, 'Normal', 0.42, 0.018, 0.041, 'Improving'],
    ['Telecom', 'Neutral', 0.33, 'Normal', 0.41, 0.011, 0.024, 'Lagging'],
    ['Hospitality', 'Neutral', 0.32, 'Normal', 0.39, 0.008, 0.024, 'Lagging'],
    ['Services', 'Neutral', 0.31, 'Normal', 0.38, 0.012, 0.028, 'Lagging'],
    ['Real Estate', 'Neutral', 0.30, 'Elevated', 0.36, 0.005, 0.014, 'Lagging'],
    ['Logistics', 'Neutral', 0.29, 'Normal', 0.35, 0.006, 0.018, 'Lagging'],
    ['Construction', 'Neutral', 0.28, 'Normal', 0.34, 0.004, 0.012, 'Lagging'],
    ['Aviation', 'Underweight', 0.27, 'Elevated', 0.32, -0.008, -0.012, 'Lagging'],
    ['Retail', 'Underweight', 0.26, 'Normal', 0.30, -0.011, -0.018, 'Lagging'],
    ['Textiles', 'Underweight', 0.24, 'Normal', 0.28, -0.014, -0.024, 'Lagging'],
    ['Education', 'Underweight', 0.22, 'Normal', 0.26, -0.018, -0.031, 'Lagging'],
    ['Paper', 'Underweight', 0.21, 'Normal', 0.24, -0.022, -0.038, 'Lagging'],
    ['Shipping', 'Underweight', 0.19, 'Normal', 0.21, -0.024, -0.041, 'Lagging'],
    ['Plastics', 'Underweight', 0.18, 'Normal', 0.19, -0.028, -0.048, 'Lagging'],
    ['Diamonds & Jewellery', 'Underweight', 0.16, 'Elevated', 0.17, -0.031, -0.054, 'Lagging'],
    ['Tobacco', 'Underweight', 0.14, 'Normal', 0.14, -0.038, -0.068, 'Weakening'],
    ['FMCG', 'Avoid', 0.12, 'High', 0.12, -0.041, -0.078, 'Lagging'],
    ['Media', 'Avoid', 0.09, 'High', 0.08, -0.052, -0.143, 'Lagging'],
  ] as const

  return base.map((row, i) => {
    const [name, state, breadth, vol, rsCross, r1, r3, quadrant] = row
    return {
      sector_iid: `SECTOR:${name}`,
      sector_name: name as string,
      rank: i + 1,
      rank_change: i < 7 ? (i % 2 === 0 ? 1 : 0) : (i % 3 === 0 ? -1 : 0),
      days_in_state: 20 + (i * 7) % 60,
      sector_state: state as string,
      breadth_pct_stage_2: breadth as number,
      vol_regime: vol as string,
      rs_pct_cross_sector: rsCross as number,
      ret_1m: r1 as number,
      ret_3m: r3 as number,
      rrg_quadrant: quadrant as string,
      cells_favored_today: state === 'Overweight'
        ? ['Large-3m-POSITIVE', 'Mid-3m-POSITIVE']
        : state === 'Avoid'
          ? ['Large-12m-NEGATIVE']
          : [],
    }
  })
}

export function getDemoRegime(): MarketRegime {
  // Build a 252-day history of fake breadth + state.
  const today = new Date()
  const history = Array.from({ length: 252 }, (_, i) => {
    const day = new Date(today)
    day.setDate(today.getDate() - (251 - i))
    const t = i / 251
    const breadth = 0.40 + 0.30 * Math.sin(t * Math.PI * 2) + 0.10 * Math.cos(t * Math.PI * 4)
    const state =
      breadth > 0.65 ? 'Risk-On' :
      breadth > 0.50 ? 'Constructive' :
      breadth > 0.35 ? 'Cautious' :
      'Risk-Off'
    return {
      date: day.toISOString().slice(0, 10),
      pct_above_ema_50: breadth,
      regime_state: state,
    }
  })
  return {
    regime_state: 'Constructive',
    deployment_pct: 80,
    pct_above_ema_50: 0.54,
    net_stage_2_5d: 24,
    participation: 0.68,
    history,
    cells_favored: [
      { cell_id: 'Large-3m-POSITIVE', ic_in_regime: 0.062 },
      { cell_id: 'Large-6m-POSITIVE', ic_in_regime: 0.158 },
      { cell_id: 'Mid-3m-POSITIVE', ic_in_regime: 0.168 },
      { cell_id: 'Mid-6m-POSITIVE', ic_in_regime: 0.174 },
      { cell_id: 'Small-3m-POSITIVE', ic_in_regime: 0.241 },
    ],
  }
}
