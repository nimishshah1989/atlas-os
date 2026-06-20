import { describe, it, expect, vi, afterEach } from 'vitest'

describe('feature-flags', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('LENS_V4_ENABLED defaults to false', async () => {
    vi.stubEnv('NEXT_PUBLIC_LENS_V4', '')
    const { LENS_V4_ENABLED } = await import('../feature-flags')
    expect(LENS_V4_ENABLED).toBe(false)
  })

  it('LENS_V4_ENABLED is true when set to "1"', async () => {
    vi.stubEnv('NEXT_PUBLIC_LENS_V4', '1')
    const { LENS_V4_ENABLED } = await import('../feature-flags')
    expect(LENS_V4_ENABLED).toBe(true)
  })

  it('LENS_V4_ENABLED is true when set to "true"', async () => {
    vi.stubEnv('NEXT_PUBLIC_LENS_V4', 'true')
    const { LENS_V4_ENABLED } = await import('../feature-flags')
    expect(LENS_V4_ENABLED).toBe(true)
  })

  it('LENS_V4_ENABLED is false for random values', async () => {
    vi.stubEnv('NEXT_PUBLIC_LENS_V4', 'yes')
    const { LENS_V4_ENABLED } = await import('../feature-flags')
    expect(LENS_V4_ENABLED).toBe(false)
  })
})
