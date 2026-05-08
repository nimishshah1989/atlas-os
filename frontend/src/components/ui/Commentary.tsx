type Props = {
  text: string
  className?: string
}

export function Commentary({ text, className = '' }: Props) {
  return (
    <p className={`font-sans text-sm text-ink-secondary leading-relaxed ${className}`}>
      {text}
    </p>
  )
}
