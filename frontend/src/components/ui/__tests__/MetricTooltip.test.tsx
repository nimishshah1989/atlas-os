import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MetricTooltip } from '../MetricTooltip'

describe('MetricTooltip', () => {
  it('renders the info button', () => {
    render(<MetricTooltip metricKey="rs_pctile_3m" />)
    expect(screen.getByRole('button', { name: /info/i })).toBeInTheDocument()
  })

  it('renders info button for every defined metric key', () => {
    const keys: Parameters<typeof MetricTooltip>[0]['metricKey'][] = [
      'ret_1m', 'ret_3m', 'ret_6m', 'ret_1y',
      'realized_vol_63', 'avg_volume_20', 'days_in_state',
      'rs_state', 'momentum_state', 'risk_state', 'volume_state',
      'position_size_pct', 'extension', 'drawdown_from_peak', 'gold_rs', 'weinstein_gate',
    ]
    for (const key of keys) {
      const { unmount } = render(<MetricTooltip metricKey={key} />)
      expect(screen.getByRole('button', { name: /info/i })).toBeInTheDocument()
      unmount()
    }
  })
})
