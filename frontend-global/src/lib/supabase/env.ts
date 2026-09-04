// src/lib/supabase/env.ts — the two public Supabase Auth settings. Referenced by literal name so
// Next inlines them for the browser bundle; absent values mean "auth is not configured", which
// every caller renders as a state rather than an exception.

export type SupabaseEnv = { url: string; anonKey: string }

export function readSupabaseEnv(): SupabaseEnv | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  return url && anonKey ? { url, anonKey } : null
}

export function isSupabaseConfigured(): boolean {
  return readSupabaseEnv() !== null
}
