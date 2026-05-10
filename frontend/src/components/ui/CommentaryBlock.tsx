type ContextCard = {
  label: string
  value: string
  delta?: string
  deltaPositive?: boolean
}

type Props = {
  narrative: string
  contextCards?: ContextCard[]
  dataAsOf?: string
  className?: string
}

export function CommentaryBlock({ narrative, contextCards, dataAsOf, className = '' }: Props) {
  return (
    <div className={`space-y-3 ${className}`}>
      <p className="font-sans text-sm text-ink-secondary leading-relaxed">{narrative}</p>
      {contextCards && contextCards.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {contextCards.map((card, i) => (
            <div
              key={i}
              className="bg-paper-rule/10 border border-paper-rule/40 rounded-sm px-2.5 py-1.5"
            >
              <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">
                {card.label}
              </div>
              <div className="font-sans text-sm font-medium text-ink-primary flex items-center gap-1">
                {card.value}
                {card.delta && (
                  <span className={`text-xs ${card.deltaPositive ? 'text-signal-pos' : 'text-signal-neg'}`}>
                    {card.delta}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {dataAsOf && (
        <p className="font-sans text-[10px] text-ink-tertiary">
          as of {dataAsOf}
        </p>
      )}
    </div>
  )
}
