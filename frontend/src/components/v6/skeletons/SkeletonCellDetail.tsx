// frontend/src/components/v6/skeletons/SkeletonCellDetail.tsx
//
// Page layout schema (design-application.md §6.1 cell tile → /v6/cells/[cell_id]):
//   3 top-level children:
//     1. header strip  — cell label + grade chip + archetype + IC + stability
//     2. body sections — tab nav + per-window backtest + predicates + thesis
//     3. audit trail   — 7-section provenance
//
// Cell detail page (routes as /v6/cells/[cell_id]).

import { Shimmer } from './Shimmer'

interface SkeletonCellDetailProps {
  className?: string
}

export function SkeletonCellDetail({ className = '' }: SkeletonCellDetailProps) {
  return (
    <div data-testid="page-root" className={`min-h-screen bg-[#F8F4EC] p-6 space-y-6 ${className}`}>
      {/* 1 — header strip */}
      <div className="space-y-3 pb-4 border-b border-[#C2B8A8]">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <Shimmer width="w-20" height="h-3" />
            <Shimmer width="w-64" height="h-8" />
            <Shimmer width="w-48" height="h-4" />
          </div>
          <Shimmer width="w-16" height="h-8" />
        </div>
        {/* IC + stats row */}
        <div className="flex gap-6">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="space-y-1">
              <Shimmer width="w-20" height="h-3" />
              <Shimmer width="w-16" height="h-5" />
            </div>
          ))}
        </div>
      </div>

      {/* 2 — body sections */}
      <div className="space-y-4">
        {/* Tab nav */}
        <div className="flex gap-6 border-b border-[#C2B8A8]">
          {[0, 1, 2].map((i) => (
            <Shimmer key={i} width="w-24" height="h-8" />
          ))}
        </div>
        {/* Per-window backtest sparklines */}
        <div className="grid grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="border border-[#C2B8A8] rounded p-4 space-y-2">
              <Shimmer width="w-16" height="h-4" />
              <Shimmer width="w-full" height="h-20" />
              <Shimmer width="w-24" height="h-3" />
            </div>
          ))}
        </div>
        {/* Predicates + stocks */}
        <Shimmer width="w-full" height="h-40" rounded="rounded-lg" />
      </div>
    </div>
  )
}
