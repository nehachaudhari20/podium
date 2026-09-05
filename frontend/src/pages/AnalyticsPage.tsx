import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { MetricCard } from '@/components/common/MetricCard'
import {
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { useAsyncData } from '@/hooks/useAsyncData'
import { formatINR, titleCase } from '@/lib/format'
import { services } from '@/services'
import type { Lane } from '@/types/domain'

const pieColors = ['#6b46ef', '#a78bfa', '#38bdf8', '#f59e0b', '#fb7185']

export function AnalyticsPage() {
  const [range, setRange] = useState<'7d' | '30d' | '90d'>('30d')
  const [lane, setLane] = useState<Lane | 'all'>('all')

  const summary = useAsyncData(
    () => services.analytics.getSummary(range, lane),
    [range, lane],
  )
  const trend = useAsyncData(
    () => services.analytics.getTrend(range, lane),
    [range, lane],
  )
  const lanes = useAsyncData(() => services.analytics.getLaneBreakdown(range), [range])
  const outcomes = useAsyncData(
    () => services.analytics.getOutcomes(range, lane),
    [range, lane],
  )
  const actions = useAsyncData(
    () => services.analytics.getActionEffectiveness(lane),
    [lane],
  )

  if (summary.error) return <ErrorState onRetry={summary.reload} />

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Merchant-level recovery performance reporting."
        actions={
          <div className="flex flex-wrap gap-2">
            <div className="flex rounded-lg border border-ink-200 p-0.5">
              {(['7d', '30d', '90d'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRange(r)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                    range === r ? 'bg-ink-900 text-white' : 'text-ink-500'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
            <select
              value={lane}
              onChange={(e) => setLane(e.target.value as Lane | 'all')}
              className="rounded-lg border border-ink-200 px-2.5 py-1.5 text-xs"
            >
              <option value="all">All lanes</option>
              <option value="subscription">Subscription</option>
              <option value="checkout">Checkout</option>
              <option value="receivable">Receivable</option>
            </select>
          </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {summary.loading || !summary.data
          ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24" />)
          : (
            <>
              <MetricCard label="Recovery Rate" value={`${summary.data.recoveryRate}%`} />
              <MetricCard
                label="Revenue Recovered"
                value={formatINR(summary.data.revenueRecovered, true)}
              />
              <MetricCard
                label="Revenue at Risk"
                value={formatINR(summary.data.revenueAtRisk, true)}
              />
              <MetricCard
                label="Expected Recovery"
                value={formatINR(summary.data.expectedRecovery, true)}
              />
              <MetricCard
                label="Intervention Cost"
                value={formatINR(summary.data.interventionCost, true)}
              />
              <MetricCard
                label="Net Recovery Value"
                value={formatINR(summary.data.netRecoveryValue, true)}
              />
            </>
          )}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Panel title="Recovery Trend">
          {trend.loading || !trend.data ? (
            <Skeleton className="h-64" />
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
                  <Tooltip formatter={(v: number) => formatINR(v)} />
                  <Line
                    type="monotone"
                    dataKey="value"
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

        <Panel title="Revenue Recovered by Lane">
          {lanes.loading || !lanes.data ? (
            <Skeleton className="h-64" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={lanes.data.map((l) => ({ ...l, name: titleCase(l.lane) }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#6b7385' }} />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#6b7385' }}
                    tickFormatter={(v) => formatINR(Number(v), true)}
                    width={56}
                  />
                  <Tooltip formatter={(v: number) => formatINR(v)} />
                  <Bar dataKey="recovered" fill="#6b46ef" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel title="Recovery Rate by Lane">
          {lanes.loading || !lanes.data ? (
            <Skeleton className="h-64" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={lanes.data.map((l) => ({ ...l, name: titleCase(l.lane) }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#6b7385' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#6b7385' }} tickFormatter={(v) => `${v}%`} />
                  <Tooltip formatter={(v: number) => `${v}%`} />
                  <Bar dataKey="rate" fill="#a78bfa" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel title="Recovery Outcomes Distribution">
          {outcomes.loading || !outcomes.data ? (
            <Skeleton className="h-64" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={outcomes.data}
                    dataKey="count"
                    nameKey="label"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={2}
                  >
                    {outcomes.data.map((_, i) => (
                      <Cell key={i} fill={pieColors[i % pieColors.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>
      </div>

      <Panel className="mt-4" title="Action Effectiveness">
        {actions.loading || !actions.data ? (
          <Skeleton className="h-48" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="text-xs uppercase text-ink-400">
                <tr className="border-b border-ink-100">
                  <th className="pb-2 font-medium">Action</th>
                  <th className="pb-2 font-medium">Attempts</th>
                  <th className="pb-2 font-medium">Recovery</th>
                  <th className="pb-2 font-medium">Avg Cost</th>
                </tr>
              </thead>
              <tbody>
                {actions.data.map((row) => (
                  <tr key={row.action} className="border-b border-ink-50">
                    <td className="py-2.5 font-medium">{row.action}</td>
                    <td className="py-2.5">{row.attempts}</td>
                    <td className="py-2.5">{row.recoveryRate}%</td>
                    <td className="py-2.5">{formatINR(row.avgCost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
