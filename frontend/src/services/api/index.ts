import { apiFetch } from '../http'
import type {
  AnalyticsService,
  AuditService,
  CustomerService,
  LearningService,
  NotificationService,
  RecoveryService,
  RiskService,
  SearchService,
  SettingsService,
  SimulationService,
} from '../types'
import type {
  AnalyticsPoint,
  AnalyticsSummary,
  AppNotification,
  AuditEvent,
  CalibrationBucket,
  CapacityMeter,
  CrossLaneRow,
  Customer,
  CustomerDetail,
  EvidenceCard,
  LaneBreakdown,
  LearningChange,
  LearningSummary,
  MatrixQuadrant,
  OpportunityBucket,
  OutcomeDistribution,
  OverviewKpis,
  Paginated,
  PriorityItem,
  PulseEvent,
  RecoveryCase,
  RecoveryFilters,
  RiskGroup,
  SearchResult,
  SettingsState,
  SimulationScenario,
  TrendPoint,
  ActionEffectiveness,
} from '@/types/domain'

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === '' || v === 'all') return
    sp.set(k, String(v))
  })
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const apiRecoveryService: RecoveryService = {
  async getOverviewKpis() {
    const data = await apiFetch<{ kpis: OverviewKpis }>('/api/overview')
    return data.kpis
  },
  async getTrend(range) {
    const data = await apiFetch<{ points: TrendPoint[] }>(`/api/overview/trend?range=${range}`)
    return data.points
  },
  async getOpportunities() {
    const data = await apiFetch<{ opportunities: OpportunityBucket[] }>('/api/overview')
    return data.opportunities
  },
  async getPulse() {
    const data = await apiFetch<{ pulse: PulseEvent[] }>('/api/overview')
    return data.pulse
  },
  async listCases(filters: RecoveryFilters = {}) {
    const data = await apiFetch<Paginated<RecoveryCase>>(
      `/api/recovery/cases${qs({
        search: filters.search,
        lane: filters.lane,
        risk: filters.risk,
        state: filters.state,
        page: filters.page,
        page_size: filters.pageSize,
      })}`,
    )
    return data
  },
  async getCase(id) {
    try {
      return await apiFetch<RecoveryCase>(`/api/recovery/cases/${encodeURIComponent(id)}`)
    } catch (err) {
      if (err && typeof err === 'object' && 'status' in err && (err as { status: number }).status === 404) {
        return null
      }
      throw err
    }
  },
  async getActiveCases() {
    const data = await apiFetch<{ activeCases: RecoveryCase[] }>('/api/overview')
    return data.activeCases
  },
  async runCase(id, options) {
    const data = await apiFetch<{ run: unknown; case: RecoveryCase }>(
      `/api/recovery/cases/${encodeURIComponent(id)}/run`,
      {
        method: 'POST',
        body: JSON.stringify({
          reset: options?.reset ?? true,
          intelligence: options?.intelligence ?? 'deterministic',
        }),
      },
    )
    return data
  },
}

export const apiCustomerService: CustomerService = {
  async listCustomers(search = '') {
    const data = await apiFetch<{ items: Customer[] }>(
      `/api/customers${qs({ search })}`,
    )
    return data.items
  },
  async getCustomer(id) {
    try {
      return await apiFetch<CustomerDetail>(`/api/customers/${encodeURIComponent(id)}`)
    } catch (err) {
      if (err && typeof err === 'object' && 'status' in err && (err as { status: number }).status === 404) {
        return null
      }
      throw err
    }
  },
}

export const apiLearningService: LearningService = {
  async getSummary() {
    return apiFetch<LearningSummary>('/api/learning/summary')
  },
  async getEffectiveness() {
    const data = await apiFetch<{ effectiveness: ActionEffectiveness[] }>('/api/learning/actions')
    return data.effectiveness
  },
  async getEvidence() {
    const data = await apiFetch<{ evidence: EvidenceCard[] }>('/api/learning/actions')
    return data.evidence
  },
  async getCalibration() {
    const data = await apiFetch<{ buckets: CalibrationBucket[] }>('/api/learning/calibration')
    return data.buckets
  },
  async getChanges() {
    const data = await apiFetch<{ items: LearningChange[] }>('/api/learning/changes')
    return data.items
  },
  async getCrossLane() {
    const data = await apiFetch<{ rows: CrossLaneRow[] }>('/api/learning/cross-lane')
    return data.rows
  },
}

