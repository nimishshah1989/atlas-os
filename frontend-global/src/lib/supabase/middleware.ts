// src/lib/supabase/middleware.ts — refresh the session cookie on every request and gate the board.
// Without a session every route except /login and /health redirects to /login. When auth itself
// is not configured the same rule applies — a deployment without auth exposes nothing but the
// operator surface and the sign-in page, which explains what is missing.
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { basePath } from '@/lib/basePath'
import { e2eBypassEmail } from '@/lib/e2e'
import { cookieScope } from './cookieScope'
import { readSupabaseEnv } from './env'
import { isPublicPath } from './paths'

function toLogin(request: NextRequest): NextResponse {
  const url = request.nextUrl.clone()
  const wanted = request.nextUrl.pathname + request.nextUrl.search
  url.pathname = '/login'
  url.search = wanted === '/' ? '' : `?next=${encodeURIComponent(wanted)}`
  return NextResponse.redirect(url)
}

export async function updateSession(request: NextRequest): Promise<NextResponse> {
  // The smoke's dev-only bypass (src/lib/e2e.ts): compiled away by `next build`.
  if (e2eBypassEmail()) return NextResponse.next({ request })
  const { pathname } = request.nextUrl
  const env = readSupabaseEnv()
  if (!env) return isPublicPath(pathname) ? NextResponse.next({ request }) : toLogin(request)

  let response = NextResponse.next({ request })
  // Every refresh writes the session cookie, so this is the hot path for the Path=/ problem
  // (./cookieScope.ts): the middleware runs on every request, India's included if it ever
  // shared a process. Scoped on the library AND on the response cookie we set ourselves.
  const path = cookieScope(basePath)
  const supabase = createServerClient(env.url, env.anonKey, {
    cookieOptions: { path },
    cookies: {
      getAll() {
        return request.cookies.getAll()
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
        response = NextResponse.next({ request })
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, { ...options, path }),
        )
      },
    },
  })

  // getUser() validates the token with Supabase; getSession() would trust the cookie alone.
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user && !isPublicPath(pathname)) return toLogin(request)
  return response
}
