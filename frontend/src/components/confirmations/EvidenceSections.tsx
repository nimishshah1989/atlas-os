'use client'
// "Additional weight of evidence": free sections for the sector charts that back
// the week's stock selection.
import { ChartAttach } from './ChartAttach'
import type { DraftEvidence } from './draftTypes'

export function EvidenceSections({
  sections,
  confirmationId,
  readOnly,
  onChange,
  onRefresh,
}: {
  sections: DraftEvidence[]
  confirmationId: number | null
  readOnly: boolean
  onChange: (s: DraftEvidence[]) => void
  onRefresh: () => void
}) {
  const update = (i: number, patch: Partial<DraftEvidence>) =>
    onChange(sections.map((s, j) => (j === i ? { ...s, ...patch } : s)))

  return (
    <section className="rounded-panel border border-edge-hair bg-surface-panel p-4 shadow-tile">
      <h2 className="mb-1 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">
        Additional weight of evidence
      </h2>
      <p className="mb-3 font-sans text-[12px] text-txt-3">
        Sector charts and the reasoning that supports this week&rsquo;s selection.
      </p>

      <div className="space-y-3">
        {sections.map((s, i) => (
          <div key={i} className="rounded-tile border border-edge-hair bg-surface-base p-3">
            <div className="mb-2 flex items-start gap-2">
              <input
                value={s.title}
                readOnly={readOnly}
                onChange={(e) => update(i, { title: e.target.value })}
                placeholder={`Section ${i + 1} title`}
                className="flex-1 rounded-tile border border-edge-rule bg-surface-base px-2.5 py-1.5 font-sans text-[13px] font-semibold text-txt-1 outline-none focus:border-brand"
              />
              {readOnly ? (
                <span className="pt-2 font-sans text-[11px] text-txt-3">{s.hasImage ? '✓ Chart' : '—'}</span>
              ) : (
                <ChartAttach
                  confirmationId={confirmationId}
                  target="evidence"
                  refKey={String(i)}
                  attached={s.hasImage}
                  onDone={onRefresh}
                />
              )}
              {!readOnly && (
                <button
                  type="button"
                  onClick={() => onChange(sections.filter((_, j) => j !== i))}
                  aria-label="Remove evidence section"
                  className="pt-2 font-sans text-[13px] text-txt-3 hover:text-sig-neg"
                >
                  ✕
                </button>
              )}
            </div>
            <textarea
              value={s.comment}
              readOnly={readOnly}
              onChange={(e) => update(i, { comment: e.target.value })}
              rows={3}
              placeholder="What this chart shows and why it matters"
              className="w-full rounded-tile border border-edge-rule bg-surface-base px-2.5 py-1.5 font-sans text-[12.5px] text-txt-1 outline-none focus:border-brand"
            />
          </div>
        ))}
      </div>

      {!readOnly && sections.length < 5 && (
        <button
          type="button"
          onClick={() =>
            onChange([...sections, { position: sections.length, title: '', comment: '', hasImage: false, evidenceId: null }])
          }
          className="mt-3 rounded-tile border border-edge-rule bg-surface-base px-3 py-1.5 font-sans text-[12px] text-txt-2 hover:border-edge-strong"
        >
          + Add section
        </button>
      )}
    </section>
  )
}
