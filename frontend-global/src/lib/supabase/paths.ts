// src/lib/supabase/paths.ts — pure path rules shared by the middleware, the login action and
// the callback route (kept dependency-free so they are unit-testable).

// Reachable without a session. /health is the operator surface and must stay visible when auth
// is broken; /login covers the form and its /login/callback exchange; /api/revalidate is the
// orchestrator's publish webhook, guarded by its own bearer secret (src/lib/revalidate.ts).
const PUBLIC_PREFIXES = ['/login', '/health', '/api/revalidate']

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))
}

/** A post-login destination we are willing to follow: a same-origin path, never a URL. */
export function safeNext(value: unknown): string {
  if (typeof value !== 'string') return '/'
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) return '/'
  return value
}

// The two URLs the sign-in flow builds itself, and which Next therefore does not prefix (see
// src/lib/basePath.ts). `next` is a board path WITHOUT the prefix — the middleware reads it from
// request.nextUrl.pathname, which Next has already stripped — so the prefix is added once, here.

/** Where the emailed magic link must land: this board's callback, on this origin. */
export function magicLinkRedirect(origin: string, basePath: string, next: string): string {
  return `${origin}${basePath}/login/callback?next=${encodeURIComponent(next)}`
}

/**
 * Where the callback sends the reader once the code is exchanged (or the link has failed).
 * The board root is the prefix itself: '/global/' would cost a 308 on the one hop that matters.
 */
export function postLoginPath(basePath: string, next: string): string {
  if (next === '/') return basePath || '/'
  return `${basePath}${next}`
}
