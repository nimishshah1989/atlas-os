// src/middleware.ts — every request passes through the session gate (see lib/supabase/middleware).
import type { NextRequest } from 'next/server'
import { updateSession } from '@/lib/supabase/middleware'

export async function middleware(request: NextRequest) {
  return updateSession(request)
}

export const config = {
  // Everything except Next internals and static files. Next rebases the pattern on basePath at
  // build time, so the exclusions keep their meaning under /global. '/' is listed separately
  // because the catch-all's path group is mandatory: without it the board's own front door
  // (/global, no trailing slash) is the one URL the gate never sees, and the session cookie is
  // never refreshed for a reader who lands there. page.tsx calls requireUser() either way.
  matcher: [
    '/',
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|txt|xml)$).*)',
  ],
}
