// src/lib/supabase/client.ts — the browser client, for client components that need auth state.
import { createBrowserClient } from '@supabase/ssr'
import { readSupabaseEnv } from './env'

export function createBrowserSupabase() {
  const env = readSupabaseEnv()
  if (!env) throw new Error('Auth is not configured: NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY are unset.')
  return createBrowserClient(env.url, env.anonKey)
}
