// frontend/src/components/skeletons/Shimmer.tsx
//
// Shared shimmer primitive used by all per-page skeletons.
// Design tokens: bg-paper (canvas) + ink-tertiary base (paper-rule / #C2B8A8)
// Animation: CSS @keyframes shimmer; disabled under prefers-reduced-motion.
// ARIA: role="presentation" — decorative; Suspense boundary owns announcement.
//
// No external imports beyond Tailwind classnames.

'use client'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ShimmerProps {
  /** Tailwind width class e.g. "w-full", "w-48" — default: w-full */
  width?: string
  /** Tailwind height class e.g. "h-4", "h-8" — default: h-4 */
  height?: string
  /** Tailwind border-radius class e.g. "rounded", "rounded-full" — default: rounded */
  rounded?: string
  /** Additional Tailwind classes */
  className?: string
}

// ── Component ─────────────────────────────────────────────────────────────────

export function Shimmer({
  width = 'w-full',
  height = 'h-4',
  rounded = 'rounded',
  className = '',
}: ShimmerProps) {
  return (
    <>
      <style>{`
        @keyframes atlas-shimmer {
          0% { background-position: -400px 0; }
          100% { background-position: 400px 0; }
        }
        @media (prefers-reduced-motion: no-preference) {
          .atlas-shimmer {
            background: linear-gradient(
              90deg,
              #C2B8A8 0px,
              #E8E1D4 80px,
              #C2B8A8 160px
            );
            background-size: 800px 100%;
            animation: atlas-shimmer 1.6s linear infinite;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .atlas-shimmer {
            background-color: #C2B8A8;
          }
        }
      `}</style>
      <div
        role="presentation"
        aria-hidden="true"
        className={`atlas-shimmer ${width} ${height} ${rounded} ${className}`}
      />
    </>
  )
}
