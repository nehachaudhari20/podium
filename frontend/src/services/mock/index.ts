import {
  actionEffectiveness,
  analyticsSummary,
  analyticsTrend,
  auditEvents,
  buildSearchIndex,
  calibrationBuckets,
  capacityMeters,
  crossLaneLearning,
  defaultSettings,
  evidenceCards,
  laneBreakdowns,
  learningChanges,
  learningSummary,
  matrixQuadrants,
  notifications,
  outcomeDistribution,
  priorityQueue,
  riskGroups,
  scenarios,
} from '@/mock/data'
import { delay } from '@/lib/format'
import type {
  AnalyticsService,
  AuditService,
  LearningService,
  NotificationService,
  RiskService,
  SearchService,
  SettingsService,
  SimulationService,
} from '../types'
import type { SettingsState } from '@/types/domain'

let settingsState: SettingsState = { ...defaultSettings }
let notificationState = [...notifications]

export const mockLearningService: LearningService = {
  async getSummary() {
    await delay()
    return learningSummary
  },
  async getEffectiveness() {
    await delay()
    return actionEffectiveness
  },
  async getEvidence() {
    await delay()
    return evidenceCards
  },
  async getCalibration() {
    await delay()
    return calibrationBuckets
  },
  async getChanges() {
    await delay()
    return learningChanges
  },
  async getCrossLane() {
    await delay()
    return crossLaneLearning
  },
}

export const mockAnalyticsService: AnalyticsService = {
  async getSummary() {
    await delay()
    return analyticsSummary
  },
  async getTrend() {
    await delay()
    return analyticsTrend
  },
  async getLaneBreakdown() {
    await delay()
    return laneBreakdowns
  },
  async getOutcomes() {
    await delay()
    return outcomeDistribution
  },
  async getActionEffectiveness() {
    await delay()
    return actionEffectiveness
  },
}

export const mockRiskService: RiskService = {
  async getRiskGroups() {
    await delay()
    return riskGroups
  },
  async getMatrix() {
    await delay()
    return matrixQuadrants
  },
  async getCapacity() {
    await delay()
    return capacityMeters
  },
  async getPriorityQueue() {
    await delay()
    return priorityQueue
  },
}

export const mockSimulationService: SimulationService = {
  async listScenarios() {
    await delay()
    return scenarios
  },
  async getScenario(id) {
    await delay()
    return scenarios.find((s) => s.id === id) ?? null
  },
}

export const mockAuditService: AuditService = {
  async listEvents(filters = {}) {
    await delay()
    const { search = '', type = 'all' } = filters
    let items = [...auditEvents]
    if (type !== 'all') items = items.filter((e) => e.type === type)
    if (search.trim()) {
      const q = search.toLowerCase()
      items = items.filter(
        (e) =>
          e.event.toLowerCase().includes(q) ||
          e.customerName.toLowerCase().includes(q) ||
          e.caseId.toLowerCase().includes(q),
      )
    }
    return items
  },
}

export const mockNotificationService: NotificationService = {
  async list() {
    await delay(120)
    return notificationState
  },
  async markRead(id) {
    await delay(80)
    notificationState = notificationState.map((n) =>
      n.id === id ? { ...n, read: true } : n,
    )
  },
}

export const mockSearchService: SearchService = {
  async search(query) {
    await delay(120)
    const q = query.trim().toLowerCase()
    if (!q) return []
    return buildSearchIndex()
      .filter(
        (r) =>
          r.title.toLowerCase().includes(q) ||
          r.subtitle.toLowerCase().includes(q) ||
          r.type.includes(q),
      )
      .slice(0, 12)
  },
}

export const mockSettingsService: SettingsService = {
  async get() {
    await delay()
    return { ...settingsState }
  },
  async save(next) {
    await delay(200)
    settingsState = { ...next }
    return { ...settingsState }
  },
}
