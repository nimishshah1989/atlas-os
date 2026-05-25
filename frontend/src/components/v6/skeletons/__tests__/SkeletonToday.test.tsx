// frontend/src/components/v6/skeletons/__tests__/SkeletonToday.test.tsx
// Schema: 2 top-level children (header strip + body grid containing 3-col cards, sector ladder, signal calls)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonToday } from '../SkeletonToday'

describe('SkeletonToday', () => {
  it('renders page-root testid', () => {
    render(<SkeletonToday />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 2 top-level children (header strip + body grid)', () => {
    render(<SkeletonToday />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(2)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonToday className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
