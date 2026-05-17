interface MetricProps {
  icon: React.ReactNode
  label: string
  value: string
}

export function Metric({ icon, label, value }: MetricProps) {
  return (
    <div className="flex flex-col gap-xs">
      <div className="flex items-center gap-xs text-xs text-ink-secondary">
        {icon}
        {label}
      </div>
      <p className="text-sm font-semibold text-ink">{value}</p>
    </div>
  )
}
