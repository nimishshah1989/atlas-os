// frontend/src/lib/api/demo-cells.ts
//
// Demo fixture for /v1/cell.definitions until the backend endpoint lands.
// Snapshot of /tmp/deep_search_v2/master_summary.json + top_10 from a few
// priority cells. 24 cells total; rule detail is populated for the "ship"
// cells and a representative amber, with the remaining cells carrying just
// the cell-level summary.

import type { CellDefinition, CellRule } from './v1'

const PRIORITY_CELLS_WITH_RULES: Record<string, CellRule[]> = {
  'Large-3m-POSITIVE': [
    {
      rule_id: 'QM_L3m_align3_lowvol',
      name: 'QM_L3m_align3_lowvol',
      archetype: 'quality_momentum',
      eli5:
        'Stocks that are simultaneously above their 30-week, 50-day, and 20-day moving averages with below-median realized vol tend to keep going for the next 3 months.',
      predicates_natural: [
        'rs_alignment_count >= 3',
        'realized_vol_60d <= 0.025',
        'log_med_tv_60d >= 16.5',
      ],
      predicates_dsl: {},
      ic_mean: 0.0416,
      ic_ir: 0.71,
      q_value: 0.0127,
      fric_adj_excess_mean_ann: 0.0071,
      gate_pass_count: 2,
      gate_total: 3,
      per_window_stability: [0.023, 0.007, -0.008],
      population_today: 23,
      population_today_iids: [],
    },
    {
      rule_id: 'DV_L3m_neg12m_dd5y_-70_-40',
      name: 'DV_L3m_neg12m_dd5y_-70_-40',
      archetype: 'deep_value',
      eli5:
        'Large caps with a 1Y drawdown between 40 and 70% AND negative 1Y RS — a deep base often precedes a multi-quarter rebound.',
      predicates_natural: [
        'drawdown_252d in (-0.70, -0.40)',
        'rs_pctile_252d < 0.20',
        'rs_pctile_63d > 0.40',
      ],
      predicates_dsl: {},
      ic_mean: 0.060,
      ic_ir: 0.58,
      q_value: 3.4e-9,
      fric_adj_excess_mean_ann: 0.0061,
      gate_pass_count: 2,
      gate_total: 3,
      per_window_stability: [0.045, 0.072, 0.063],
      population_today: 18,
      population_today_iids: [],
    },
    {
      rule_id: 'SRL_L3m_topsector',
      name: 'SRL_L3m_topsector',
      archetype: 'sector_relative_leadership',
      eli5:
        'Top-quartile RS stocks within sectors ranked in the top 5 (cross-sector) — the strongest names in the strongest sectors.',
      predicates_natural: [
        'sector_rank <= 5',
        'within_sector_rs_pctile >= 0.85',
        'breadth_pct_stage_2 >= 0.55',
      ],
      predicates_dsl: {},
      ic_mean: 0.054,
      ic_ir: 0.62,
      q_value: 0.008,
      fric_adj_excess_mean_ann: 0.012,
      gate_pass_count: 2,
      gate_total: 3,
      per_window_stability: [0.041, 0.058, 0.061],
      population_today: 31,
      population_today_iids: [],
    },
  ],
  'Large-6m-POSITIVE': [
    {
      rule_id: 'SRL2_L6m_rk90_sc5',
      name: 'SRL2_L6m_rk90_sc5',
      archetype: 'sector_relative_leadership',
      eli5:
        '6-month leadership within top-5 sectors — the highest-conviction "ride the leader" rule across the entire matrix.',
      predicates_natural: [
        'sector_rank <= 5',
        'rs_pctile_126d >= 0.90',
      ],
      predicates_dsl: {},
      ic_mean: 0.1545,
      ic_ir: 0.81,
      q_value: 0.0,
      fric_adj_excess_mean_ann: 0.0079,
      gate_pass_count: 3,
      gate_total: 3,
      per_window_stability: [0.142, 0.165, 0.157],
      population_today: 19,
      population_today_iids: [],
    },
  ],
  'Mid-12m-POSITIVE': [
    {
      rule_id: 'SRL_M12m_secrnk5_rk85_br55',
      name: 'SRL_M12m_secrnk5_rk85_br55',
      archetype: 'sector_relative_leadership',
      eli5:
        'Mid-caps in top-5 sectors with high RS and broad sector participation — the matrix\'s highest IC at 0.45.',
      predicates_natural: [
        'sector_rank <= 5',
        'rs_pctile_252d >= 0.85',
        'breadth_pct_stage_2 >= 0.55',
      ],
      predicates_dsl: {},
      ic_mean: 0.448,
      ic_ir: 0.91,
      q_value: 4.05e-6,
      fric_adj_excess_mean_ann: 0.936,
      gate_pass_count: 3,
      gate_total: 3,
      per_window_stability: [0.412, 0.461, 0.471],
      population_today: 12,
      population_today_iids: [],
    },
  ],
  'Mid-3m-POSITIVE': [
    {
      rule_id: 'BAB_M3m_beta_60_exvol_-3',
      name: 'BAB_M3m_beta_60_exvol_-3',
      archetype: 'bab_low_beta',
      eli5:
        'Lower-beta mid-caps deliver more bang per unit of risk — the classic "betting against beta" anomaly.',
      predicates_natural: [
        'beta_60d <= 0.85',
        'excess_vol_60d <= -0.03',
      ],
      predicates_dsl: {},
      ic_mean: 0.165,
      ic_ir: 0.74,
      q_value: 1.75e-11,
      fric_adj_excess_mean_ann: 0.0076,
      gate_pass_count: 3,
      gate_total: 3,
      per_window_stability: [0.151, 0.173, 0.169],
      population_today: 27,
      population_today_iids: [],
    },
  ],
  'Mid-6m-POSITIVE': [
    {
      rule_id: 'QM_M6m_rs6m_topq4_lowvol_22',
      name: 'QM_M6m_rs6m_topq4_lowvol_22',
      archetype: 'quality_momentum',
      eli5:
        '6-month quality-momentum on mid-caps: top-quartile 6M RS with sub-22% realized vol.',
      predicates_natural: [
        'rs_pctile_126d >= 0.75',
        'realized_vol_60d <= 0.022',
      ],
      predicates_dsl: {},
      ic_mean: 0.172,
      ic_ir: 0.79,
      q_value: 0.0,
      fric_adj_excess_mean_ann: 0.060,
      gate_pass_count: 3,
      gate_total: 3,
      per_window_stability: [0.158, 0.184, 0.171],
      population_today: 22,
      population_today_iids: [],
    },
  ],
  'Small-3m-POSITIVE': [
    {
      rule_id: 'SRL_S3m_secrnk3_rk85_br35',
      name: 'SRL_S3m_secrnk3_rk85_br35',
      archetype: 'sector_relative_leadership',
      eli5:
        'Small-caps in top-3 sectors with high RS — the cleanest small-cap leadership signal.',
      predicates_natural: [
        'sector_rank <= 3',
        'rs_pctile_63d >= 0.85',
        'breadth_pct_stage_2 >= 0.35',
      ],
      predicates_dsl: {},
      ic_mean: 0.241,
      ic_ir: 0.83,
      q_value: 4.4e-7,
      fric_adj_excess_mean_ann: 0.046,
      gate_pass_count: 3,
      gate_total: 3,
      per_window_stability: [0.218, 0.247, 0.258],
      population_today: 35,
      population_today_iids: [],
    },
  ],
  'Small-6m-POSITIVE': [
    {
      rule_id: 'SRL_S6m_secrnk3_rk85_br35',
      name: 'SRL_S6m_secrnk3_rk85_br35',
      archetype: 'sector_relative_leadership',
      eli5:
        '6M small-cap leadership within top-3 sectors — best-in-class small-cap signal.',
      predicates_natural: [
        'sector_rank <= 3',
        'rs_pctile_126d >= 0.85',
        'breadth_pct_stage_2 >= 0.35',
      ],
      predicates_dsl: {},
      ic_mean: 0.237,
      ic_ir: 0.80,
      q_value: 9.1e-7,
      fric_adj_excess_mean_ann: 0.182,
      gate_pass_count: 3,
      gate_total: 3,
      per_window_stability: [0.211, 0.243, 0.252],
      population_today: 28,
      population_today_iids: [],
    },
  ],
}

