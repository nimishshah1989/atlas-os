// src/lib/supabase/client.ts — the browser client, for client components that need auth state.
import { createBrowserClient } from '@supabase/ssr'
import { basePath } from '@/lib/basePath'
import { cookieScope } from './cookieScope'
import { readSupabaseEnv } from './env'

export function createBrowserSupabase() {
  const env = readSupabaseEnv()
  if (!env) throw new Error('Auth is not configured: NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY are unset.')
  // Path-scoped: this board shares atlas.jslwealth.in with the India board (./cookieScope.ts).
  return createBrowserClient(env.url, env.anonKey, {
    cookieOptions: { path: cookieScope(basePath) },
  })
}
