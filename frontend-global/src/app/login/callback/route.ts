// src/app/login/callback/route.ts — the magic link lands here: exchange the code for a session
// cookie, then continue to where the reader was going. Lives under /login so it is reachable
// without a session.
import { NextResponse, type NextRequest } from 'next/server'
import { isSupabaseConfigured } from '@/lib/supabase/env'
import { safeNext } from '@/lib/supabase/paths'
import { createServerSupabase } from '@/lib/supabase/server'

export async function GET(request: NextRequest) {
  const url = new URL(request.url)
  const code = url.searchParams.get('code')
  const next = safeNext(url.searchParams.get('next'))

  if (code && isSupabaseConfigured()) {
    const supabase = await createServerSupabase()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) return NextResponse.redirect(new URL(next, url.origin))
  }
  return NextResponse.redirect(new URL('/login?error=link', url.origin))
}
