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
    label: 'COVID',
    description: 'COVID-19 crash — global markets sold off 30-40% in 5 weeks',
    startDate: '2020-02-20',
    endDate:   '2020-03-23',
    color: '#B0492C',
  },
  {
    id: 'rate-hike-cycle-2022',
    label: 'Rate hike',
    description: 'Global rate hike cycle — RBI followed Fed with 250bps of hikes',
    startDate: '2022-06-01',
    endDate:   '2023-02-15',
    color: '#B8860B',
  },
  {
    id: 'adani-crisis-2023',
    label: 'Adani',
    description: 'Adani Group crisis — Hindenburg report triggered contagion in related sectors',
    startDate: '2023-01-24',
    endDate:   '2023-03-01',
    color: '#B0492C',
  },
  {
    id: 'election-2024',
    label: 'Election',
    description: '2024 Indian general election — market uncertainty around coalition outcome',
    startDate: '2024-04-01',
    endDate:   '2024-06-04',
    color: '#1D9E75',
  },
]
