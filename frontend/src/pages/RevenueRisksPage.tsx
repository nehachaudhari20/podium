import { Link, useSearchParams } from 'react-router-dom'
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { LaneBadge } from '@/components/common/Badges'
import { useAsyncData } from '@/hooks/useAsyncData'
import { formatINR, cn } from '@/lib/format'
import { services } from '@/services'

export function RevenueRisksPage() {
  const [params, setParams] = useSearchParams()
  const selected = params.get('quadrant')

  const groups = useAsyncData(() => services.risks.getRiskGroups(), [])
  const matrix = useAsyncData(() => services.risks.getMatrix(), [])
  const capacity = useAsyncData(() => services.risks.getCapacity(), [])
  const queue = useAsyncData(() => services.risks.getPriorityQueue(), [])

  if (groups.error || matrix.error) {
    return <ErrorState onRetry={() => { groups.reload(); matrix.reload() }} />
  }

  return (
    <div>
      <PageHeader
        title="Revenue Risks"
        subtitle="Where revenue is exposed and how Podium allocates recovery capacity."
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {groups.loading || !groups.data
          ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
          : groups.data.map((g) => (
              <div
                key={g.id}
                className="rounded-xl border border-ink-200 bg-white p-4 shadow-soft"
              >
                <div className="text-xs font-semibold uppercase tracking-wide text-ink-400">
                  {g.title}
                </div>
                <div className="mt-2 text-2xl font-semibold text-ink-900">
                  {g.cases.toLocaleString()} cases
                </div>
                <div className="mt-1 text-sm font-medium text-ink-700">
                  {formatINR(g.amount, true)} at risk
                </div>
                <p className="mt-2 text-xs text-ink-500">{g.description}</p>
              </div>
            ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Risk / Recoverability Matrix" subtitle="Economic prioritization">
          {matrix.loading || !matrix.data ? (
            <Skeleton className="h-72" />
          ) : (
            <div>
              <div className="mb-2 text-center text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                High Recoverability ↑
              </div>
              <div className="grid grid-cols-2 gap-3">
                {(['automate', 'act_now', 'stop', 'conserve'] as const).map((id) => {
                  const q = matrix.data!.find((m) => m.id === id)!
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() =>
                        setParams(selected === id ? {} : { quadrant: id })
                      }
                      className={cn(
                        'rounded-xl border p-4 text-left transition',
                        selected === id
                          ? 'border-podium-400 bg-podium-50'
                          : 'border-ink-200 bg-ink-50/60 hover:border-podium-200',
                      )}
                    >
                      <div className="text-sm font-semibold text-ink-900">{q.label}</div>
                      <div className="mt-2 text-2xl font-semibold">{q.count}</div>
                      <div className="text-xs text-ink-500">{formatINR(q.amount, true)}</div>
                    </button>
                  )
                })}
              </div>
              <div className="mt-2 flex justify-between text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                <span>← Low value</span>
                <span>High value →</span>
              </div>
              <div className="mt-1 text-center text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                ↓ Low Recoverability
              </div>
              {selected && (
                <p className="mt-3 text-sm text-ink-600">
                  Filtering conceptual queue to{' '}
                  <span className="font-semibold">
                    {matrix.data.find((m) => m.id === selected)?.label}
                  </span>
                  . Case drill-down available in Recovery.
                </p>
              )}
            </div>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel title="Recovery Capacity">
            {capacity.loading || !capacity.data ? (
              <Skeleton className="h-40" />
            ) : (
              <div className="space-y-4">
                {capacity.data.map((m) => (
                  <div key={m.id}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span className="font-medium text-ink-800">{m.label}</span>
                      <span className="text-ink-500">{m.utilized}%</span>
                    </div>
                    <div className="h-2.5 overflow-hidden rounded-full bg-ink-100">
                      <div
                        className="h-full rounded-full bg-podium-600"
                        style={{ width: `${m.utilized}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel
            title="Podium Priority Queue"
            subtitle="3 lower-value actions deferred · ₹11,400 capacity preserved"
          >
            {queue.loading || !queue.data ? (
              <Skeleton className="h-48" />
            ) : queue.data.length === 0 ? (
              <EmptyState title="Queue empty" />
            ) : (
              <ol className="space-y-3">
                {queue.data.map((item) => (
                  <li key={item.caseId}>
                    <Link
                      to={`/recovery/${item.caseId}`}
                      className="flex items-center gap-3 rounded-lg border border-ink-100 px-3 py-3 hover:bg-ink-50"
                    >
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-ink-900 text-sm font-semibold text-white">
                        {item.rank}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <LaneBadge lane={item.lane} />
                          <span className="text-sm font-medium text-ink-800">
                            {item.customerName}
                          </span>
                        </div>
                        <div className="mt-1 text-sm text-ink-600">
                          {formatINR(item.amount)}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-[11px] text-ink-400">Expected Net</div>
                        <div className="text-sm font-semibold">
                          {formatINR(item.expectedNet)}
                        </div>
                      </div>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}
