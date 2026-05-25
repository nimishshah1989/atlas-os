// frontend/src/components/v6/skeletons/__tests__/SkeletonSectorDetail.test.tsx
// Schema: 2 top-level children (header strip + body containing breadth panel, bubble, constituent table)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonSectorDetail } from '../SkeletonSectorDetail'

describe('SkeletonSectorDetail', () => {
  it('renders page-root testid', () => {
    render(<SkeletonSectorDetail />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 2 top-level children (header strip + body sections)', () => {
    render(<SkeletonSectorDetail />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(2)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonSectorDetail className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
