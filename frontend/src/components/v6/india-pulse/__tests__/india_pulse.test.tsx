// frontend/src/components/v6/india-pulse/__tests__/india_pulse.test.tsx
//
// Tests for India Pulse page components.
// Covers: helpers (pure functions), HeroStrip, HeadlineIndices, BreadthTable,
//         VolatilitySection, TierLeadership, SectorHeatmap rendering.
//
// Recharts mocked via vi.mock to avoid jsdom canvas issues.

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

// ---------------------------------------------------------------------------
// Recharts mock — minimal stubs so components render without canvas errors
// ---------------------------------------------------------------------------

vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: ReactNode }) => <svg data-testid="line-chart">{children}</svg>,
  BarChart: ({ children }: { children: ReactNode }) => <svg data-testid="bar-chart">{children}</svg>,
  Line: () => <line data-testid="line" />,
  Bar: ({ children }: { children: ReactNode }) => <g data-testid="bar">{children}</g>,
  Cell: ({ fill }: { fill: string }) => <rect data-fill={fill} />,
  XAxis: () => <g data-testid="xaxis" />,
  YAxis: () => <g data-testid="yaxis" />,
  CartesianGrid: () => <g data-testid="grid" />,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="rc">{children}</div>
  ),
  ReferenceLine: () => <line data-testid="refline" />,
}))

import {
  fmtPct,
  fmtZ,
  fmtPctAbs,
  fmtNum,
  fmtCrore,
  colorClass,
  sectorColorClass,
  fmtDateDMY,
} from '../helpers'
import { HeroStrip } from '../HeroStrip'
import { HeadlineIndices } from '../HeadlineIndices'
import { BreadthTable } from '../BreadthTable'
import { VolatilitySection } from '../VolatilitySection'
import { TierLeadership } from '../TierLeadership'
import { SectorHeatmap } from '../SectorHeatmap'
import type {
  HeadlineIndexItem,
  BreadthRow,
  SectorHeatmapItem,
  TierLeadership as TierLeadershipData,
} from '@/lib/queries/v6/india_pulse'

// ---------------------------------------------------------------------------
// Helpers — pure functions, no DOM
// ---------------------------------------------------------------------------

describe('helpers', () => {
  describe('fmtPct', () => {
    it('formats positive decimal fraction with + sign', () => {
      expect(fmtPct(0.0418)).toBe('+4.2%')
    })
    it('formats negative decimal fraction with − sign', () => {
      expect(fmtPct(-0.0841)).toBe('−8.4%')
    })
    it('returns — for null', () => {
      expect(fmtPct(null)).toBe('—')
    })
    it('zero renders as +0.0%', () => {
      expect(fmtPct(0)).toBe('+0.0%')
    })
  })

  describe('fmtZ', () => {
    it('formats negative Z-score with − sign', () => {
      expect(fmtZ(-0.84)).toBe('−0.84')
    })
    it('formats positive Z-score with + sign', () => {
      expect(fmtZ(1.23)).toBe('+1.23')
    })
    it('returns — for null', () => {
      expect(fmtZ(null)).toBe('—')
    })
  })

  describe('fmtPctAbs', () => {
    it('formats fraction as percentage without sign', () => {
      expect(fmtPctAbs(0.42)).toBe('42.0%')
    })
    it('returns — for null', () => {
      expect(fmtPctAbs(null)).toBe('—')
    })
  })

  describe('fmtNum', () => {
    it('formats number with 2 decimals by default', () => {
      expect(fmtNum(18.4)).toBe('18.40')
    })
    it('returns — for null', () => {
      expect(fmtNum(null)).toBe('—')
    })
    it('formats with custom decimals', () => {
      expect(fmtNum(18.456, 1)).toBe('18.5')
    })
  })

  describe('fmtCrore', () => {
    it('formats positive large crore value with + and cr', () => {
      const result = fmtCrore(41200)
      expect(result).toContain('+')
      expect(result).toContain('cr')
    })
    it('formats negative crore value with − and cr', () => {
      const result = fmtCrore(-38400)
      expect(result).toContain('−')
      expect(result).toContain('cr')
    })
    it('returns — for null', () => {
      expect(fmtCrore(null)).toBe('—')
    })
  })

  describe('colorClass', () => {
    it('returns text-signal-pos for positive value', () => {
      expect(colorClass(1.5)).toBe('text-signal-pos')
    })
    it('returns text-signal-neg for negative value', () => {
      expect(colorClass(-0.5)).toBe('text-signal-neg')
    })
    it('returns text-ink-tertiary for null', () => {
      expect(colorClass(null)).toBe('text-ink-tertiary')
    })
  })

  describe('sectorColorClass', () => {
    it('returns strong positive class for >3% rs', () => {
      expect(sectorColorClass(0.031)).toContain('rgba(47,107,67,0.55)')
    })
    it('returns medium positive class for ~2.5% rs (between 1.5% and 3%)', () => {
      expect(sectorColorClass(0.025)).toContain('rgba(47,107,67,0.30)')
    })
    it('returns strong negative class for <-3% rs', () => {
      expect(sectorColorClass(-0.031)).toContain('rgba(176,73,44,0.55)')
    })
    it('returns flat/paper class for near-zero rs', () => {
      expect(sectorColorClass(0.001)).toContain('paper')
    })
    it('returns paper/flat class for null', () => {
      expect(sectorColorClass(null)).toContain('paper')
    })
  })

  describe('fmtDateDMY', () => {
    it('formats ISO date to DD-MMM-YYYY', () => {
      const result = fmtDateDMY('2026-05-27')
      expect(result).toBe('27-May-2026')
    })
    it('returns — for null', () => {
      expect(fmtDateDMY(null)).toBe('—')
    })
  })
})

