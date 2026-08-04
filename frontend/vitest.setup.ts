import '@testing-library/jest-dom'
import { existsSync } from 'node:fs'

// Next loads .env.local itself; vitest does not. Loading it here is what lets the
// *.int.test.ts suites see ATLAS_DB_URL and run against the real DB on a laptop.
// In CI there is no .env.local, so those suites skip themselves.
if (existsSync('.env.local')) process.loadEnvFile('.env.local')

// Radix UI primitives (Tooltip, Popover, etc.) use ResizeObserver internally.
// jsdom does not implement it; provide a minimal stub so tests don't crash.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
