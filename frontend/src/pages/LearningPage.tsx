import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { useAsyncData } from '@/hooks/useAsyncData'
import { formatINR, formatPercent, cn } from '@/lib/format'
import { services } from '@/services'

export function LearningPage() {
  const summary = useAsyncData(() => services.learning.getSummary(), [])
  const effectiveness = useAsyncData(() => services.learning.getEffectiveness(), [])
  const evidence = useAsyncData(() => services.learning.getEvidence(), [])
  const calibration = useAsyncData(() => services.learning.getCalibration(), [])
  const changes = useAsyncData(() => services.learning.getChanges(), [])
  const crossLane = useAsyncData(() => services.learning.getCrossLane(), [])

  if (summary.error) return <ErrorState onRetry={summary.reload} />

  return (
    <div>
      <PageHeader
        title="Recovery Intelligence"
        subtitle="Learn from observed outcomes to improve future recovery decisions."
      />

      <div className="mb-4 grid gap-3 lg:grid-cols-5">
        {summary.loading || !summary.data ? (
          <Skeleton className="h-32 lg:col-span-5" />
        ) : (
          <>
            <div className="rounded-xl border border-ink-200 bg-white p-5 shadow-soft lg:col-span-2">
              <div className="text-xs font-medium text-ink-400">Outcomes observed</div>
              <div className="mt-2 text-4xl font-semibold tracking-tight text-ink-900">
                {summary.data.outcomesObserved.toLocaleString()}
              </div>
            </div>
            <div className="rounded-xl border border-ink-200 bg-white p-4 shadow-soft">
              <div className="text-xs text-ink-400">Actions tracked</div>
              <div className="mt-2 text-2xl font-semibold">{summary.data.actionsTracked}</div>
            </div>
            <div className="rounded-xl border border-ink-200 bg-white p-4 shadow-soft">
              <div className="text-xs text-ink-400">High-confidence actions</div>
              <div className="mt-2 text-2xl font-semibold">
                {summary.data.highConfidenceActions}
              </div>
            </div>
            <div className="rounded-xl border border-ink-200 bg-white p-4 shadow-soft">
              <div className="text-xs text-ink-400">Calibration score</div>
              <div className="mt-2 text-2xl font-semibold">
                {summary.data.calibrationScore.toFixed(3)}
              </div>
              <div className="mt-1 text-xs text-ink-400">
                Updated {summary.data.lastUpdate}
              </div>
            </div>
          </>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title="Action Effectiveness">
          {effectiveness.loading || !effectiveness.data ? (
            <Skeleton className="h-56" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="text-xs uppercase text-ink-400">
                  <tr className="border-b border-ink-100">
                    <th className="pb-2 font-medium">Action</th>
                    <th className="pb-2 font-medium">Attempts</th>
                    <th className="pb-2 font-medium">Recovery</th>
                    <th className="pb-2 font-medium">Avg Cost</th>
                    <th className="pb-2 font-medium">Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {effectiveness.data.map((row) => (
                    <tr key={row.action} className="border-b border-ink-50">
                      <td className="py-2.5 font-medium">{row.action}</td>
                      <td className="py-2.5">{row.attempts}</td>
                      <td className="py-2.5">{row.recoveryRate}%</td>
                      <td className="py-2.5">{formatINR(row.avgCost)}</td>
                      <td className="py-2.5">
                        <span
                          className={cn(
                            'text-sm',
                            row.trend === 'up' && 'text-emerald-600',
                            row.trend === 'down' && 'text-rose-600',
                            row.trend === 'flat' && 'text-ink-400',
                          )}
                        >
                          {row.trend === 'up' ? '↑' : row.trend === 'down' ? '↓' : '→'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="What Changed?" subtitle="Since last update">
          {changes.loading || !changes.data ? (
            <Skeleton className="h-40" />
          ) : (
            <ul className="space-y-3">
              {changes.data.map((c) => (
                <li
                  key={c.action}
                  className="flex items-center justify-between rounded-lg border border-ink-100 px-3 py-2.5"
                >
                  <span className="text-sm font-medium text-ink-800">{c.action}</span>
                  <span
                    className={cn(
                      'text-sm font-semibold',
                      c.delta >= 0 ? 'text-emerald-600' : 'text-rose-600',
                    )}
                  >
                    {c.delta > 0 ? '+' : ''}
                    {c.delta}% effectiveness
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        {evidence.loading || !evidence.data
          ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40" />)
          : evidence.data.map((card) => (
              <Panel key={card.action} title={card.action}>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-ink-500">Observations</span>
                    <span className="font-medium">{card.observations}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink-500">Recoveries</span>
                    <span className="font-medium">{card.recoveries}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink-500">Observed recovery</span>
                    <span className="font-medium">{card.observedRecovery}%</span>
                  </div>
                  <div>
                    <div className="mb-1 flex justify-between text-xs">
                      <span className="text-ink-400">Confidence</span>
                      <span className="font-semibold uppercase text-ink-600">
                        {card.confidence}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-ink-100">
                      <div
                        className="h-full rounded-full bg-podium-600"
                        style={{
                          width:
                            card.confidence === 'high'
                              ? '90%'
                              : card.confidence === 'medium'
                                ? '60%'
                                : '35%',
                        }}
                      />
                    </div>
                  </div>
                </div>
              </Panel>
            ))}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Panel title="Predicted vs Observed Recovery">
          {calibration.loading || !calibration.data ? (
            <Skeleton className="h-64" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={calibration.data}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
                  <XAxis dataKey="predicted" tick={{ fontSize: 11, fill: '#6b7385' }} />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#6b7385' }}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip formatter={(v: number) => formatPercent(v, 0)} />
                  <Bar dataKey="observed" name="Observed" fill="#6b46ef" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel title="Cross-Lane Learning">
          {crossLane.loading || !crossLane.data ? (
            <Skeleton className="h-64" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-left text-sm">
                <thead className="text-xs uppercase text-ink-400">
                  <tr className="border-b border-ink-100">
                    <th className="pb-2 font-medium">Action</th>
                    <th className="pb-2 font-medium">Subscription</th>
                    <th className="pb-2 font-medium">Checkout</th>
                    <th className="pb-2 font-medium">Receivable</th>
                  </tr>
                </thead>
                <tbody>
                  {crossLane.data.map((row) => (
                    <tr key={row.action} className="border-b border-ink-50">
                      <td className="py-2.5 font-medium">{row.action}</td>
                      <td className="py-2.5">{row.subscription}%</td>
                      <td className="py-2.5">{row.checkout}%</td>
                      <td className="py-2.5">{row.receivable}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