// ---------------------------------------------------------------------------
// HeroStrip
// ---------------------------------------------------------------------------

describe('HeroStrip', () => {
  it('renders all 4 hero tile labels', () => {
    render(
      <HeroStrip
        data={{
          smallcap_rs_z: -0.84,
          breadth_pct_above_200dma: 0.42,
          india_vix: 18.4,
          cross_section_dispersion: 0.087,
        }}
      />,
    )
    expect(screen.getByText('Small-cap RS Z-score')).toBeInTheDocument()
    expect(screen.getByText('Breadth — % above 200 DMA')).toBeInTheDocument()
    expect(screen.getByText('India VIX')).toBeInTheDocument()
    expect(screen.getByText('Cross-section dispersion')).toBeInTheDocument()
  })

  it('renders — for null values without crashing', () => {
    render(
      <HeroStrip
        data={{
          smallcap_rs_z: null,
          breadth_pct_above_200dma: null,
          india_vix: null,
          cross_section_dispersion: null,
        }}
      />,
    )
    // Each tile shows a dash for null
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(4)
  })

  it('renders negative Z-score with minus sign', () => {
    render(
      <HeroStrip
        data={{
          smallcap_rs_z: -0.84,
          breadth_pct_above_200dma: 0.42,
          india_vix: 18.4,
          cross_section_dispersion: 0.087,
        }}
      />,
    )
    expect(screen.getByText('−0.84')).toBeInTheDocument()
  })

  it('renders breadth as percentage', () => {
    render(
      <HeroStrip
        data={{
          smallcap_rs_z: -0.84,
          breadth_pct_above_200dma: 0.42,
          india_vix: 18.4,
          cross_section_dispersion: 0.087,
        }}
      />,
    )
    expect(screen.getByText('42%')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// HeadlineIndices
// ---------------------------------------------------------------------------

const SAMPLE_INDICES: HeadlineIndexItem[] = [
  {
    index_code: 'NIFTY 50',
    label: 'Nifty 50',
    close: 24832,
    ret_1d: -0.0062,
    ret_1w: -0.018,
    ret_1m: -0.041,
    ret_3m: 0.018,
    ret_6m: 0.126,
    rs_3m_vs_nifty500: 0.056,
  },
  {
    index_code: 'NIFTY 500',
    label: 'Nifty 500',
    close: 22710,
    ret_1d: -0.0087,
    ret_1w: null,
    ret_1m: -0.043,
    ret_3m: -0.014,
    ret_6m: 0.096,
    rs_3m_vs_nifty500: null,
  },
]

describe('HeadlineIndices', () => {
  it('renders index labels', () => {
    render(<HeadlineIndices indices={SAMPLE_INDICES} />)
    expect(screen.getByText('Nifty 50')).toBeInTheDocument()
    expect(screen.getByText('Nifty 500')).toBeInTheDocument()
  })

  it('renders close price formatted Indian style', () => {
    render(<HeadlineIndices indices={SAMPLE_INDICES} />)
    expect(screen.getByText('24,832')).toBeInTheDocument()
  })

  it('renders RS baseline text for Nifty 500', () => {
    render(<HeadlineIndices indices={SAMPLE_INDICES} />)
    expect(screen.getByText('The baseline (≡)')).toBeInTheDocument()
  })

  it('renders RS vs Nifty 500 label for non-baseline index', () => {
    render(<HeadlineIndices indices={SAMPLE_INDICES} />)
    expect(screen.getByText('RS vs Nifty 500 · 3M')).toBeInTheDocument()
  })

  it('renders empty state when indices is empty', () => {
    render(<HeadlineIndices indices={[]} />)
    expect(screen.getByText('No headline index data available.')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// BreadthTable
// ---------------------------------------------------------------------------

const SAMPLE_BREADTH: BreadthRow[] = [
  {
    metric: 'pct_above_200ema',
    label: '% above 200 EMA',
    today: 42,
    delta_1w: -3,
    delta_1m: -16,
    delta_3m: -29,
    data_gap: false,
  },
  {
    metric: 'pct_above_100ema',
    label: '% above 100 EMA',
    today: null,
    delta_1w: null,
    delta_1m: null,
    delta_3m: null,
    data_gap: true,
  },
  {
    metric: 'mcclellan',
    label: 'McClellan oscillator',
    today: -84,
    delta_1w: -52,
    delta_1m: 12,
    delta_3m: 68,
    data_gap: false,
  },
]

describe('BreadthTable', () => {
  it('renders breadth measure labels', () => {
    render(<BreadthTable rows={SAMPLE_BREADTH} />)
    expect(screen.getByText('% above 200 EMA')).toBeInTheDocument()
    expect(screen.getByText('% above 100 EMA')).toBeInTheDocument()
  })

  it('renders today value for non-gap row', () => {
    render(<BreadthTable rows={SAMPLE_BREADTH} />)
    expect(screen.getByText('42%')).toBeInTheDocument()
  })

  it('shows Pipeline gap for data_gap rows', () => {
    render(<BreadthTable rows={SAMPLE_BREADTH} />)
    expect(screen.getByText('Pipeline gap')).toBeInTheDocument()
  })

  it('renders Oversold chip for deep McClellan', () => {
    render(<BreadthTable rows={SAMPLE_BREADTH} />)
    expect(screen.getByText('Oversold')).toBeInTheDocument()
  })

  it('renders empty state when rows is empty', () => {
    render(<BreadthTable rows={[]} />)
    expect(screen.getByText('No breadth data available.')).toBeInTheDocument()
  })
})

// Regression: mv_india_pulse v2 (migration 122) emits pct_above_{20,50,100,200}EMA
// — NOT the *dma keys the component originally hardcoded. With dma-only handling the
// EMA breadth rows rendered a bare number (no %), no progress bar, and no "reads as"
// interpretation. These fixtures use the REAL MV metric keys.
const MV_EMA_BREADTH: BreadthRow[] = [
  { metric: 'pct_above_20ema', label: '% above 20 EMA', today: 50.4, delta_1w: 2, delta_1m: -5, delta_3m: -10, data_gap: false },
  { metric: 'pct_above_200ema', label: '% above 200 EMA', today: 46.9, delta_1w: -3, delta_1m: -16, delta_3m: -29, data_gap: false },
]

describe('BreadthTable — real MV ema keys (regression)', () => {
  it('formats pct_above_*ema rows as percentages, not bare numbers', () => {
    render(<BreadthTable rows={MV_EMA_BREADTH} />)
    expect(screen.getByText('47%')).toBeInTheDocument() // 46.9 -> 47%
    expect(screen.getByText('50%')).toBeInTheDocument() // 50.4 -> 50%
  })

  it('renders a "reads as" interpretation for an ema breadth row (not the em-dash default)', () => {
    render(<BreadthTable rows={MV_EMA_BREADTH} />)
    // 200 EMA at 46.9 (<50) => below-half-line warning text
    expect(screen.getByText(/below half-line/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// VolatilitySection
// ---------------------------------------------------------------------------

describe('VolatilitySection', () => {
  it('renders all three volatility card titles', () => {
    render(
      <VolatilitySection
        data={{ vix_spot: 18.4, vix_5y_pct: 0.68, vix_term_structure: 0.41 }}
      />,
    )
    expect(screen.getByText('Spot India VIX')).toBeInTheDocument()
    expect(screen.getByText('5-year percentile')).toBeInTheDocument()
    expect(screen.getByText(/Term structure/)).toBeInTheDocument()
  })

  it('renders VIX spot value with 1 decimal', () => {
    render(
      <VolatilitySection
        data={{ vix_spot: 18.4, vix_5y_pct: 0.68, vix_term_structure: 0.41 }}
      />,
    )
    expect(screen.getByText('18.40')).toBeInTheDocument()
  })

  it('renders 68th percentile text', () => {
    render(
      <VolatilitySection
        data={{ vix_spot: 18.4, vix_5y_pct: 0.68, vix_term_structure: 0.41 }}
      />,
    )
    // Both the "68th" numeric display and the narrative text include "68"
    const matches = screen.getAllByText((content) => content.includes('68'))
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })

  it('renders gracefully with all nulls', () => {
    render(
      <VolatilitySection
        data={{ vix_spot: null, vix_5y_pct: null, vix_term_structure: null }}
      />,
    )
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
  })

  it('renders positive term structure with + sign', () => {
    render(
      <VolatilitySection
        data={{ vix_spot: 18.4, vix_5y_pct: 0.68, vix_term_structure: 0.41 }}
      />,
    )
    expect(screen.getByText('+0.41')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// TierLeadership
// ---------------------------------------------------------------------------

const SAMPLE_TIER: TierLeadershipData = {
  returns_table: [
    { window: '1w', sc: -0.021, mc: -0.013, lc: -0.006, sc_lc_spread: -0.015, mc_lc_spread: -0.007 },
    { window: '3m', sc: -0.087, mc: -0.042, lc: 0.008, sc_lc_spread: -0.095, mc_lc_spread: -0.050 },
  ],
  smallcap_rs_z: -0.84,
}

describe('TierLeadership', () => {
  it('renders the returns table section title', () => {
    render(<TierLeadership tier_leadership={SAMPLE_TIER} />)
    expect(screen.getByText('Tier returns · trailing windows')).toBeInTheDocument()
  })

  it('renders smallcap Z-score label', () => {
    render(<TierLeadership tier_leadership={SAMPLE_TIER} />)
    expect(screen.getByText('Smallcap 250 RS Z-score (vs Nifty 100)')).toBeInTheDocument()
  })

  it('renders Z-score value with sign', () => {
    render(<TierLeadership tier_leadership={SAMPLE_TIER} />)
    expect(screen.getByText('−0.84')).toBeInTheDocument()
  })

  it('renders null state without crashing', () => {
    render(<TierLeadership tier_leadership={null} />)
    expect(screen.getByText('No tier leadership data available.')).toBeInTheDocument()
  })

  it('renders window labels in the returns table', () => {
    render(<TierLeadership tier_leadership={SAMPLE_TIER} />)
    expect(screen.getByText('1 week')).toBeInTheDocument()
    expect(screen.getByText('3 months')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// SectorHeatmap
// ---------------------------------------------------------------------------

const SAMPLE_SECTORS: SectorHeatmapItem[] = [
  { sector_name: 'Energy', rs_1w: 0.034, ret_1m: 0.021, ret_3m: 0.08 },
  { sector_name: 'PSU Bank', rs_1w: -0.031, ret_1m: -0.04, ret_3m: -0.12 },
  { sector_name: 'FMCG', rs_1w: 0.001, ret_1m: 0.005, ret_3m: 0.02 },
]

describe('SectorHeatmap', () => {
  it('renders sector names', () => {
    render(<SectorHeatmap sectors={SAMPLE_SECTORS} />)
    expect(screen.getByText('Energy')).toBeInTheDocument()
    expect(screen.getByText('PSU Bank')).toBeInTheDocument()
    expect(screen.getByText('FMCG')).toBeInTheDocument()
  })

  it('renders window toggle buttons', () => {
    render(<SectorHeatmap sectors={SAMPLE_SECTORS} />)
    expect(screen.getByText('1W')).toBeInTheDocument()
    expect(screen.getByText('1M')).toBeInTheDocument()
    expect(screen.getByText('3M')).toBeInTheDocument()
  })

  it('renders empty state when sectors is empty', () => {
    render(<SectorHeatmap sectors={[]} />)
    expect(screen.getByText('No sector heatmap data available.')).toBeInTheDocument()
  })

  it('renders colour scale legend', () => {
    render(<SectorHeatmap sectors={SAMPLE_SECTORS} />)
    expect(screen.getByText('Colour scale:')).toBeInTheDocument()
  })

  it('renders Open Sectors link', () => {
    render(<SectorHeatmap sectors={SAMPLE_SECTORS} />)
    expect(screen.getByText('Open Sectors →')).toBeInTheDocument()
  })
})
