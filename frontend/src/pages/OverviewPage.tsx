import { Link, useNavigate } from 'react-router-dom'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { MetricCard } from '@/components/common/MetricCard'
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { LaneBadge, RiskBadge, StatusBadge } from '@/components/common/Badges'
import { useAsyncData } from '@/hooks/useAsyncData'
import { formatINR } from '@/lib/format'
import { services } from '@/services'
import { useState } from 'react'
import type { Lane } from '@/types/domain'

export function OverviewPage() {
  const navigate = useNavigate()
  const [range, setRange] = useState<'7d' | '30d' | '90d'>('30d')
  const kpis = useAsyncData(() => services.recovery.getOverviewKpis(), [])
  const trend = useAsyncData(() => services.recovery.getTrend(range), [range])
  const opportunities = useAsyncData(() => services.recovery.getOpportunities(), [])
  const pulse = useAsyncData(() => services.recovery.getPulse(), [])
  const active = useAsyncData(() => services.recovery.getActiveCases(), [])

  if (kpis.error) {
    return <ErrorState onRetry={kpis.reload} />
  }

  return (
    <div>
      <PageHeader
        title="Revenue Recovery"
        subtitle="Monitor and recover revenue across your customer lifecycle."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.loading || !kpis.data ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))
        ) : (
          <>
            <MetricCard
              label="Revenue at Risk"
              value={formatINR(kpis.data.revenueAtRisk, true)}
              delta={kpis.data.revenueAtRiskDelta}
              hint="vs prior period"
            />
            <MetricCard
              label="Recovered"
              value={formatINR(kpis.data.recovered, true)}
              delta={kpis.data.recoveredDelta}
              hint="vs prior period"
            />
            <MetricCard
              label="Recovery Rate"
              value={`${kpis.data.recoveryRate}%`}
              delta={kpis.data.recoveryRateDelta}
              hint="vs prior period"
            />
            <MetricCard
              label="Expected Recovery"
              value={formatINR(kpis.data.expectedRecovery, true)}
              delta={kpis.data.expectedRecoveryDelta}
              hint="pipeline EV"
            />
          </>
        )}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Panel
          className="xl:col-span-2"
          title="Revenue Recovery Trend"
          subtitle="Revenue at risk vs revenue recovered"
          action={
            <div className="flex rounded-lg border border-ink-200 p-0.5">
              {(['7d', '30d', '90d'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRange(r)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                    range === r
                      ? 'bg-ink-900 text-white'
                      : 'text-ink-500 hover:text-ink-800'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          }
        >
          {trend.loading ? (
            <Skeleton className="h-64" />
          ) : !trend.data?.length ? (
            <EmptyState title="No trend data" description="Trend series will appear here." />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend.data}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: '#6b7385' }}
                    tickFormatter={(v) => String(v).slice(5)}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#6b7385' }}
                    tickFormatter={(v) => formatINR(Number(v), true)}
                    width={56}
                  />
                  <Tooltip
                    formatter={(value: number) => formatINR(value)}
                    contentStyle={{
                      borderRadius: 8,
                      borderColor: '#dde1e8',
                      fontSize: 12,
                    }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="atRisk"
                    name="At Risk"
                    stroke="#a78bfa"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="recovered"
                    name="Recovered"
                    stroke="#6b46ef"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel
          title="Recovery Opportunities"
          subtitle={
            opportunities.data
              ? `${opportunities.data.reduce((s, o) => s + o.cases, 0)} cases need attention`
              : 'Loading…'
          }
        >
          {opportunities.loading || !opportunities.data ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12" />
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {opportunities.data.map((o) => (
                <Link
                  key={o.lane}
                  to={`/recovery?lane=${o.lane}`}
                  className="flex items-center justify-between rounded-lg border border-ink-100 px-3 py-2.5 transition hover:border-podium-200 hover:bg-podium-50/40"
                >
                  <div>
                    <div className="text-sm font-medium text-ink-800">{o.label}</div>
                    <div className="text-xs text-ink-400">{o.cases} cases</div>
                  </div>
                  <div className="text-sm font-semibold text-ink-900">
                    {formatINR(o.amount, true)}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-5">
        <Panel className="xl:col-span-2" title="Recovery Pulse" subtitle="Live recovery activity">
          {pulse.loading || !pulse.data ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {pulse.data.map((event) => (
                <article
                  key={event.id}
                  className="rounded-lg border border-ink-100 bg-ink-50/50 p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-mono text-xs text-ink-400">{event.timestamp}</div>
                    <LaneBadge lane={event.lane as Lane} />
                  </div>
                  <div className="mt-1 text-sm font-semibold text-ink-900">
                    {event.customerName}
                  </div>
                  <div className="text-xs text-ink-500">
                    {event.lane} · {formatINR(event.amount)}
                  </div>
                  <ul className="mt-2 space-y-1">
                    {event.summary.map((line) => (
                      <li key={line} className="text-xs leading-relaxed text-ink-600">
                        {line}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-[11px] font-medium uppercase tracking-wide text-ink-400">
                      {event.status}
                    </span>
                    <Link
                      to={`/recovery/${event.caseId}`}
                      className="text-xs font-semibold text-podium-700 hover:underline"
                    >
                      View case
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          className="xl:col-span-3"
          title="Active Recovery Cases"
          subtitle="Operational queue"
          action={
            <Link to="/recovery" className="text-xs font-semibold text-podium-700 hover:underline">
              View all
            </Link>
          }
        >
          {active.loading || !active.data ? (
            <Skeleton className="h-64" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-ink-400">
                  <tr className="border-b border-ink-100">
                    <th className="pb-2 font-medium">Customer</th>
                    <th className="pb-2 font-medium">Lane</th>
                    <th className="pb-2 font-medium">Risk</th>
                    <th className="pb-2 font-medium">Amount</th>
                    <th className="pb-2 font-medium">State</th>
                    <th className="pb-2 font-medium">Next Action</th>
                    <th className="pb-2 font-medium">Expected Value</th>
                    <th className="pb-2 font-medium">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {active.data.map((c) => (
                    <tr
                      key={c.id}
                      className="cursor-pointer border-b border-ink-50 hover:bg-ink-50/80"
                      onClick={() => navigate(`/recovery/${c.id}`)}
                    >
                      <td className="py-2.5 font-medium text-ink-900">
                        <Link to={`/recovery/${c.id}`} className="hover:text-podium-700">
                          {c.customerName}
                        </Link>
                      </td>
                      <td className="py-2.5">
                        <LaneBadge lane={c.lane} />
                      </td>
                      <td className="py-2.5">
                        <RiskBadge risk={c.risk} />
                      </td>
                      <td className="py-2.5">{formatINR(c.amountAtRisk)}</td>
                      <td className="py-2.5">
                        <StatusBadge state={c.state} />
                      </td>
                      <td className="py-2.5 text-ink-600">{c.nextAction}</td>
                      <td className="py-2.5 font-medium">{formatINR(c.expectedValue)}</td>
                      <td className="py-2.5 text-ink-400">{c.updatedAt}</td>
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
