// The smoke's sign-in bypass must be inert in production whatever the environment says.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { e2eBypassEmail } from '@/lib/e2e'

afterEach(() => vi.unstubAllEnvs())

describe('e2eBypassEmail', () => {
  it('is null in production even when ATLAS_E2E_BYPASS is set', () => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('ATLAS_E2E_BYPASS', 'smoke@localhost')
    expect(e2eBypassEmail()).toBeNull()
  })
  it('is null outside production when the variable is unset or blank', () => {
    vi.stubEnv('NODE_ENV', 'development')
    vi.stubEnv('ATLAS_E2E_BYPASS', '')
    expect(e2eBypassEmail()).toBeNull()
  })
  it('is the lower-cased address outside production', () => {
    vi.stubEnv('NODE_ENV', 'development')
    vi.stubEnv('ATLAS_E2E_BYPASS', 'Smoke@Localhost')
    expect(e2eBypassEmail()).toBe('smoke@localhost')
  })
})
