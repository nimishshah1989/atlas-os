// frontend/src/components/v6/skeletons/__tests__/SkeletonStockDetail.test.tsx
// Schema: 2 top-level children (hero header strip + body grid containing tab nav and content)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonStockDetail } from '../SkeletonStockDetail'

describe('SkeletonStockDetail', () => {
  it('renders page-root testid', () => {
    render(<SkeletonStockDetail />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 2 top-level children (header strip + body grid)', () => {
    render(<SkeletonStockDetail />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(2)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonStockDetail className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
