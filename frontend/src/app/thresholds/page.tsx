// /thresholds — the FM methodology control panel. Server shell: read every knob from
// atlas_foundation.atlas_thresholds and hand it to the editable client panel.
export const dynamic = 'force-dynamic' // always show the current saved values

import { getThresholds } from '@/lib/queries/thresholds'
import { ThresholdsPanelV4 } from '@/components/thresholds/ThresholdsPanelV4'

export default async function ThresholdsPage() {
  const rows = await getThresholds()
  return (
    <div className="mx-auto max-w-[1440px] px-6 py-7">
      <div className="mb-5">
        <div className="mb-2 font-num text-[11px] uppercase tracking-[0.14em] text-txt-3">
          <a href="/" className="text-brand no-underline hover:underline">Atlas</a> › Thresholds
        </div>
        <h1 className="mb-2 font-display text-[40px] font-medium leading-[1.1] tracking-[-0.011em] text-txt-1">
          Methodology control panel
        </h1>
        <p className="max-w-[820px] font-sans text-[14px] text-txt-2">
          Every threshold and weight the scoring uses, live from <strong className="text-txt-1">atlas_foundation.atlas_thresholds</strong>.
          Edit within each knob’s allowed range, <strong className="text-txt-1">Save</strong>, then <strong className="text-txt-1">Preview</strong> the
          impact and <strong className="text-txt-1">Commit</strong> to re-blend the live composite from the cached lens scores — seconds, because only the
          weighting re-runs. {rows.length} active knobs.
        </p>
      </div>
      <ThresholdsPanelV4 rows={rows} />
    </div>
  )
}
