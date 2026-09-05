import { cn } from '@/lib/format'
import type { Lane, RiskLevel, CaseState, StageStatus } from '@/types/domain'
import { titleCase } from '@/lib/format'

const laneStyles: Record<Lane, string> = {
  subscription: 'bg-sky-50 text-sky-800 border-sky-200',
  checkout: 'bg-amber-50 text-amber-800 border-amber-200',
  receivable: 'bg-violet-50 text-violet-800 border-violet-200',
  failed_payment: 'bg-rose-50 text-rose-800 border-rose-200',
}

const riskStyles: Record<RiskLevel, string> = {
  high: 'bg-rose-50 text-rose-700 border-rose-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

const stateStyles: Record<string, string> = {
  needs_action: 'bg-rose-50 text-rose-700 border-rose-200',
  waiting: 'bg-slate-50 text-slate-700 border-slate-200',
  ptp_active: 'bg-podium-50 text-podium-700 border-podium-200',
  retry_scheduled: 'bg-sky-50 text-sky-700 border-sky-200',
  abandoned: 'bg-amber-50 text-amber-700 border-amber-200',
  recovered: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  escalated: 'bg-orange-50 text-orange-700 border-orange-200',
  deferred: 'bg-slate-50 text-slate-600 border-slate-200',
  coordinated: 'bg-podium-50 text-podium-700 border-podium-200',
}

export function Badge({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium',
        className,
      )}
    >
      {children}
    </span>
  )
}

export function LaneBadge({ lane }: { lane: Lane }) {
  return <Badge className={laneStyles[lane]}>{titleCase(lane)}</Badge>
}

export function RiskBadge({ risk }: { risk: RiskLevel }) {
  return <Badge className={riskStyles[risk]}>{titleCase(risk)}</Badge>
}

export function StatusBadge({ state }: { state: CaseState | string }) {
  return (
    <Badge className={stateStyles[state] ?? 'bg-slate-50 text-slate-700 border-slate-200'}>
      {titleCase(state)}
    </Badge>
  )
}

export function StageBadge({ status }: { status: StageStatus }) {
  const styles: Record<StageStatus, string> = {
    completed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    active: 'bg-podium-50 text-podium-700 border-podium-200',
    pending: 'bg-slate-50 text-slate-600 border-slate-200',
    blocked: 'bg-rose-50 text-rose-700 border-rose-200',
  }
  return <Badge className={styles[status]}>{titleCase(status)}</Badge>
}
