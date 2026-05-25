// frontend/src/components/v6/skeletons/__tests__/SkeletonMatrix.test.tsx
// Schema: 3 top-level children (header strip, body grid, footer)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonMatrix } from '../SkeletonMatrix'

describe('SkeletonMatrix', () => {
  it('renders page-root testid', () => {
    render(<SkeletonMatrix />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 3 top-level children (header, grid, footer)', () => {
    render(<SkeletonMatrix />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(3)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonMatrix className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
