import { useState } from 'react'
import { Link } from 'react-router-dom'
import { X } from 'lucide-react'
import { LaneBadge, RiskBadge, StageBadge, StatusBadge } from '@/components/common/Badges'
import {
  Button,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { useAsyncData } from '@/hooks/useAsyncData'
import { formatINR, formatPercent, cn } from '@/lib/format'
import { services } from '@/services'
import type { PipelineStage, RecoveryCase } from '@/types/domain'

function WhyActionDrawer({
  open,
  onClose,
  decision,
}: {
  open: boolean
  onClose: () => void
  decision: NonNullable<RecoveryCase['decision']>
}) {
  if (!open) return null
  const why = decision.whyDrawer
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        className="absolute inset-0 bg-ink-900/30"
        aria-label="Close drawer"
        onClick={onClose}
      />
      <aside className="relative z-10 flex h-full w-full max-w-md flex-col bg-white shadow-panel">
        <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-ink-900">{why.title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-ink-400 hover:bg-ink-100"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {why.sections.map((section) => (
            <div key={section.heading} className="mb-5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-400">
                {section.heading}
              </h3>
              <ul className="mt-2 space-y-1.5">
                {section.bullets.map((b) => (
                  <li key={b} className="text-sm text-ink-700">
                    {b}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <div className="rounded-lg border border-podium-200 bg-podium-50 px-3 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-podium-700">
              Decision
            </div>
            <div className="mt-1 text-sm font-semibold text-ink-900">{why.decision}</div>
          </div>
        </div>
      </aside>
    </div>
  )
}

export function CaseDetailPage({ caseId }: { caseId: string }) {
  const { data, loading, error, reload } = useAsyncData(
    () => services.recovery.getCase(caseId),
    [caseId],
  )
  const [activeStage, setActiveStage] = useState<PipelineStage | null>(null)
  const [whyOpen, setWhyOpen] = useState(false)

  if (error) return <ErrorState onRetry={reload} />
  if (loading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  const decision = data.decision
  const stage = activeStage ?? data.pipeline?.find((p) => p.status === 'active')?.stage ?? 'diagnosis'

  return (
    <div>
      <PageHeader
        title={data.customerName}
        subtitle={`${data.lane} · ${data.caseRef}`}
        actions={
          <div className="flex items-center gap-2">
            <RiskBadge risk={data.risk} />
            {data.priority === 'high' && (
              <span className="rounded-md border border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-semibold text-rose-700">
                High Priority
              </span>
            )}
            <Link
              to={`/customers/${data.customerId}`}
              className="text-xs font-semibold text-podium-700 hover:underline"
            >
              Customer 360
            </Link>
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-end gap-4 rounded-xl border border-ink-200 bg-white p-4 shadow-soft">
        <div>
          <div className="text-xs text-ink-400">Amount at Risk</div>
          <div className="text-2xl font-semibold">{formatINR(data.amountAtRisk)}</div>
          {data.daysOverdue !== undefined && (
            <div className="text-xs text-ink-500">{data.daysOverdue} days overdue</div>
          )}
        </div>
        <div className="grid flex-1 grid-cols-2 gap-3 md:grid-cols-4">
          <div>
            <div className="text-xs text-ink-400">Expected Recovery</div>
            <div className="text-lg font-semibold">
              {formatINR(data.expectedRecovery ?? data.expectedValue)}
            </div>
          </div>
          <div>
            <div className="text-xs text-ink-400">Remaining</div>
            <div className="text-lg font-semibold">
              {formatINR(data.remaining ?? data.amountAtRisk)}
            </div>
          </div>
          <div>
            <div className="text-xs text-ink-400">Current State</div>
            <div className="mt-1">
              <StatusBadge state={data.state} />
            </div>
          </div>
          <div>
            <div className="text-xs text-ink-400">Lane</div>
            <div className="mt-1">
              <LaneBadge lane={data.lane} />
            </div>
          </div>
        </div>
      </div>

      {data.pipeline && (
        <Panel className="mb-4" title="Recovery Decision Pipeline" subtitle="Click a stage for details">
          <div className="flex gap-2 overflow-x-auto pb-1">
            {data.pipeline.map((step, idx) => (
              <button
                key={step.stage}
                type="button"
                onClick={() => setActiveStage(step.stage)}
                className={cn(
                  'min-w-[110px] rounded-lg border px-3 py-2 text-left transition',
                  stage === step.stage
                    ? 'border-podium-300 bg-podium-50'
                    : 'border-ink-200 bg-white hover:bg-ink-50',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                    {idx + 1}. {step.label}
                  </span>
                  <StageBadge status={step.status} />
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-ink-600">{step.summary}</p>
              </button>
            ))}
          </div>
          <div className="mt-3 rounded-lg bg-ink-50 px-3 py-2 text-sm text-ink-600">
            {data.pipeline.find((p) => p.stage === stage)?.summary}
          </div>
        </Panel>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Context">
          {data.context ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              {Object.entries(data.context).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-xs text-ink-400">{k}</dt>
                  <dd className="mt-0.5 font-medium text-ink-800">{v}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm text-ink-500">Context details unavailable for this case.</p>
          )}
        </Panel>

        <Panel
          title="Diagnosis"
          action={
            decision && (
              <Button size="sm" onClick={() => setWhyOpen(true)}>
                Why this action?
              </Button>
            )
          }
        >
          {decision ? (
            <div className="space-y-3">
              <div>
                <div className="text-xs text-ink-400">Likely cause</div>
                <div className="text-sm font-semibold text-ink-900">{decision.likelyCause}</div>
              </div>
              <div>
                <div className="text-xs text-ink-400">Confidence</div>
                <div className="text-sm font-semibold">{decision.confidence}%</div>
              </div>
              <p className="text-sm leading-relaxed text-ink-600">{decision.reasoning}</p>
              <div className="rounded-lg border border-ink-100 bg-ink-50 px-3 py-2">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                  Intelligence recommendation
                </div>
                <div className="mt-1 text-sm font-medium text-ink-900">
                  {decision.selectedAction}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-500">Diagnosis not yet available.</p>
          )}
        </Panel>

        <Panel title="Candidate Actions">
          {decision?.candidates ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-left text-sm">
                <thead className="text-xs uppercase text-ink-400">
                  <tr className="border-b border-ink-100">
                    <th className="pb-2 font-medium">Action</th>
                    <th className="pb-2 font-medium">Probability</th>
                    <th className="pb-2 font-medium">Cost</th>
                    <th className="pb-2 font-medium">Expected Net</th>
                  </tr>
                </thead>
                <tbody>
                  {decision.candidates.map((c) => (
                    <tr
                      key={c.id}
                      className={cn(
                        'border-b border-ink-50',
                        c.selected && 'bg-podium-50/60',
                      )}
                    >
                      <td className="py-2.5 font-medium">
                        {c.action}
                        {c.selected && (
                          <span className="ml-2 text-[10px] font-semibold uppercase text-podium-700">
                            Selected
                          </span>
                        )}
                      </td>
                      <td className="py-2.5">{formatPercent(c.probability * 100, 0)}</td>
                      <td className="py-2.5">{formatINR(c.cost)}</td>
                      <td className="py-2.5 font-medium">{formatINR(c.expectedNet)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-ink-500">Candidates not available.</p>
          )}
        </Panel>

        <Panel title="Policy Check" subtitle="Deterministic enforcement">
          {decision ? (
            <div>
              <ul className="space-y-2">
                {decision.policyChecks.map((item) => (
                  <li key={item.label} className="flex items-center gap-2 text-sm">
                    <span className={item.passed ? 'text-emerald-600' : 'text-rose-600'}>
                      {item.passed ? '✓' : '✗'}
                    </span>
                    <span className="text-ink-700">{item.label}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                  Status
                </div>
                <div className="text-sm font-semibold uppercase text-emerald-800">
                  {decision.policyStatus}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-500">Policy evaluation pending.</p>
          )}
        </Panel>

        <Panel title="Outcome">
          {data.outcome ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs text-ink-400">Action</dt>
                <dd className="font-medium">{data.outcome.action}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-400">Status</dt>
                <dd>
                  <StatusBadge state={data.outcome.status} />
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-ink-400">Outcome</dt>
                <dd className="font-medium">{data.outcome.outcome}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-400">Recovered</dt>
                <dd className="text-lg font-semibold">{formatINR(data.outcome.recovered)}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-ink-500">No outcome recorded yet.</p>
          )}
        </Panel>

        <Panel title="Learning Signal">
          {data.learning ? (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-ink-400">Action</div>
                  <div className="font-medium">{data.learning.action}</div>
                </div>
                <div>
                  <div className="text-xs text-ink-400">Observations</div>
                  <div className="font-medium">{data.learning.observations}</div>
                </div>
                <div>
                  <div className="text-xs text-ink-400">Observed success</div>
                  <div className="font-medium">
                    {formatPercent(data.learning.observedSuccess * 100, 0)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-ink-400">Prediction</div>
                  <div className="font-medium">
                    {formatPercent(data.learning.prediction * 100, 0)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-ink-400">Confidence</div>
                  <div className="font-medium uppercase">{data.learning.confidence}</div>
                </div>
                <div>
                  <div className="text-xs text-ink-400">Outcome</div>
                  <div className="font-medium">{data.learning.outcome}</div>
                </div>
              </div>
              <Link to="/learning" className="text-xs font-semibold text-podium-700 hover:underline">
                View learning evidence
              </Link>
            </div>
          ) : (
            <p className="text-sm text-ink-500">Learning signal pending.</p>
          )}
        </Panel>
      </div>

      {decision && (
        <WhyActionDrawer open={whyOpen} onClose={() => setWhyOpen(false)} decision={decision} />
      )}
    </div>
  )
}
