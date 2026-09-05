import { useMemo } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { LaneBadge, RiskBadge, StatusBadge } from '@/components/common/Badges'
import {
  Button,
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { useToast } from '@/components/common/Toast'
import { useAsyncData } from '@/hooks/useAsyncData'
import { formatINR } from '@/lib/format'
import { services } from '@/services'
import type { CaseState, Lane, RecoveryFilters, RiskLevel } from '@/types/domain'

export function RecoveryPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { toast } = useToast()

  const filters: RecoveryFilters = useMemo(
    () => ({
      search: params.get('search') ?? '',
      lane: (params.get('lane') as Lane | 'all') || 'all',
      risk: (params.get('risk') as RiskLevel | 'all') || 'all',
      state: (params.get('state') as CaseState | 'all') || 'all',
      sortBy: (params.get('sortBy') as RecoveryFilters['sortBy']) || 'updated',
      sortDir: (params.get('sortDir') as 'asc' | 'desc') || 'desc',
      page: Number(params.get('page') || 1),
      pageSize: 8,
    }),
    [params],
  )

  const { data, loading, error, reload } = useAsyncData(
    () => services.recovery.listCases(filters),
    [JSON.stringify(filters)],
  )

  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params)
    Object.entries(patch).forEach(([k, v]) => {
      if (!v || v === 'all' || (k === 'page' && v === '1') || (k === 'search' && !v)) {
        if (k === 'search' && !v) next.delete(k)
        else if (v === 'all' || (k === 'page' && v === '1')) next.delete(k)
        else next.set(k, v)
      } else {
        next.set(k, v)
      }
    })
    if (!('page' in patch)) next.delete('page')
    setParams(next)
  }

  const clearFilters = () => {
    setParams({})
    toast('Filters cleared')
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1

  return (
    <div>
      <PageHeader
        title="Recovery"
        subtitle="Prioritize revenue-risk cases and manage recovery actions."
      />

      <Panel className="mb-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <label className="block text-xs font-medium text-ink-500">
            Search
            <input
              value={filters.search}
              onChange={(e) => update({ search: e.target.value, page: '1' })}
              placeholder="Customer or case"
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-xs font-medium text-ink-500">
            Lane
            <select
              value={filters.lane}
              onChange={(e) => update({ lane: e.target.value, page: '1' })}
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
            >
              <option value="all">All lanes</option>
              <option value="subscription">Subscription</option>
              <option value="checkout">Checkout</option>
              <option value="receivable">Receivable</option>
              <option value="failed_payment">Failed Payments</option>
            </select>
          </label>
          <label className="block text-xs font-medium text-ink-500">
            Risk
            <select
              value={filters.risk}
              onChange={(e) => update({ risk: e.target.value, page: '1' })}
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
            >
              <option value="all">All</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </label>
          <label className="block text-xs font-medium text-ink-500">
            State
            <select
              value={filters.state}
              onChange={(e) => update({ state: e.target.value, page: '1' })}
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
            >
              <option value="all">All</option>
              <option value="needs_action">Needs Action</option>
              <option value="waiting">Waiting</option>
              <option value="recovered">Recovered</option>
              <option value="escalated">Escalated</option>
              <option value="deferred">Deferred</option>
            </select>
          </label>
          <label className="block text-xs font-medium text-ink-500">
            Sort
            <select
              value={`${filters.sortBy}:${filters.sortDir}`}
              onChange={(e) => {
                const [sortBy, sortDir] = e.target.value.split(':')
                update({ sortBy, sortDir, page: '1' })
              }}
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
            >
              <option value="updated:desc">Recently updated</option>
              <option value="amount:desc">Amount high → low</option>
              <option value="amount:asc">Amount low → high</option>
              <option value="risk:desc">Risk high → low</option>
              <option value="expected:desc">Expected value</option>
            </select>
          </label>
        </div>
        <div className="mt-3">
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            Clear filters
          </Button>
        </div>
      </Panel>

      {error ? (
        <ErrorState onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton className="h-96" />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No matching cases"
          description="Try adjusting search or filters."
          action={
            <Button variant="secondary" onClick={clearFilters}>
              Clear filters
            </Button>
          }
        />
      ) : (
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-ink-400">
                <tr className="border-b border-ink-100">
                  <th className="pb-2 font-medium">Customer</th>
                  <th className="pb-2 font-medium">Case</th>
                  <th className="pb-2 font-medium">Lane</th>
                  <th className="pb-2 font-medium">Amount at Risk</th>
                  <th className="pb-2 font-medium">Risk</th>
                  <th className="pb-2 font-medium">Current State</th>
                  <th className="pb-2 font-medium">Next Action</th>
                  <th className="pb-2 font-medium">Expected Net Value</th>
                  <th className="pb-2 font-medium">Last Updated</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr
                    key={c.id}
                    className="cursor-pointer border-b border-ink-50 hover:bg-ink-50"
                    onClick={() => navigate(`/recovery/${c.id}`)}
                  >
                    <td className="py-3 font-medium">
                      <Link
                        to={`/customers/${c.customerId}`}
                        className="hover:text-podium-700"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {c.customerName}
                      </Link>
                    </td>
                    <td className="py-3 text-ink-600">{c.caseRef}</td>
                    <td className="py-3">
                      <LaneBadge lane={c.lane} />
                    </td>
                    <td className="py-3">{formatINR(c.amountAtRisk)}</td>
                    <td className="py-3">
                      <RiskBadge risk={c.risk} />
                    </td>
                    <td className="py-3">
                      <StatusBadge state={c.state} />
                    </td>
                    <td className="py-3 text-ink-600">{c.nextAction}</td>
                    <td className="py-3 font-medium">{formatINR(c.expectedValue)}</td>
                    <td className="py-3 text-ink-400">{c.updatedAt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between text-sm text-ink-500">
            <span>
              Showing {(data.page - 1) * data.pageSize + 1}–
              {Math.min(data.page * data.pageSize, data.total)} of {data.total}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={data.page <= 1}
                onClick={() => update({ page: String(data.page - 1) })}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={data.page >= totalPages}
                onClick={() => update({ page: String(data.page + 1) })}
              >
                Next
              </Button>
            </div>
          </div>
        </Panel>
      )}
    </div>
  )
}
