// Stub for 'server-only' package in vitest test environment.
// The real package throws when imported outside a Next.js Server Component.
// In tests we just need the module to be importable without side effects.
export {}
