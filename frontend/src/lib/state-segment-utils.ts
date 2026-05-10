export type Segment = {
  state: string
  startDate: Date
  endDate: Date
  days: number
}

export function buildSegments(rows: { date: Date; state: string }[]): Segment[] {
  if (rows.length === 0) return []
  const segments: Segment[] = []
  let current = rows[0]
  let startDate = rows[0].date

  for (let i = 1; i < rows.length; i++) {
    if (rows[i].state !== current.state) {
      segments.push({
        state: current.state,
        startDate,
        endDate: rows[i - 1].date,
        days: i - segments.reduce((s, seg) => s + seg.days, 0),
      })
      current = rows[i]
      startDate = rows[i].date
    }
  }
  segments.push({
    state: current.state,
    startDate,
    endDate: rows[rows.length - 1].date,
    days: rows.length - segments.reduce((s, seg) => s + seg.days, 0),
  })
  return segments
}
