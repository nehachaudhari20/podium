import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { StatusBadge } from '@/components/common/Badges'
import { useAsyncData } from '@/hooks/useAsyncData'
import { formatINR } from '@/lib/format'
import { services } from '@/services'

export function CustomersPage() {
  const [search, setSearch] = useState('')
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsyncData(
    () => services.customers.listCustomers(search),
    [search],
  )

  return (
    <div>
      <PageHeader
        title="Customers"
        subtitle="Browse customers with active or recent revenue exposure."
      />

      <Panel className="mb-4">
        <label className="block text-xs font-medium text-ink-500">
          Search customers
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Name, ID, or email"
            className="mt-1 w-full max-w-md rounded-lg border border-ink-200 px-3 py-2 text-sm"
          />
        </label>
      </Panel>

      {error ? (
        <ErrorState onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton className="h-80" />
      ) : data.length === 0 ? (
        <EmptyState
          title="No search results"
          description="No customers match your query."
        />
      ) : (
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-ink-400">
                <tr className="border-b border-ink-100">
                  <th className="pb-2 font-medium">Customer</th>
                  <th className="pb-2 font-medium">Customer ID</th>
                  <th className="pb-2 font-medium">Revenue at Risk</th>
                  <th className="pb-2 font-medium">Active Cases</th>
                  <th className="pb-2 font-medium">Last Activity</th>
                  <th className="pb-2 font-medium">Recovery Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((c) => (
                  <tr
                    key={c.id}
                    className="cursor-pointer border-b border-ink-50 hover:bg-ink-50"
                    onClick={() => navigate(`/customers/${c.id}`)}
                  >
                    <td className="py-3">
                      <div className="font-medium text-ink-900">{c.name}</div>
                      <div className="text-xs text-ink-400">{c.email}</div>
                    </td>
                    <td className="py-3 font-mono text-xs text-ink-600">{c.id}</td>
                    <td className="py-3 font-medium">{formatINR(c.revenueAtRisk)}</td>
                    <td className="py-3">{c.activeCases}</td>
                    <td className="py-3 text-ink-500">{c.lastActivity}</td>
                    <td className="py-3">
                      <StatusBadge state={c.recoveryStatus.toLowerCase().replace(/ /g, '_')} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  )
}

export function CustomerDetailPage({ customerId }: { customerId: string }) {
  const { data, loading, error, reload } = useAsyncData(
    () => services.customers.getCustomer(customerId),
    [customerId],
  )

  if (error) return <ErrorState onRetry={reload} />
  if (loading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title={data.name}
        subtitle={`${data.id} · ${formatINR(data.totalExposure)} total revenue exposure`}
      />

      <div className="mb-4 grid gap-3 md:grid-cols-3">
        {data.lanes.length === 0 ? (
          <EmptyState title="No active lane exposure" />
        ) : (
          data.lanes.map((lane) => (
            <Link
              key={lane.lane}
              to={lane.caseId ? `/recovery/${lane.caseId}` : '/recovery'}
              className="rounded-xl border border-ink-200 bg-white p-4 shadow-soft transition hover:border-podium-200 hover:bg-podium-50/30"
            >
              <div className="text-xs font-semibold uppercase tracking-wide text-ink-400">
                {lane.lane}
              </div>
              <div className="mt-2 text-xl font-semibold text-ink-900">
                {formatINR(lane.amount)}
              </div>
              <div className="mt-1 text-sm text-ink-500">{lane.status}</div>
            </Link>
          ))
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title="Customer Recovery Timeline">
          <ol className="relative space-y-0 border-l border-ink-200 ml-2">
            {data.timeline.map((event) => (
              <li key={event.id} className="relative pb-6 pl-6 last:pb-0">
                <span className="absolute -left-1.5 top-1.5 h-3 w-3 rounded-full border-2 border-white bg-podium-500" />
                <div className="text-xs font-medium text-ink-400">{event.date}</div>
                <div className="mt-0.5 text-sm font-semibold text-ink-900">{event.title}</div>
                <p className="mt-1 text-sm text-ink-500">{event.description}</p>
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-ink-400">
                  {event.lane && <span>{event.lane}</span>}
                  {event.amount !== undefined && <span>{formatINR(event.amount)}</span>}
                  {event.status && <span>{event.status}</span>}
                </div>
              </li>
            ))}
          </ol>
        </Panel>

        <Panel title="Customer Recovery Summary">
          <dl className="space-y-4">
            <div>
              <dt className="text-xs text-ink-400">Total Revenue at Risk</dt>
              <dd className="mt-1 text-xl font-semibold">{formatINR(data.revenueAtRisk)}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-400">Recovered</dt>
              <dd className="mt-1 text-sm font-medium text-ink-800">
                {formatINR(data.recovered)} / {formatINR(data.totalExposure)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-400">Active Cases</dt>
              <dd className="mt-1 text-xl font-semibold">{data.activeCases}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-400">Current Recovery State</dt>
              <dd className="mt-1">
                <StatusBadge state={data.recoveryState.toLowerCase().replace(/ /g, '_')} />
              </dd>
            </div>
          </dl>
        </Panel>
      </div>
    </div>
  )
}
