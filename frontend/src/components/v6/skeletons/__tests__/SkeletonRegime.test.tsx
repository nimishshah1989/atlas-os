// frontend/src/components/v6/skeletons/__tests__/SkeletonRegime.test.tsx
// Schema: 3 top-level children (header strip with 12w strip, body sections, classifier explainer)

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkeletonRegime } from '../SkeletonRegime'

describe('SkeletonRegime', () => {
  it('renders page-root testid', () => {
    render(<SkeletonRegime />)
    expect(screen.getByTestId('page-root')).toBeTruthy()
  })

  it('page-root has exactly 3 top-level children (header, body, classifier)', () => {
    render(<SkeletonRegime />)
    const root = screen.getByTestId('page-root')
    expect(root.children.length).toBe(3)
  })

  it('accepts className prop without error', () => {
    const { container } = render(<SkeletonRegime className="test-class" />)
    expect(container.querySelector('.test-class')).toBeTruthy()
  })
})
