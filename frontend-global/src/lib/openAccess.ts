// src/lib/openAccess.ts — one switch: is this board behind a sign-in, or open?
//
// OPEN IS THE DEFAULT, and that is a decision about WHAT IS ON THE BOARD, not a shortcut.
// Everything Global Atlas renders today is public information: S&P 500 and US-listed ETF
// prices, returns, relative strength against SPY, and one representative fund per country.
// There are no client accounts, no positions, no holdings, no PII — M2 has not been built.
// A sign-in wall in front of published market data protects nothing and costs the reader the
// product, which is exactly what it did: it kept the FM out of his own board for a day while
// Supabase declined to send a magic link.
//
// The rule that replaces it is simple and stated once here: THE MOMENT THIS BOARD RENDERS
// ANYTHING THAT IS NOT PUBLIC MARKET DATA — a client's holdings, a saved basket, a position,
// an address, or an /admin surface that writes thresholds — auth goes back on, in the same PR
// that adds it, by setting ATLAS_GLOBAL_REQUIRE_AUTH=1. Not afterwards, not as a follow-up.
// tests/openAccess.test.ts asserts the default, so changing it is a reviewed act rather than
// a drifting one.
//
// BAKED AT BUILD TIME. This is read by src/middleware.ts, which Next compiles for the Edge
// runtime, where process.env is inlined during `next build` rather than read at boot. So
// flipping the variable requires a rebuild — which is what scripts/ops/atlas_global_deploy.sh
// does anyway. Setting it in .env.local and reloading pm2 alone would change nothing, and
// that silent no-op is worth knowing about before it is discovered at an unhelpful moment.

/**
 * True when readers must sign in. Off unless `ATLAS_GLOBAL_REQUIRE_AUTH=1` is set at build.
 *
 * Anything but the exact string `1` means open — a mis-set variable should fail toward the
 * state the deployment is actually in (a public-data board), not toward a wall nobody can pass.
 */
export function authRequired(): boolean {
  return process.env.ATLAS_GLOBAL_REQUIRE_AUTH === '1'
}
