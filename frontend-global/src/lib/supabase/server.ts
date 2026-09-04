// src/lib/supabase/server.ts — the server client for Server Components, Server Actions and Route
// Handlers. Sessions live in cookies; the middleware refreshes them, so a Server Component that
// cannot write cookies is free to ignore the setAll failure.
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { readSupabaseEnv } from './env'

export async function createServerSupabase() {
  const env = readSupabaseEnv()
  if (!env) throw new Error('Auth is not configured: NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY are unset.')
  const cookieStore = await cookies()
  return createServerClient(env.url, env.anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll()
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options))
        } catch {
          // Called from a Server Component, which may not set cookies. The middleware keeps the
          // session fresh, so nothing is lost.
        }
      },
    },
  })
}
