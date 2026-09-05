import { useEffect, useState } from 'react'
import {
  Button,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { useToast } from '@/components/common/Toast'
import { useAsyncData } from '@/hooks/useAsyncData'
import { services } from '@/services'
import type { SettingsState } from '@/types/domain'
import { formatINR } from '@/lib/format'

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
}) {
  return (
    <label className="flex items-center justify-between gap-3 text-sm">
      <span className="text-ink-700">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 rounded-full transition ${
          checked ? 'bg-podium-600' : 'bg-ink-200'
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
            checked ? 'left-5' : 'left-0.5'
          }`}
        />
      </button>
    </label>
  )
}

export function SettingsPage() {
  const { data, loading, error, reload } = useAsyncData(() => services.settings.get(), [])
  const [form, setForm] = useState<SettingsState | null>(null)
  const { toast } = useToast()

  useEffect(() => {
    if (data) setForm(data)
  }, [data])

  if (error) return <ErrorState onRetry={reload} />
  if (loading || !form) return <Skeleton className="h-96" />

  const update = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev))
  }

  const save = async () => {
    const next = await services.settings.save(form)
    setForm(next)
    toast('Settings saved', 'success')
  }

  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="Recovery policies, capacity, and operational preferences."
        actions={
          <Button onClick={save}>Save changes</Button>
        }
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Recovery Policies">
          <div className="space-y-4">
            <label className="block text-xs font-medium text-ink-500">
              Max contacts / 24h
              <input
                type="number"
                min={0}
                value={form.maxContacts24h}
                onChange={(e) => update('maxContacts24h', Number(e.target.value))}
                className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-xs font-medium text-ink-500">
              Minimum contact gap (hours)
              <input
                type="number"
                min={0}
                value={form.minContactGapHours}
                onChange={(e) => update('minContactGapHours', Number(e.target.value))}
                className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-xs font-medium text-ink-500">
              Max human escalations
              <input
                type="number"
                min={0}
                value={form.maxHumanEscalations}
                onChange={(e) => update('maxHumanEscalations', Number(e.target.value))}
                className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-xs font-medium text-ink-500">
              Max active incentives
              <input
                type="number"
                min={0}
                value={form.maxActiveIncentives}
                onChange={(e) => update('maxActiveIncentives', Number(e.target.value))}
                className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-xs font-medium text-ink-500">
              Human escalation threshold
              <input
                type="number"
                min={0}
                step={1000}
                value={form.humanEscalationThreshold}
                onChange={(e) =>
                  update('humanEscalationThreshold', Number(e.target.value))
                }
                className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
              />
              <span className="mt-1 block text-xs text-ink-400">
                Currently {formatINR(form.humanEscalationThreshold)}
              </span>
            </label>
          </div>
        </Panel>

        <Panel title="Capacity">
          <p className="mb-4 text-sm text-ink-500">
            Capacity budgets are enforced deterministically during coordination. These
            controls are UI-only until Phase 10 backend integration.
          </p>
          <div className="space-y-3 rounded-lg border border-ink-100 bg-ink-50/60 p-3 text-sm">
            <div className="flex justify-between">
              <span>Customer contact budget</span>
              <span className="font-medium">88% utilized</span>
            </div>
            <div className="flex justify-between">
              <span>Human escalation slots</span>
              <span className="font-medium">52% utilized</span>
            </div>
            <div className="flex justify-between">
              <span>Incentive budget</span>
              <span className="font-medium">41% utilized</span>
            </div>
          </div>
        </Panel>

        <Panel title="Intervention Costs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-ink-400">
                <tr className="border-b border-ink-100">
                  <th className="pb-2 font-medium">Action</th>
                  <th className="pb-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['Payment Link', 2],
                  ['Invoice Reminder', 2],
                  ['Retry', 0],
                  ['Human Follow-up', 500],
                  ['Checkout Reminder', 1],
                ].map(([action, cost]) => (
                  <tr key={String(action)} className="border-b border-ink-50">
                    <td className="py-2.5">{action}</td>
                    <td className="py-2.5 font-medium">{formatINR(Number(cost))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Notifications">
          <div className="space-y-4">
            <Toggle
              label="Email notifications"
              checked={form.emailNotifications}
              onChange={(v) => update('emailNotifications', v)}
            />
            <Toggle
              label="Slack notifications"
              checked={form.slackNotifications}
              onChange={(v) => update('slackNotifications', v)}
            />
          </div>
        </Panel>

        <Panel title="Team">
          <ul className="space-y-3 text-sm">
            {[
              ['Ops Lead', 'Merchant Admin'],
              ['Recovery Analyst', 'Operator'],
              ['Finance Partner', 'Viewer'],
            ].map(([name, role]) => (
              <li
                key={name}
                className="flex items-center justify-between rounded-lg border border-ink-100 px-3 py-2.5"
              >
                <span className="font-medium text-ink-800">{name}</span>
                <span className="text-ink-500">{role}</span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="API & Webhooks">
          <label className="block text-xs font-medium text-ink-500">
            Webhook URL
            <input
              value={form.webhookUrl}
              onChange={(e) => update('webhookUrl', e.target.value)}
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 font-mono text-sm"
            />
          </label>
          <p className="mt-3 text-xs text-ink-400">
            Real API credentials and webhook delivery arrive in Phase 10.
          </p>
        </Panel>
      </div>
    </div>
  )
}
