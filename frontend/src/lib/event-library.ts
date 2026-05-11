// Shape is frozen for Sprint 3. Do not change field names without updating
// BreadthWaterfall and the Sprint 5 regime page.

export type MarketEvent = {
  id: string
  label: string          // short label for chart annotation
  description: string    // tooltip / screen-reader text
  startDate: string      // ISO date YYYY-MM-DD
  endDate: string        // ISO date YYYY-MM-DD (same as startDate for point events)
  color: string          // hex color for reference line
}

export const MARKET_EVENTS: MarketEvent[] = [
  {
    id: 'covid-crash-2020',
    label: 'COVID Crash',
    description: 'COVID-19 crash — global markets sold off 30-40% in 5 weeks. Defensives and pharma led; cyclicals, financials collapsed.',
    startDate: '2020-02-20',
    endDate:   '2020-03-23',
    color: '#B0492C',
  },
  {
    id: 'post-covid-bull-2020',
    label: 'COVID Recovery',
    description: 'Post-COVID bull run — Nifty more than doubled from March 2020 lows. Metals, IT, chemicals, and consumer discretionary led the broad-based recovery.',
    startDate: '2020-05-01',
    endDate:   '2021-10-31',
    color: '#1D9E75',
  },
  {
    id: 'rate-hike-cycle-2022',
    label: 'Rate Hike Cycle',
    description: 'Global rate hike cycle — RBI followed Fed with 250bps of hikes. Bond-proxy sectors (utilities, real estate) underperformed; IT sold off on US recession fears.',
    startDate: '2022-06-01',
    endDate:   '2023-02-15',
    color: '#B8860B',
  },
  {
    id: 'adani-crisis-2023',
    label: 'Adani Crisis',
    description: 'Adani Group crisis — Hindenburg report triggered contagion in related sectors. Infrastructure, ports, and energy saw sharp corrections; defensives held.',
    startDate: '2023-01-24',
    endDate:   '2023-03-01',
    color: '#B0492C',
  },
  {
    id: 'capex-rally-2023',
    label: 'Capex Rally',
    description: 'Post-budget capex rally — Union Budget 2023 announced record infrastructure spending. Capital goods, defence, railways, and PSU themes led a strong sector rotation.',
    startDate: '2023-03-01',
    endDate:   '2023-12-31',
    color: '#1D9E75',
  },
  {
    id: 'election-2024',
    label: 'Election Jitters',
    description: '2024 Indian general election — market uncertainty around coalition outcome compressed valuations ahead of results.',
    startDate: '2024-04-01',
    endDate:   '2024-06-04',
    color: '#B8860B',
  },
  {
    id: 'post-election-rally-2024',
    label: 'Post-Election Rally',
    description: 'Post-election recovery — swift reversal of election-driven selloff. Defensives unwound, cyclicals and financials reaccelerated as coalition concerns eased.',
    startDate: '2024-06-05',
    endDate:   '2024-09-30',
    color: '#1D9E75',
  },
]
