/**
 * MultiBenchmarkRSWaterfall.test.tsx
 *
 * 5 test cases per tighter Opus acceptance criteria:
 *   1. Full data (with Gold, positive stock): 5 <rect> elements, 4 signal-pos, 1 signal-neg
 *   2. Attribution sentence exact string match
 *   3. Without Gold: 4 bars rendered
 *   4. All negatives: all 5 bars signal-neg
 *   5. ARIA label present
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

// ---------------------------------------------------------------------------
// Recharts mock — Cell renders a <rect> with data-fill-type for assertions
// ---------------------------------------------------------------------------

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="rc">{children}</div>
  ),
  BarChart: ({ children }: { children: ReactNode }) => (
    <svg data-testid="bar-chart">{children}</svg>
  ),
  Bar: ({ children }: { children: ReactNode }) => (
    <g data-testid="bar">{children}</g>
  ),
  Cell: ({
    fill,
    'data-fill-type': fillType,
  }: {
    fill?: string
    'data-fill-type'?: string
  }) => <rect data-fill-type={fillType} fill={fill} />,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ReferenceLine: () => null,
}))

// Import AFTER mock is set up
import {
  MultiBenchmarkRSWaterfall,
  buildAttributionSentence,
  FILL_POS,
  FILL_NEG,
} from '../MultiBenchmarkRSWaterfall'
import type { WaterfallInput } from '../MultiBenchmarkRSWaterfall'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/**
 * Baseline with Gold: stock=18.4, cohort=6.8, nifty500=8.4, nifty50=11.2, gold=-14.6
 * All positive except Gold.
 */
const WITH_GOLD: WaterfallInput = {
  stock_return:   '18.4',
  cohort_return:  '6.8',
  nifty500_return: '8.4',
  nifty50_return:  '11.2',
  gold_return:    '-14.6',
  tenure: '12m',
}

const WITHOUT_GOLD: WaterfallInput = {
  ...WITH_GOLD,
  gold_return: null,
}

const ALL_NEGATIVE: WaterfallInput = {
  stock_return:   '-5.0',
  cohort_return:  '-3.0',
  nifty500_return: '-4.0',
  nifty50_return:  '-2.0',
  gold_return:    '-8.0',
  tenure: '1m',
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MultiBenchmarkRSWaterfall', () => {

  // Test 1: 5 <rect> elements, 4 signal-pos, 1 signal-neg (gold)
  it('renders 5 rect elements with 4 signal-pos and 1 signal-neg when gold is negative', () => {
    const { container } = render(<MultiBenchmarkRSWaterfall data={WITH_GOLD} />)
    const rects = container.querySelectorAll('rect')
    expect(rects).toHaveLength(5)

    const fillTypes = Array.from(rects).map(r => r.getAttribute('data-fill-type'))
    const posCount = fillTypes.filter(f => f === FILL_POS).length
    const negCount = fillTypes.filter(f => f === FILL_NEG).length

    expect(posCount).toBe(4)
    expect(negCount).toBe(1)
  })

  // Test 2: Attribution sentence exact string match
  it('renders correct attribution sentence for the canonical example', () => {
    render(<MultiBenchmarkRSWaterfall data={WITH_GOLD} />)
    const el = screen.getByTestId('attribution-summary')
    // Whitespace-normalize the text content
    const text = el.textContent?.replace(/\s+/g, ' ').trim() ?? ''
    expect(text).toBe(
      'Nifty 500 beat Nifty 50 by +2.8pp → Cohort added +1.6pp → Stock added +6.8pp on top',
    )
  })

  // Test 3: Without Gold — 4 bars
  it('renders 4 rect elements when gold_return is null', () => {
    const { container } = render(<MultiBenchmarkRSWaterfall data={WITHOUT_GOLD} />)
    const rects = container.querySelectorAll('rect')
    expect(rects).toHaveLength(4)
  })

  // Test 4: All negatives — all 5 bars signal-neg
  it('colors all 5 bars signal-neg when all returns are negative', () => {
    const { container } = render(<MultiBenchmarkRSWaterfall data={ALL_NEGATIVE} />)
    const rects = container.querySelectorAll('rect')
    expect(rects).toHaveLength(5)
    const fillTypes = Array.from(rects).map(r => r.getAttribute('data-fill-type'))
    expect(fillTypes.every(f => f === FILL_NEG)).toBe(true)
  })

  // Test 5: ARIA label present
  it('renders an aria-label on the chart container', () => {
    const { container } = render(<MultiBenchmarkRSWaterfall data={WITH_GOLD} />)
    const wrapper = container.firstElementChild
    expect(wrapper?.getAttribute('aria-label')).toBeTruthy()
    expect(wrapper?.getAttribute('aria-label')).toContain('12m')
  })

})

// ---------------------------------------------------------------------------
// Pure function tests for buildAttributionSentence
// ---------------------------------------------------------------------------

describe('buildAttributionSentence', () => {
  it('produces the canonical attribution string', () => {
    const result = buildAttributionSentence(18.4, 6.8, 8.4, 11.2)
    expect(result).toBe(
      'Nifty 500 beat Nifty 50 by +2.8pp → Cohort added +1.6pp → Stock added +6.8pp on top',
    )
  })

  it('handles negative deltas with minus sign', () => {
    // nifty50=5, nifty500=8: nifty500 "beat" nifty50 by 5-8=-3pp (negative)
    const result = buildAttributionSentence(10, 5, 8, 5)
    expect(result).toContain('-3.0pp')
  })
})
