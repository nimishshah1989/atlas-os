// frontend/src/components/skeletons/__tests__/Shimmer.test.tsx

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Shimmer } from '../Shimmer'

describe('Shimmer', () => {
  it('renders a decorative presentation element', () => {
    const { container } = render(<Shimmer />)
    const el = container.querySelector('[role="presentation"]')
    expect(el).toBeTruthy()
  })

  it('is hidden from screen readers via aria-hidden', () => {
    const { container } = render(<Shimmer />)
    const el = container.querySelector('[aria-hidden="true"]')
    expect(el).toBeTruthy()
  })

  it('applies custom width + height + rounded classes', () => {
    const { container } = render(<Shimmer width="w-32" height="h-8" rounded="rounded-full" />)
    const el = container.querySelector('[role="presentation"]') as HTMLElement
    expect(el.className).toContain('w-32')
    expect(el.className).toContain('h-8')
    expect(el.className).toContain('rounded-full')
  })

  it('applies atlas-shimmer animation class', () => {
    const { container } = render(<Shimmer />)
    const el = container.querySelector('[role="presentation"]') as HTMLElement
    expect(el.className).toContain('atlas-shimmer')
  })
})
