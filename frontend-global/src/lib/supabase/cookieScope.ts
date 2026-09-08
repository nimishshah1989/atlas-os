// src/lib/supabase/cookieScope.ts — the URL prefix the session cookie is allowed to travel with.
//
// THIS BOARD SHARES A DOMAIN. On the box the Global board is served at
// atlas.jslwealth.in/global, beside the live India board at atlas.jslwealth.in/ — same origin,
// so same cookie jar. `@supabase/ssr` writes its session cookie at `Path=/` by default, which
// means every request to the India board, every static asset it fetches included, would carry
// a Supabase session the India board has no use for and never reads.
//
// That is not merely untidy. The session is a JWT plus a refresh token, chunked across several
// cookies and measured in kilobytes; nginx bounds a request's header block
// (`large_client_header_buffers`, 4 x 8k by default) and answers an overflow with a bare
// 400 Bad Request. The people who would hit it are exactly the ones with a Global session —
// the FM and the analysts — on a board that keeps working for everybody else. A support report
// of "the board is broken for me only, sometimes" is about the worst shape a bug can take.
//
// So the cookie is scoped to this board's own sub-path. India never sees it.
//
// The value is the deployment's base path, and `/` at the root (an empty Path is invalid and
// browsers fall back to the request's directory, which would drop the cookie on a redirect).

/** The cookie `Path` for a board served under `base`. `'/'` at the root, never empty. */
export function cookieScope(base: string): string {
  const trimmed = base.replace(/\/+$/, '')
  return trimmed === '' ? '/' : trimmed
}
