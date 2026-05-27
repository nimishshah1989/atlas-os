// frontend/src/components/v6/skeletons/__tests__/SkeletonFunds.test.tsx
// Schema: 4 top-level children (header strip, industry snapshot, charts, ranked table)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonFunds } from '../SkeletonFunds'

describe('SkeletonFunds', () => {
  it('renders page-root testid', () => {
    render(<SkeletonFunds />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 4 top-level children (header, snapshot, charts, table)', () => {
    render(<SkeletonFunds />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(4)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonFunds className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
