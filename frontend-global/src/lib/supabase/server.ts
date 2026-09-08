// src/lib/supabase/server.ts — the server client for Server Components, Server Actions and Route
// Handlers. Sessions live in cookies; the middleware refreshes them, so a Server Component that
// cannot write cookies is free to ignore the setAll failure.
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { basePath } from '@/lib/basePath'
import { cookieScope } from './cookieScope'
import { readSupabaseEnv } from './env'

export async function createServerSupabase() {
  const env = readSupabaseEnv()
  if (!env) throw new Error('Auth is not configured: NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY are unset.')
  const cookieStore = await cookies()
  const path = cookieScope(basePath)
  return createServerClient(env.url, env.anonKey, {
    // Scoped to this board's sub-path so the session never rides along on an India request
    // (./cookieScope.ts). Passed to the library AND forced in setAll below: the library's
    // default is Path=/, and a default is not something to leave a shared domain resting on.
    cookieOptions: { path },
    cookies: {
      getAll() {
        return cookieStore.getAll()
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, { ...options, path }),
          )
        } catch {
          // Called from a Server Component, which may not set cookies. The middleware keeps the
          // session fresh, so nothing is lost.
        }
      },
    },
  })
}