export const apiAnalyticsService: AnalyticsService = {
  async getSummary(range, lane) {
    const data = await apiFetch<{ summary: AnalyticsSummary }>(
      `/api/analytics${qs({ range, lane })}`,
    )
    return data.summary
  },
  async getTrend(range, lane) {
    const data = await apiFetch<{ trend: AnalyticsPoint[] }>(
      `/api/analytics${qs({ range, lane })}`,
    )
    return data.trend
  },
  async getLaneBreakdown(range) {
    const data = await apiFetch<{ laneBreakdown: LaneBreakdown[] }>(
      `/api/analytics${qs({ range })}`,
    )
    return data.laneBreakdown
  },
  async getOutcomes(range, lane) {
    const data = await apiFetch<{ outcomes: OutcomeDistribution[] }>(
      `/api/analytics${qs({ range, lane })}`,
    )
    return data.outcomes
  },
  async getActionEffectiveness(lane) {
    const data = await apiFetch<{ actionEffectiveness: ActionEffectiveness[] }>(
      `/api/analytics${qs({ lane })}`,
    )
    return data.actionEffectiveness
  },
}

export const apiRiskService: RiskService = {
  async getRiskGroups() {
    const data = await apiFetch<{ groups: RiskGroup[] }>('/api/revenue-risks')
    return data.groups
  },
  async getMatrix() {
    const data = await apiFetch<{ matrix: MatrixQuadrant[] }>('/api/revenue-risks')
    return data.matrix
  },
  async getCapacity() {
    const data = await apiFetch<{ capacity: CapacityMeter[] }>('/api/revenue-risks')
    return data.capacity
  },
  async getPriorityQueue() {
    const data = await apiFetch<{ priorityQueue: PriorityItem[] }>('/api/revenue-risks')
    return data.priorityQueue
  },
}

export const apiSimulationService: SimulationService = {
  async listScenarios() {
    const data = await apiFetch<{ items: SimulationScenario[] }>('/api/scenarios')
    return data.items
  },
  async getScenario(id) {
    const items = await this.listScenarios()
    return items.find((s) => s.id === id) ?? null
  },
  async runScenario(id, options) {
    return apiFetch<{
      scenarioId: string
      runs: unknown[]
      steps: SimulationScenario['steps']
      customer: unknown
    }>(`/api/scenarios/${encodeURIComponent(id)}/run`, {
      method: 'POST',
      body: JSON.stringify({
        reset: options?.reset ?? true,
        intelligence: options?.intelligence ?? 'deterministic',
      }),
    })
  },
}

export const apiAuditService: AuditService = {
  async listEvents(filters = {}) {
    const data = await apiFetch<{ items: AuditEvent[] }>(
      `/api/audit${qs({ search: filters.search, type: filters.type })}`,
    )
    return data.items
  },
}

export const apiNotificationService: NotificationService = {
  async list() {
    const data = await apiFetch<{ items: AppNotification[] }>('/api/notifications')
    return data.items
  },
  async markRead(_id: string) {
    // Notifications are derived from live state — mark-read is UI-local for now.
  },
}

export const apiSearchService: SearchService = {
  async search(query) {
    const data = await apiFetch<{ results: SearchResult[] }>(
      `/api/search${qs({ q: query })}`,
    )
    return data.results
  },
}

export const apiSettingsService: SettingsService = {
  async get() {
    const data = await apiFetch<SettingsState & { readOnly?: boolean }>('/api/config')
    return data
  },
  async save(next) {
    // Config is read-only from YAML in Phase 10.
    return next
  },
}
