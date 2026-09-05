import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Button,
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { Badge } from '@/components/common/Badges'
import { useAsyncData } from '@/hooks/useAsyncData'
import { services } from '@/services'
import type { AuditEventType } from '@/types/domain'

const typeStyles: Record<AuditEventType, string> = {
  decision: 'bg-podium-50 text-podium-700 border-podium-200',
  policy: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  action: 'bg-sky-50 text-sky-700 border-sky-200',
  outcome: 'bg-amber-50 text-amber-700 border-amber-200',
  learning: 'bg-violet-50 text-violet-700 border-violet-200',
  coordination: 'bg-slate-50 text-slate-700 border-slate-200',
}

export function AuditPage() {
  const [search, setSearch] = useState('')
  const [type, setType] = useState<AuditEventType | 'all'>('all')
  const filters = useMemo(() => ({ search, type }), [search, type])
  const { data, loading, error, reload } = useAsyncData(
    () => services.audit.listEvents(filters),
    [JSON.stringify(filters)],
  )

  return (
    <div>
      <PageHeader
        title="Audit Log"
        subtitle="Operational events across decision, policy, action, and learning."
      />

      <Panel className="mb-4">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="block text-xs font-medium text-ink-500">
            Search
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Customer, case, or event"
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-xs font-medium text-ink-500">
            Event type
            <select
              value={type}
              onChange={(e) => setType(e.target.value as AuditEventType | 'all')}
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
            >
              <option value="all">All</option>
              <option value="decision">Decision</option>
              <option value="policy">Policy</option>
              <option value="action">Action</option>
              <option value="outcome">Outcome</option>
              <option value="learning">Learning</option>
              <option value="coordination">Coordination</option>
            </select>
          </label>
          <div className="flex items-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearch('')
                setType('all')
              }}
            >
              Clear filters
            </Button>
          </div>
        </div>
      </Panel>

      {error ? (
        <ErrorState onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton className="h-80" />
      ) : data.length === 0 ? (
        <EmptyState title="No matching events" description="Try a different filter." />
      ) : (
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-ink-400">
                <tr className="border-b border-ink-100">
                  <th className="pb-2 font-medium">Timestamp</th>
                  <th className="pb-2 font-medium">Event</th>
                  <th className="pb-2 font-medium">Customer</th>
                  <th className="pb-2 font-medium">Case</th>
                  <th className="pb-2 font-medium">Actor</th>
                  <th className="pb-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((e) => (
                  <tr key={e.id} className="border-b border-ink-50 hover:bg-ink-50/80">
                    <td className="py-3 font-mono text-xs text-ink-500">{e.timestamp}</td>
                    <td className="py-3">
                      <div className="font-medium text-ink-900">{e.event}</div>
                      <div className="mt-1">
                        <Badge className={typeStyles[e.type]}>{e.type}</Badge>
                      </div>
                    </td>
                    <td className="py-3">
                      <Link
                        to={`/customers/${e.customerId}`}
                        className="font-medium hover:text-podium-700"
                      >
                        {e.customerName}
                      </Link>
                    </td>
                    <td className="py-3">
                      <Link
                        to={`/recovery/${e.caseId}`}
                        className="font-mono text-xs text-podium-700 hover:underline"
                      >
                        {e.caseId}
                      </Link>
                    </td>
                    <td className="py-3 text-ink-600">{e.actor}</td>
                    <td className="py-3 text-ink-600">{e.status}</td>
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
