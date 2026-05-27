// frontend/src/components/v6/skeletons/__tests__/SkeletonScreener.test.tsx
// Schema: 2 top-level children (header strip + body grid with filter panel left + results table right)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonScreener } from '../SkeletonScreener'

describe('SkeletonScreener', () => {
  it('renders page-root testid', () => {
    render(<SkeletonScreener />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 2 top-level children (header strip + body grid)', () => {
    render(<SkeletonScreener />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(2)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonScreener className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
