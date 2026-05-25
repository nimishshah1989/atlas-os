// frontend/src/components/v6/skeletons/__tests__/SkeletonSectors.test.tsx
// Schema: 4 top-level children (header strip, industry overview, charts, ranked ladder)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonSectors } from '../SkeletonSectors'

describe('SkeletonSectors', () => {
  it('renders page-root testid', () => {
    render(<SkeletonSectors />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 4 top-level children (header, overview, charts, ladder)', () => {
    render(<SkeletonSectors />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(4)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonSectors className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
