// frontend/src/components/v6/skeletons/__tests__/SkeletonETFDetail.test.tsx
// Schema: 2 top-level children (header strip + tab nav with body containing rank decomp + waterfall)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonETFDetail } from '../SkeletonETFDetail'

describe('SkeletonETFDetail', () => {
  it('renders page-root testid', () => {
    render(<SkeletonETFDetail />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 2 top-level children (header strip + body)', () => {
    render(<SkeletonETFDetail />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(2)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonETFDetail className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
