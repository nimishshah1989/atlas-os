'use server'
// src/app/login/actions.ts — send the magic link; sign out.
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'
import { isInvited } from '@/lib/auth'
import { dbAvailable } from '@/lib/db'
import { isSupabaseConfigured } from '@/lib/supabase/env'
import { safeNext } from '@/lib/supabase/paths'
import { createServerSupabase } from '@/lib/supabase/server'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

async function requestOrigin(): Promise<string> {
  const h = await headers()
  const host = h.get('x-forwarded-host') ?? h.get('host') ?? 'localhost:3000'
  const proto = h.get('x-forwarded-proto') ?? (host.startsWith('localhost') ? 'http' : 'https')
  return `${proto}://${host}`
}

export async function sendMagicLink(formData: FormData): Promise<void> {
  if (!isSupabaseConfigured()) redirect('/login')
  const email = String(formData.get('email') ?? '').trim().toLowerCase()
  const next = safeNext(formData.get('next'))
  if (!EMAIL_RE.test(email)) redirect('/login?error=email')

  // The allowlist is atlas_global.app_user. With a database it is checked before anything is sent
  // and Supabase may create the auth user on first sign-in; without one, only an existing auth
  // user can sign in (shouldCreateUser: false) and requireUser() re-checks once the DB is back.
  if (dbAvailable && !(await isInvited(email))) redirect('/login?reason=not-invited')

  const supabase = await createServerSupabase()
  const origin = await requestOrigin()
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: `${origin}/login/callback?next=${encodeURIComponent(next)}`,
      shouldCreateUser: dbAvailable,
    },
  })
  if (error) redirect(error.status === 422 ? '/login?reason=not-invited' : '/login?error=send')
  redirect(`/login?sent=${encodeURIComponent(email)}`)
}

export async function signOut(): Promise<void> {
  if (isSupabaseConfigured()) {
    const supabase = await createServerSupabase()
    await supabase.auth.signOut()
  }
  redirect('/login')
}
