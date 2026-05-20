// src/lib/stage-labels.ts
// Shared human-readable label maps for Weinstein engine states and instrument universe values.
// Used by PolicyPanel, DeteriorationPanel, and any other consumer that must not show raw DB enums.

export const STAGE_LABEL: Record<string, string> = {
  stage_1: 'Stage 1 Base',
  stage_2a: 'Stage 2A',
  stage_2b: 'Stage 2B',
  stage_2c: 'Stage 2C',
  stage_3: 'Stage 3 Top',
  stage_4: 'Stage 4 Decline',
  uninvestable: 'Uninvestable',
}

export const INSTRUMENT_UNIVERSE_LABEL: Record<string, string> = {
  direct_equity: 'Direct Equity',
  etf: 'ETF',
  mutual_fund: 'Mutual Fund',
  mixed: 'Mixed',
}

/** Translate a raw engine state to its display label. Falls back to the raw value if unknown. */
export function stageLabel(raw: string | null | undefined): string {
  if (raw == null) return '—'
  return STAGE_LABEL[raw] ?? raw
}

/** Translate a raw instrument universe enum to its display label. Falls back to the raw value. */
export function instrumentUniverseLabel(raw: string | null | undefined): string {
  if (raw == null) return '—'
  return INSTRUMENT_UNIVERSE_LABEL[raw] ?? raw
}
