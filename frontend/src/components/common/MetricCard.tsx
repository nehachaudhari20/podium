import { cn, formatDelta } from '@/lib/format'
import { TrendingDown, TrendingUp } from 'lucide-react'

export function MetricCard({
  label,
  value,
  delta,
  hint,
  className,
}: {
  label: string
  value: string
  delta?: number
  hint?: string
  className?: string
}) {
  const up = (delta ?? 0) >= 0
  return (
    <div
      className={cn(
        'rounded-xl border border-ink-200 bg-white p-4 shadow-soft',
        className,
      )}
    >
      <div className="text-sm font-medium text-ink-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-ink-900">
        {value}
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        {delta !== undefined && (
          <span
            className={cn(
              'inline-flex items-center gap-1 font-medium',
              up ? 'text-emerald-600' : 'text-rose-600',
            )}
          >
            {up ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
            {formatDelta(delta)}
          </span>
        )}
        {hint && <span className="text-ink-400">{hint}</span>}
      </div>
    </div>
  )
}
