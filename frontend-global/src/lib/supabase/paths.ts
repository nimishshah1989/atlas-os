// src/lib/supabase/paths.ts — pure path rules shared by the middleware, the login action and
// the callback route (kept dependency-free so they are unit-testable).

// Reachable without a session. /health is the operator surface and must stay visible when auth
// is broken; /login covers the form and its /login/callback exchange.
const PUBLIC_PREFIXES = ['/login', '/health']

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))
}

/** A post-login destination we are willing to follow: a same-origin path, never a URL. */
export function safeNext(value: unknown): string {
  if (typeof value !== 'string') return '/'
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) return '/'
  return value
}
