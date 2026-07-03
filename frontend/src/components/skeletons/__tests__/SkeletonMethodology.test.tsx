// frontend/src/components/skeletons/__tests__/SkeletonMethodology.test.tsx
// Schema: 2 top-level children (header strip + body with ClosedLoopDiagram area + 5 explainer sections)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonMethodology } from '../SkeletonMethodology'

describe('SkeletonMethodology', () => {
  it('renders page-root testid', () => {
    render(<SkeletonMethodology />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 2 top-level children (header strip + body sections)', () => {
    render(<SkeletonMethodology />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(2)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonMethodology className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
