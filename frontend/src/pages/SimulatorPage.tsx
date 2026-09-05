import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Pause, Play, RotateCcw, StepForward } from 'lucide-react'
import {
  Button,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
} from '@/components/common/Page'
import { useToast } from '@/components/common/Toast'
import { useAsyncData } from '@/hooks/useAsyncData'
import { formatINR, cn } from '@/lib/format'
import { isApiMode, services } from '@/services'
import type { SimulationScenario } from '@/types/domain'

export function SimulatorPage() {
  const { data: scenarios, loading, error, reload } = useAsyncData(
    () => services.simulation.listScenarios(),
    [],
  )
  const { toast } = useToast()
  const [scenarioId, setScenarioId] = useState('')
  const [stepIndex, setStepIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [running, setRunning] = useState(false)
  const [liveSteps, setLiveSteps] = useState<SimulationScenario['steps'] | null>(null)

  useEffect(() => {
    if (scenarios?.length && !scenarioId) {
      setScenarioId(scenarios[0].id)
    }
  }, [scenarios, scenarioId])

  const scenario = useMemo(
    () => scenarios?.find((s) => s.id === scenarioId) ?? scenarios?.[0],
    [scenarios, scenarioId],
  )

  const steps = liveSteps ?? scenario?.steps ?? []

  useEffect(() => {
    setStepIndex(0)
    setPlaying(false)
    setLiveSteps(null)
  }, [scenarioId])

  useEffect(() => {
    if (!playing || steps.length === 0) return
    if (stepIndex >= steps.length - 1) {
      setPlaying(false)
      return
    }
    const timer = window.setTimeout(() => {
      setStepIndex((i) => Math.min(i + 1, steps.length - 1))
    }, 1200)
    return () => window.clearTimeout(timer)
  }, [playing, stepIndex, steps])

  const runOnBackend = async () => {
    if (!scenario || !services.simulation.runScenario) {
      toast('Backend scenario run unavailable in mock mode', 'error')
      return
    }
    setRunning(true)
    try {
      const result = await services.simulation.runScenario(scenario.id, {
        reset: true,
        intelligence: 'deterministic',
      })
      setLiveSteps(result.steps)
      setStepIndex(Math.min(6, result.steps.length - 1))
      toast('Scenario executed on backend', 'success')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Scenario run failed', 'error')
    } finally {
      setRunning(false)
    }
  }

  if (error) return <ErrorState onRetry={reload} />
  if (loading || !scenarios || !scenario) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20" />
        <Skeleton className="h-96" />
      </div>
    )
  }

  const current = steps[stepIndex] ?? steps[0]

  return (
    <div>
      <PageHeader
        title="Podium Simulator"
        subtitle="Run recovery scenarios and watch Podium adapt."
      />

      <Panel className="mb-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <label className="block flex-1 text-xs font-medium text-ink-500">
            Scenario
            <select
              value={scenario.id}
              onChange={(e) => setScenarioId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <div className="flex flex-wrap gap-2">
            {isApiMode() && services.simulation.runScenario && (
              <Button onClick={runOnBackend} disabled={running}>
                {running ? 'Executing…' : 'Run on Backend'}
              </Button>
            )}
            <Button
              onClick={() => {
                setPlaying(true)
                toast('Scenario playback started', 'success')
              }}
              disabled={playing || stepIndex >= steps.length - 1}
            >
              <Play className="h-4 w-4" /> Play
            </Button>
            <Button variant="secondary" onClick={() => setPlaying(false)} disabled={!playing}>
              <Pause className="h-4 w-4" /> Pause
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setPlaying(false)
                setStepIndex((i) => Math.min(i + 1, steps.length - 1))
              }}
              disabled={stepIndex >= steps.length - 1}
            >
              <StepForward className="h-4 w-4" /> Step
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setPlaying(false)
                setStepIndex(0)
              }}
            >
              <RotateCcw className="h-4 w-4" /> Reset
            </Button>
          </div>
        </div>
        <p className="mt-3 text-sm text-ink-500">{scenario.description}</p>
        <div className="mt-2 text-xs text-ink-400">
          <Link to={`/customers/${scenario.customerId}`} className="text-podium-700 hover:underline">
            Open customer
          </Link>
          {' · '}
          <Link to={`/recovery/${scenario.caseId}`} className="text-podium-700 hover:underline">
            Open case
          </Link>
          {isApiMode() && (
            <span className="ml-2 rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-emerald-700">
              Live backend
            </span>
          )}
        </div>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-5">
        <Panel className="xl:col-span-3" title="Simulation Timeline">
          <ol className="space-y-2">
            {steps.map((step, idx) => (
              <li
                key={step.id}
                className={cn(
                  'rounded-lg border px-3 py-2.5 transition',
                  idx === stepIndex
                    ? 'border-podium-300 bg-podium-50'
                    : idx < stepIndex
                      ? 'border-ink-100 bg-white'
                      : 'border-ink-100 bg-ink-50/40 opacity-60',
                )}
              >
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-ink-400">{step.time}</span>
                  <span className="text-sm font-semibold text-ink-900">{step.title}</span>
                </div>
                <p className="mt-1 text-xs text-ink-500">{step.detail}</p>
              </li>
            ))}
          </ol>
        </Panel>

        <Panel className="xl:col-span-2" title="Simulation Output">
          {current ? (
            <dl className="space-y-3 text-sm">
              {[
                ['Current state', current.state],
                ['Current decision', current.decision],
                ['Action', current.action],
                ['Expected value', formatINR(current.expectedValue)],
                ['Policy status', current.policyStatus],
                ['Outcome', current.outcome],
                ['Learning signal', current.learning],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-lg border border-ink-100 bg-ink-50/50 px-3 py-2"
                >
                  <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                    {label}
                  </dt>
                  <dd className="mt-1 font-medium text-ink-900">{value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm text-ink-500">No steps available.</p>
          )}
        </Panel>
      </div>
    </div>
  )
}