// Cell-level summaries, ordered to match the IA spec: Large/Mid/Small × 4 tenures × 2 directions.
const CELL_SUMMARIES: Omit<CellDefinition, 'rules'>[] = [
  // Large
  { cell_id: 'Large-1m-POSITIVE', tier: 'Large', tenure: '1m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 0, grade: 'red', ship_or_park: 'park_no_signal', reason: 'No candidate cleared the gate.', disclaimers_applicable: ['w3_thin_coverage', 'no_fundamentals'], best_rule_id: 'LE_L1m_vz_25_rs6m_pos', best_rule_ic: 0.344, best_rule_fric_adj_ann: -0.069, best_archetype: 'liquidity_expansion' },
  { cell_id: 'Large-1m-NEGATIVE', tier: 'Large', tenure: '1m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 3, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'OE_L1m_roc126_100', best_rule_ic: -0.068, best_rule_fric_adj_ann: -0.010, best_archetype: 'overextension' },
  { cell_id: 'Large-3m-POSITIVE', tier: 'Large', tenure: '3m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 2, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.060 > +0.04; cross-cell q=0.000.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'DV_L3m_neg12m_dd5y_-70_-40', best_rule_ic: 0.060, best_rule_fric_adj_ann: 0.006, best_archetype: 'deep_value' },
  { cell_id: 'Large-3m-NEGATIVE', tier: 'Large', tenure: '3m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 1, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'DVA_L3m_dd-50_negrs', best_rule_ic: -0.046, best_rule_fric_adj_ann: -0.012, best_archetype: 'deep_value_avoid' },
  { cell_id: 'Large-6m-POSITIVE', tier: 'Large', tenure: '6m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 17, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.155 > +0.05.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'SRL2_L6m_rk90_sc5', best_rule_ic: 0.155, best_rule_fric_adj_ann: 0.008, best_archetype: 'sector_relative_leadership' },
  { cell_id: 'Large-6m-NEGATIVE', tier: 'Large', tenure: '6m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 12, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'SBD_L6m_secrnk18_br20_rs85', best_rule_ic: -0.121, best_rule_fric_adj_ann: -0.010, best_archetype: 'sector_breakdown' },
  { cell_id: 'Large-12m-POSITIVE', tier: 'Large', tenure: '12m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 31, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.376 > +0.04.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'LE_L12m_vz252_10', best_rule_ic: 0.376, best_rule_fric_adj_ann: 0.064, best_archetype: 'liquidity_expansion' },
  { cell_id: 'Large-12m-NEGATIVE', tier: 'Large', tenure: '12m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 28, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'SDR_L12m_secrnk28_secvol20', best_rule_ic: -0.184, best_rule_fric_adj_ann: -0.016, best_archetype: 'sector_drag' },
  // Mid
  { cell_id: 'Mid-1m-POSITIVE', tier: 'Mid', tenure: '1m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 27, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.239 > +0.02.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'SRL_M1m_secrnk10_rk95_br55', best_rule_ic: 0.239, best_rule_fric_adj_ann: 0.039, best_archetype: 'sector_relative_leadership' },
  { cell_id: 'Mid-1m-NEGATIVE', tier: 'Mid', tenure: '1m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 8, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'SDR_M1m_secrnk28_secvol25', best_rule_ic: -0.076, best_rule_fric_adj_ann: -0.021, best_archetype: 'sector_drag' },
  { cell_id: 'Mid-3m-POSITIVE', tier: 'Mid', tenure: '3m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 49, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.165 > +0.04.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'BAB_M3m_beta_60_exvol_-3', best_rule_ic: 0.165, best_rule_fric_adj_ann: 0.008, best_archetype: 'bab_low_beta' },
  { cell_id: 'Mid-3m-NEGATIVE', tier: 'Mid', tenure: '3m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 8, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'SDR_M3m_secrnk28_secvol20', best_rule_ic: -0.291, best_rule_fric_adj_ann: -0.029, best_archetype: 'sector_drag' },
  { cell_id: 'Mid-6m-POSITIVE', tier: 'Mid', tenure: '6m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 33, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.172 > +0.05.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'QM_M6m_rs6m_topq4_lowvol_22', best_rule_ic: 0.172, best_rule_fric_adj_ann: 0.060, best_archetype: 'quality_momentum' },
  { cell_id: 'Mid-6m-NEGATIVE', tier: 'Mid', tenure: '6m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 6, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'SDR_M6m_secrnk28_secvol20', best_rule_ic: -0.315, best_rule_fric_adj_ann: -0.031, best_archetype: 'sector_drag' },
  { cell_id: 'Mid-12m-POSITIVE', tier: 'Mid', tenure: '12m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 70, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.448 > +0.04.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'SRL_M12m_secrnk5_rk85_br55', best_rule_ic: 0.448, best_rule_fric_adj_ann: 0.936, best_archetype: 'sector_relative_leadership' },
  { cell_id: 'Mid-12m-NEGATIVE', tier: 'Mid', tenure: '12m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 14, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'WQ_M12m_dvol_25', best_rule_ic: -0.169, best_rule_fric_adj_ann: -0.049, best_archetype: 'weak_quality' },
  // Small
  { cell_id: 'Small-1m-POSITIVE', tier: 'Small', tenure: '1m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 13, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.180 > +0.02.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'OBV_S1m_12m_topq10', best_rule_ic: 0.180, best_rule_fric_adj_ann: 0.013, best_archetype: 'obv_thrust' },
  { cell_id: 'Small-1m-NEGATIVE', tier: 'Small', tenure: '1m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 1, grade: 'amber', ship_or_park: 'park_borderline', reason: 'Validated within-cell but cross-cell q=0.37.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'SDR_S1m_secrnk28_cross20', best_rule_ic: -0.055, best_rule_fric_adj_ann: -0.008, best_archetype: 'sector_drag' },
  { cell_id: 'Small-3m-POSITIVE', tier: 'Small', tenure: '3m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 56, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.241 > +0.04.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'SRL_S3m_secrnk3_rk85_br35', best_rule_ic: 0.241, best_rule_fric_adj_ann: 0.046, best_archetype: 'sector_relative_leadership' },
  { cell_id: 'Small-3m-NEGATIVE', tier: 'Small', tenure: '3m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 8, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'SBD_S3m_secrnk22_br15_rs90', best_rule_ic: -0.185, best_rule_fric_adj_ann: -0.048, best_archetype: 'sector_breakdown' },
  { cell_id: 'Small-6m-POSITIVE', tier: 'Small', tenure: '6m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 62, grade: 'green', ship_or_park: 'ship', reason: 'Validated; IC +0.237 > +0.05.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'SRL_S6m_secrnk3_rk85_br35', best_rule_ic: 0.237, best_rule_fric_adj_ann: 0.182, best_archetype: 'sector_relative_leadership' },
  { cell_id: 'Small-6m-NEGATIVE', tier: 'Small', tenure: '6m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 3, grade: 'amber', ship_or_park: 'park_survivorship', reason: 'Passes BH-FDR but cache is survivor-only.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'SBD_S6m_secrnk25_br15_rs90', best_rule_ic: -0.246, best_rule_fric_adj_ann: -0.067, best_archetype: 'sector_breakdown' },
  { cell_id: 'Small-12m-POSITIVE', tier: 'Small', tenure: '12m', direction: 'POSITIVE', n_candidates: 321, n_gate_pass: 54, grade: 'amber', ship_or_park: 'park_borderline', reason: 'Validated within-cell but cross-cell q=0.16 is borderline.', disclaimers_applicable: ['w3_thin_coverage'], best_rule_id: 'LE_S12m_vz252_10', best_rule_ic: 0.140, best_rule_fric_adj_ann: 0.496, best_archetype: 'liquidity_expansion' },
  { cell_id: 'Small-12m-NEGATIVE', tier: 'Small', tenure: '12m', direction: 'NEGATIVE', n_candidates: 191, n_gate_pass: 0, grade: 'red', ship_or_park: 'park_no_signal', reason: 'No candidate cleared the gate.', disclaimers_applicable: ['survivorship_bias'], best_rule_id: 'VS_S12m_brkdwn50_-2', best_rule_ic: -0.330, best_rule_fric_adj_ann: 0.149, best_archetype: 'volatility_spike' },
]

function hydrateCell(summary: typeof CELL_SUMMARIES[number]): CellDefinition {
  return {
    ...summary,
    rules: PRIORITY_CELLS_WITH_RULES[summary.cell_id] ?? [],
  }
}

export function getDemoCellDefinitions(): CellDefinition[] {
  return CELL_SUMMARIES.map(hydrateCell)
}

export function getDemoCellDefinition(cellId: string): CellDefinition | null {
  const found = CELL_SUMMARIES.find(c => c.cell_id === cellId)
  if (!found) return null
  return hydrateCell(found)
}
