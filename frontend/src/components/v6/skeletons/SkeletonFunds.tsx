// frontend/src/components/v6/skeletons/SkeletonFunds.tsx
//
// Page layout schema (design-application.md §6.5):
//   4 top-level children:
//     1. header strip     — eyebrow + H1
//     2. industry snapshot — 4-6 callout cards + AMC leaderboard
//     3. charts section   — bubble chart + signature matrix
//     4. ranked table     — with column chooser
//
// Mutual funds list page.

import { Shimmer } from './Shimmer'

interface SkeletonFundsProps {
  className?: string
}

export function SkeletonFunds({ className = '' }: SkeletonFundsProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-2">
        <Shimmer width="w-28" height="h-3" />
        <Shimmer width="w-48" height="h-8" />
        <Shimmer width="w-64" height="h-4" />
      </div>

      {/* 2 — industry snapshot callout cards */}
      <div className="grid grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="border border-[#C2B8A8] rounded p-4 space-y-2">
            <Shimmer width="w-24" height="h-3" />
            <Shimmer width="w-full" height="h-7" />
          </div>
        ))}
      </div>

      {/* 3 — charts section: bubble + signature matrix */}
      <div className="grid grid-cols-2 gap-4">
        <Shimmer width="w-full" height="h-64" rounded="rounded-lg" />
        <div className="border border-[#C2B8A8] rounded p-4 space-y-2">
          <Shimmer width="w-40" height="h-4" />
          <div className="grid grid-cols-5 gap-1">
            {Array.from({ length: 30 }, (_, i) => (
              <Shimmer key={i} width="w-full" height="h-8" />
            ))}
          </div>
        </div>
      </div>

      {/* 4 — ranked table */}
      <div className="space-y-1">
        <div className="grid grid-cols-6 gap-2 pb-2 border-b border-[#C2B8A8]">
          {Array.from({ length: 6 }, (_, i) => (
            <Shimmer key={i} width="w-full" height="h-3" />
          ))}
        </div>
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="grid grid-cols-6 gap-2 py-2">
            {Array.from({ length: 6 }, (_, j) => (
              <Shimmer key={j} width="w-full" height="h-4" />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
