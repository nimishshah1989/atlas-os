// Admin · Methodology — the whole scoring model as a plain-English expanding tree: every metric,
// every calculation, and how it rolls up to sector / ETF / fund. Static content (no DB).
import { MethodologyTree } from '@/components/v6/admin/MethodologyTree'
import { METHODOLOGY } from '@/lib/v6/methodologySpec'

export default function AdminMethodologyPage() {
  return (
    <div>
      <p className="mb-5 max-w-[820px] font-sans text-[14px] leading-[1.55] text-txt-2">
        How Atlas scores everything, in plain terms. Click any node to open it — the conviction score breaks
        into four lenses, each into sub-components, each into the real metrics behind them; the last three
        sections show how a single stock’s read rolls up to a <strong className="text-txt-1">sector</strong>,
        an <strong className="text-txt-1">ETF / fund</strong>, and a <strong className="text-txt-1">category ranking</strong>.
        Each metric’s definition is the same one behind its info-icon on the tables.
      </p>
      <MethodologyTree roots={METHODOLOGY} />
    </div>
  )
}
