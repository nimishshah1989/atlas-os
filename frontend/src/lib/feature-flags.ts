/**
 * Feature flags — read from NEXT_PUBLIC_* env vars.
 * Flag OFF = production UI byte-identical.
 */

/** Six-lens v4 surfaces (behind NEXT_PUBLIC_LENS_V4=1). */
export const LENS_V4_ENABLED =
  process.env.NEXT_PUBLIC_LENS_V4 === '1' ||
  process.env.NEXT_PUBLIC_LENS_V4 === 'true'
