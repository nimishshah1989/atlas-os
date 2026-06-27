// Admin · Thresholds — the methodology control panel (edit knobs + recompute). Reuses the same
// ThresholdsPanelV4 over foundation_staging.atlas_thresholds.
export const dynamic = 'force-dynamic'

import { getThresholds } from '@/lib/queries/v6/thresholds'
import { ThresholdsPanelV4 } from '@/components/v6/thresholds/ThresholdsPanelV4'

export default async function AdminThresholdsPage() {
  const rows = await getThresholds()
  return (
    <div>
      <p className="mb-4 max-w-[820px] font-sans text-[14px] text-txt-2">
        Every threshold and weight the scoring uses, live from <strong className="text-txt-1">foundation_staging.atlas_thresholds</strong>.
        Edit within each knob’s allowed range, <strong className="text-txt-1">Save</strong>, then <strong className="text-txt-1">Preview</strong> the
        impact and <strong className="text-txt-1">Commit</strong> to re-blend the live composite from the cached lens scores. {rows.length} active knobs.
      </p>
      <ThresholdsPanelV4 rows={rows} />
    </div>
  )
}
