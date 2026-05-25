// frontend/src/components/v6/skeletons/SkeletonMethodology.tsx
//
// Page layout schema (design-application.md §6.10):
//   3 top-level children:
//     1. header strip  — "Methodology" H1
//     2. body sections — ClosedLoopDiagram SVG area + 5 explainer sections below
//     3. (no footer)
//
// Interactive methodology / closed-loop page.

import { Shimmer } from './Shimmer'

interface SkeletonMethodologyProps {
  className?: string
}

export function SkeletonMethodology({ className = '' }: SkeletonMethodologyProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-2">
        <Shimmer width="w-28" height="h-3" />
        <Shimmer width="w-56" height="h-8" />
      </div>

      {/* 2 — body sections */}
      <div className="space-y-6">
        {/* ClosedLoopDiagram SVG area */}
        <Shimmer width="w-full" height="h-80" rounded="rounded-lg" />

        {/* 5 explainer sections below the diagram */}
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="border border-[#C2B8A8] rounded p-4 space-y-2">
            <Shimmer width="w-40" height="h-5" />
            <Shimmer width="w-full" height="h-4" />
            <Shimmer width={i % 2 === 0 ? 'w-5/6' : 'w-3/4'} height="h-4" />
          </div>
        ))}
      </div>
    </div>
  )
}
