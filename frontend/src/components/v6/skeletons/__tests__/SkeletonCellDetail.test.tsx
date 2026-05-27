// frontend/src/components/v6/skeletons/__tests__/SkeletonCellDetail.test.tsx
// Schema: 2 top-level children (header strip with IC stats + body with tabs, window backtests, predicates)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonCellDetail } from '../SkeletonCellDetail'

describe('SkeletonCellDetail', () => {
  it('renders page-root testid', () => {
    render(<SkeletonCellDetail />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 2 top-level children (header strip + body sections)', () => {
    render(<SkeletonCellDetail />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(2)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonCellDetail className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
