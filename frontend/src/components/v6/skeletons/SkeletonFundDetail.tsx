// frontend/src/components/v6/skeletons/SkeletonFundDetail.tsx
//
// Page layout schema (design-application.md §6.6):
//   3 top-level children:
//     1. header strip — fund name + grade chip + conviction tape + thesis
//     2. tab nav + body — Overview (rank decomp + waterfall), Holdings, Audit
//     3. (no footer)
//
// Fund detail page.

import { Shimmer } from './Shimmer'

interface SkeletonFundDetailProps {
  className?: string
}

export function SkeletonFundDetail({ className = '' }: SkeletonFundDetailProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-3 pb-4 border-b border-[#C2B8A8]">
        <div className="flex items-start justify-between">
          <div className="space-y-2 flex-1">
            <Shimmer width="w-80" height="h-8" />
            <Shimmer width="w-56" height="h-4" />
          </div>
          <Shimmer width="w-16" height="h-8" />
        </div>
        <Shimmer width="w-full" height="h-8" rounded="rounded" />
        <div className="space-y-2">
          {Array.from({ length: 3 }, (_, i) => (
            <Shimmer key={i} width={i % 2 === 0 ? 'w-full' : 'w-4/5'} height="h-4" />
          ))}
        </div>
      </div>

      {/* 2 — tab nav + body */}
      <div className="space-y-4">
        {/* Tabs */}
        <div className="flex gap-6 border-b border-[#C2B8A8]">
          {[0, 1, 2].map((i) => (
            <Shimmer key={i} width="w-24" height="h-8" />
          ))}
        </div>
        {/* Rank decomposition cards — 4 horizontal */}
        <div className="grid grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="border border-[#C2B8A8] rounded p-4 space-y-2">
              <Shimmer width="w-full" height="h-4" />
              <Shimmer width="w-16" height="h-7" />
              <Shimmer width="w-full" height="h-3" />
              <Shimmer width="w-3/4" height="h-3" />
            </div>
          ))}
        </div>
        {/* Waterfall */}
        <Shimmer width="w-full" height="h-40" rounded="rounded-lg" />
      </div>
    </div>
  )
}
