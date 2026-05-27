import '@testing-library/jest-dom'

// Radix UI primitives (Tooltip, Popover, etc.) use ResizeObserver internally.
// jsdom does not implement it; provide a minimal stub so tests don't crash.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
