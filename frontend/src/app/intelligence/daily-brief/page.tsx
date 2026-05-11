// frontend/src/app/intelligence/daily-brief/page.tsx
// SP05 — server component that renders the latest Claude-authored brief.

import { getLatestBrief } from '@/lib/queries/briefs'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function formatDate(d: Date | string): string {
  const date = typeof d === 'string' ? new Date(d) : d
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function summaryBadgeStyle(summary: string): React.CSSProperties {
  const palette: Record<string, { bg: string; fg: string }> = {
    bullish: { bg: '#dcfce7', fg: '#166534' },
    neutral: { bg: '#f1f5f9', fg: '#334155' },
    cautious: { bg: '#fef3c7', fg: '#854d0e' },
    defensive: { bg: '#fee2e2', fg: '#991b1b' },
  }
  const c = palette[summary] ?? palette.neutral
  return {
    background: c.bg,
    color: c.fg,
    padding: '4px 12px',
    borderRadius: '9999px',
    fontSize: '13px',
    fontWeight: 600,
    textTransform: 'capitalize',
  }
}

export default async function DailyBriefPage() {
  const brief = await getLatestBrief()

  if (!brief) {
    return (
      <main style={{ maxWidth: 760, margin: '64px auto', padding: '0 24px' }}>
        <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 32 }}>
          Daily Atlas Brief
        </h1>
        <p style={{ color: '#475569', marginTop: 16 }}>
          No brief has been generated yet. Run{' '}
          <code
            style={{
              fontFamily: 'monospace',
              background: '#f1f5f9',
              padding: '2px 6px',
            }}
          >
            python scripts/generate_daily_brief.py --persist
          </code>{' '}
          to create one.
        </p>
      </main>
    )
  }

  return (
    <main
      style={{
        maxWidth: 760,
        margin: '48px auto',
        padding: '0 24px 96px',
        background: '#ffffff',
        color: '#0f172a',
      }}
    >
      <header
        style={{
          borderBottom: '1px solid #e2e8f0',
          paddingBottom: 24,
          marginBottom: 32,
        }}
      >
        <div
          style={{
            fontSize: 13,
            color: '#64748b',
            letterSpacing: 1,
            textTransform: 'uppercase',
          }}
        >
          Atlas · Daily Brief
        </div>
        <h1
          style={{
            fontFamily: 'Georgia, "Times New Roman", serif',
            fontSize: 36,
            lineHeight: 1.2,
            margin: '8px 0 12px',
            color: '#0f172a',
          }}
        >
          {formatDate(brief.as_of_date)}
        </h1>
        <div
          style={{
            display: 'flex',
            gap: 12,
            alignItems: 'center',
            flexWrap: 'wrap',
          }}
        >
          <span
            style={{
              background: '#1D9E75',
              color: 'white',
              padding: '4px 12px',
              borderRadius: 4,
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            {brief.regime_state}
          </span>
          <span style={summaryBadgeStyle(brief.regime_summary)}>
            {brief.regime_summary}
          </span>
          {brief.regime_delta !== 'unchanged' && (
            <span
              style={{
                background: '#eef2ff',
                color: '#3730a3',
                padding: '4px 12px',
                borderRadius: '9999px',
                fontSize: 13,
                fontWeight: 600,
                textTransform: 'capitalize',
              }}
            >
              Regime {brief.regime_delta}
            </span>
          )}
        </div>
      </header>

      <article
        style={{
          fontFamily: 'Georgia, "Times New Roman", serif',
          fontSize: 18,
          lineHeight: 1.7,
          color: '#1e293b',
          whiteSpace: 'pre-wrap',
        }}
      >
        {brief.narrative}
      </article>

      <section style={{ marginTop: 40 }}>
        <h2
          style={{
            fontSize: 14,
            letterSpacing: 1.5,
            textTransform: 'uppercase',
            color: '#64748b',
            marginBottom: 12,
          }}
        >
          Key Themes
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {brief.key_themes.map((theme, i) => (
            <span
              key={i}
              style={{
                background: '#f0fdf4',
                border: '1px solid #bbf7d0',
                color: '#166534',
                padding: '6px 14px',
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              {theme}
            </span>
          ))}
        </div>
      </section>

      <footer
        style={{
          marginTop: 64,
          paddingTop: 24,
          borderTop: '1px solid #e2e8f0',
          fontSize: 12,
          color: '#94a3b8',
          display: 'flex',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <span>
          Model: {brief.model} · Prompt: {brief.prompt_version} · Tokens:{' '}
          {brief.input_tokens ?? '–'} in / {brief.output_tokens ?? '–'} out
        </span>
        <span>
          See audit trail at <code>/admin/briefs/{brief.id}</code> (coming soon)
        </span>
      </footer>
    </main>
  )
}
