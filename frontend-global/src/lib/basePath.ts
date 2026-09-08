// src/lib/basePath.ts — the sub-path this deployment is served under, at run time.
//
// next.config.js reads ATLAS_GLOBAL_BASE_PATH at BUILD time and hands it to Next as `basePath`.
// Next then prefixes the routing it owns: <Link>, redirect() from next/navigation, and every
// asset URL. It does NOT prefix a URL the app assembles itself from an origin, and the sign-in
// flow assembles two — the magic link's emailRedirectTo (src/app/login/actions.ts) and the
// callback's NextResponse.redirect (src/app/login/callback/route.ts). Both run on the server, so
// they read the same variable here and prefix by hand.
//
// Set the variable in the SAME environment for `npm run build` and for the serving process
// (docs/global/deploy-subpath.md §2). A build with the prefix served by a process without it
// sends a freshly signed-in reader to atlas.jslwealth.in/etfs — the INDIA board's ETF page,
// which renders happily and is the wrong board.

/** '' at the root, '/global' on the box. Never a trailing slash: '/global/' + '/etfs' is a 404. */
export const basePath = (process.env.ATLAS_GLOBAL_BASE_PATH ?? '').replace(/\/+$/, '')
