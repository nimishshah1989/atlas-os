// src/app/strategies/v6/exclusions/page.tsx
// Exclusion explorer — every name filtered out + reason.
export const dynamic = 'force-dynamic'

const MOCK_EXCLUSIONS = [
  { symbol: 'ADANIENT',   reason: 'auditor not in top-10 (Shah Dhandharia & Co)', filter: 'auditor_quality', date: '2026-05-19' },
  { symbol: 'ADANIPORTS', reason: 'issuer-group cap (Adani group >5%)',           filter: 'group_cap',       date: '2026-05-19' },
  { symbol: 'ADANIGREEN', reason: 'auditor not in top-10',                         filter: 'auditor_quality', date: '2026-05-19' },
  { symbol: 'SUZLON',     reason: 'currently in F&O ban list',                     filter: 'fno_ban',         date: '2026-05-19' },
  { symbol: 'YESBANK',    reason: 'promoter pledge 32.4% (>30% threshold)',        filter: 'pledge',          date: '2026-05-19' },
  { symbol: 'IDEA',       reason: 'currently in F&O ban list',                     filter: 'fno_ban',         date: '2026-05-19' },
  { symbol: 'RBLBANK',    reason: 'currently in F&O ban list',                     filter: 'fno_ban',         date: '2026-05-19' },
  { symbol: 'DHFL',       reason: 'promoter pledge 62% (>30% threshold)',          filter: 'pledge',          date: '2026-05-19' },
]

const FILTER_LABELS: Record<string, string> = {
  auditor_quality: 'Auditor not top-10',
  group_cap: 'Issuer/group cap >5%',
  fno_ban: 'F&O ban list',
  pledge: 'Promoter pledge >30%',
  sme: 'SME segment',
  audit_qualification: 'Recent qualified audit',
}

export default function V6ExclusionsPage() {
  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <p className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">
          <a href="/strategies/v6" className="hover:text-ink-primary">v6 Command Center</a>
          {' / Exclusions'}
        </p>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Governance Exclusions</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          Every name filtered out of the v6 book, with reason. Six hard governance filters: pledge, auditor quality, F&amp;O ban, SME, issuer group, audit qualification.
        </p>
      </header>

      <div className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-paper-rule/20 border-b border-paper-rule text-ink-tertiary">
            <tr>
              <th className="text-left font-sans font-normal px-3 py-2">Symbol</th>
              <th className="text-left font-sans font-normal px-3 py-2">Filter</th>
              <th className="text-left font-sans font-normal px-3 py-2">Reason</th>
              <th className="text-left font-sans font-normal px-3 py-2">Excluded since</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_EXCLUSIONS.map((e) => (
              <tr key={e.symbol} className="border-b border-paper-rule/40">
                <td className="px-3 py-2 font-mono text-ink-primary">{e.symbol}</td>
                <td className="px-3 py-2 font-sans text-rose-800">{FILTER_LABELS[e.filter] ?? e.filter}</td>
                <td className="px-3 py-2 font-sans text-ink-secondary">{e.reason}</td>
                <td className="px-3 py-2 font-mono text-[11px] text-ink-tertiary">{e.date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="font-sans text-[11px] text-ink-tertiary mt-4">
        Backed by atlas_v6_exclusions_log. Mock data shown until backend (Plan 2) lands.
      </p>
    </main>
  )
}
