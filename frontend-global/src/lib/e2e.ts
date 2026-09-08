// src/lib/e2e.ts — the browser smoke's sign-in bypass. Local only, documented in e2e/README.md.
//
// ATLAS_E2E_BYPASS=<email> makes `next dev` treat every request as that address, skipping ONLY the
// Supabase session: the allowlist (atlas_global.app_user) is still consulted, so the address must be
// an invited row in the database the smoke runs against. It is honoured solely when NODE_ENV is not
// 'production'. `next build` inlines NODE_ENV as the literal 'production' into every bundle (server,
// edge and browser), so in a built deployment this function is compiled to `return null` — the
// variable cannot reach production auth even if someone sets it there.

export function e2eBypassEmail(): string | null {
  if (process.env.NODE_ENV === 'production') return null
  const v = process.env.ATLAS_E2E_BYPASS?.trim()
  return v ? v.toLowerCase() : null
}
