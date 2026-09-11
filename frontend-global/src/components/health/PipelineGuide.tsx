// src/components/health/PipelineGuide.tsx — the nightly, explained: each stage, each step, what it
// does, what it wrote last, and what its colour means. The catalogue is src/lib/pipeline.ts; the
// state is the latest run per script. Stages open by themselves when something in them is not
// green, so the page reads as "what needs attention" first and "how it all works" second.
import { formatNum, formatShortDateTime } from '@/lib/format'
import { CADENCE_LABEL, STAGE_LABEL, STAGE_ORDER, STEPS, stepRag, type Rag, type Step } from '@/lib/pipeline'
import type { PipelineRun } from '@/lib/queries/health'

const DOT: Record<Rag, string> = { green: 'bg-pos', amber: 'bg-warn', red: 'bg-neg', grey: 'bg-ink-3' }
const WORD: Record<Rag, string> = { green: 'ran and succeeded', amber: 'not run in its window, or still running', red: 'failed', grey: 'never recorded a run' }

function Row({ step, run, rag }: { step: Step; run: PipelineRun | undefined; rag: Rag }) {
  return (
    <li className="guide-step" data-step={step.key} data-rag={rag}>
      <span aria-hidden="true" className={`dot mt-1.5 ${DOT[rag]}`} title={WORD[rag]} />
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
          <span className="text-body font-medium text-ink">{step.key}</span>
          <code className="text-meta">{step.script}</code>
          <span className="text-meta text-ink-3">{CADENCE_LABEL[step.cadence]}</span>
          {run ? (
            <span className="num text-meta text-ink-3">
              last {formatShortDateTime(run.started_at)} ET · {run.status}
              {run.rows_written != null && ` · ${formatNum(run.rows_written)} rows`}
            </span>
          ) : (
            <span className="text-meta text-ink-3">no run recorded</span>
          )}
        </div>
        <p className="mt-0.5 max-w-[92ch] text-table text-ink-2">{step.does}</p>
        {step.writes.length > 0 && (
          <p className="mt-0.5 text-meta text-ink-3">
            writes {step.writes.map((t) => <code key={t}>{t}</code>).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, ', ', el] : [el]), [])}
          </p>
        )}
        <p className={`mt-0.5 max-w-[92ch] text-meta ${rag === 'red' ? 'text-neg' : 'text-ink-3'}`}>
          If it fails: {step.ifItFails}
        </p>
        {rag === 'red' && run?.error_message && (
          <p className="mt-1 max-w-[92ch] text-meta text-neg" title={run.error_message}>
            It said: {run.error_message}
          </p>
        )}
      </div>
    </li>
  )
}

export function PipelineGuide({ latest, now = new Date() }: { latest: PipelineRun[]; now?: Date }) {
  const byScript = new Map(latest.map((r) => [r.script_name, r]))
  return (
    <div className="space-y-2">
      <p className="max-w-[92ch] text-body text-ink-2">
        Green: ran and succeeded inside its window. Amber: not run in its window, or still running. Red: failed —
        a red <b>gate</b> withholds publish and the board keeps its last-good session; a red <b>step</b> is
        collected and reported, and the chain carries on. Grey: no run on record yet.
      </p>
      {STAGE_ORDER.map((stage) => {
        const steps = STEPS.filter((s) => s.stage === stage)
        const rags = steps.map((s) => stepRag(s, byScript.get(s.key), now))
        const worst: Rag = rags.includes('red') ? 'red' : rags.includes('amber') ? 'amber' : rags.includes('grey') ? 'grey' : 'green'
        return (
          <details key={stage} className="guide-stage panel" open={worst !== 'green'} data-stage={stage} data-rag={worst}>
            <summary className="guide-summary">
              <span aria-hidden="true" className={`dot ${DOT[worst]}`} />
              <span className="text-body font-medium text-ink">{STAGE_LABEL[stage]}</span>
              <span className="num text-meta text-ink-3">
                {steps.length} step{steps.length === 1 ? '' : 's'}
                {rags.filter((r) => r === 'red').length > 0 && ` · ${rags.filter((r) => r === 'red').length} failed`}
              </span>
            </summary>
            <ul className="guide-steps">
              {steps.map((s, i) => (
                <Row key={s.key} step={s} run={byScript.get(s.key)} rag={rags[i]} />
              ))}
            </ul>
          </details>
        )
      })}
    </div>
  )
}
