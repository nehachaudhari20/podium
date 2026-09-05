export type Lane = 'subscription' | 'checkout' | 'receivable' | 'failed_payment'

export type RiskLevel = 'high' | 'medium' | 'low'

export type CaseState =
  | 'needs_action'
  | 'waiting'
  | 'ptp_active'
  | 'retry_scheduled'
  | 'abandoned'
  | 'recovered'
  | 'escalated'
  | 'deferred'
  | 'coordinated'

export type PipelineStage =
  | 'detected'
  | 'context'
  | 'diagnosis'
  | 'candidates'
  | 'economics'
  | 'coordination'
  | 'policy'
  | 'action'
  | 'outcome'
  | 'learning'

export type StageStatus = 'completed' | 'active' | 'pending' | 'blocked'

export type OutcomeStatus = 'completed' | 'waiting' | 'partial' | 'failed' | 'replanned'

export type AuditEventType =
  | 'decision'
  | 'policy'
  | 'action'
  | 'outcome'
  | 'learning'
  | 'coordination'

export interface Customer {
  id: string
  name: string
  email: string
  segment: string
  revenueAtRisk: number
  activeCases: number
  lastActivity: string
  recoveryStatus: string
  totalExposure: number
}

export interface LaneExposure {
  lane: Lane
  amount: number
  status: string
  caseId?: string
}

export interface TimelineEvent {
  id: string
  date: string
  title: string
  description: string
  lane?: Lane
  amount?: number
  status?: string
  type: 'risk' | 'decision' | 'action' | 'outcome' | 'promise' | 'coordination'
}

export interface CustomerDetail extends Customer {
  lanes: LaneExposure[]
  timeline: TimelineEvent[]
  recovered: number
  recoveryState: string
}

export interface CandidateAction {
  id: string
  action: string
  probability: number
  cost: number
  expectedNet: number
  selected?: boolean
}

export interface PolicyCheckItem {
  label: string
  passed: boolean
}

export interface RecoveryDecision {
  likelyCause: string
  confidence: number
  reasoning: string
  selectedAction: string
  whySummary: string[]
  candidates: CandidateAction[]
  policyChecks: PolicyCheckItem[]
  policyStatus: 'approved' | 'blocked' | 'deferred'
  whyDrawer: {
    title: string
    sections: { heading: string; bullets: string[] }[]
    decision: string
  }
}

export interface RecoveryOutcome {
  action: string
  status: OutcomeStatus
  outcome: string
  recovered: number
}

export interface LearningEvidence {
  action: string
  observations: number
  observedSuccess: number
  prediction: number
  confidence: 'high' | 'medium' | 'low'
  outcome: string
}

export interface PipelineStep {
  stage: PipelineStage
  label: string
  status: StageStatus
  summary: string
}

export interface RecoveryCase {
  id: string
  caseRef: string
  customerId: string
  customerName: string
  lane: Lane
  amountAtRisk: number
  risk: RiskLevel
  state: CaseState
  nextAction: string
  expectedValue: number
  updatedAt: string
  daysOverdue?: number
  priority?: 'high' | 'medium' | 'low'
  remaining?: number
  expectedRecovery?: number
  context?: Record<string, string>
  decision?: RecoveryDecision
  pipeline?: PipelineStep[]
  outcome?: RecoveryOutcome
  learning?: LearningEvidence
}

export interface OverviewKpis {
  revenueAtRisk: number
  recovered: number
  recoveryRate: number
  expectedRecovery: number
  revenueAtRiskDelta: number
  recoveredDelta: number
  recoveryRateDelta: number
  expectedRecoveryDelta: number
}

export interface TrendPoint {
  date: string
  atRisk: number
  recovered: number
}

export interface OpportunityBucket {
  lane: Lane
  label: string
  amount: number
  cases: number
}

export interface PulseEvent {
  id: string
  timestamp: string
  customerName: string
  customerId: string
  caseId: string
  lane: Lane
  amount: number
  summary: string[]
  status: string
}

export interface RiskGroup {
  id: string
  title: string
  cases: number
  amount: number
  description: string
}

export interface MatrixQuadrant {
  id: 'act_now' | 'automate' | 'conserve' | 'stop'
  label: string
  count: number
  amount: number
}

export interface CapacityMeter {
  id: string
  label: string
  utilized: number
}

export interface PriorityItem {
  rank: number
  lane: Lane
  amount: number
  expectedNet: number
  caseId: string
  customerName: string
}

export interface LearningSummary {
  outcomesObserved: number
  actionsTracked: number
  highConfidenceActions: number
  calibrationScore: number
  lastUpdate: string
}

export interface ActionEffectiveness {
  action: string
  attempts: number
  recoveryRate: number
  avgCost: number
  trend: 'up' | 'flat' | 'down'
}

export interface EvidenceCard {
  action: string
  observations: number
  recoveries: number
  observedRecovery: number
  confidence: 'high' | 'medium' | 'low'
}

export interface CalibrationBucket {
  predicted: string
  observed: number
}

export interface LearningChange {
  action: string
  delta: number
}

export interface CrossLaneRow {
  action: string
  subscription: number
  checkout: number
  receivable: number
}

export interface AnalyticsSummary {
  recoveryRate: number
  revenueRecovered: number
  revenueAtRisk: number
  expectedRecovery: number
  interventionCost: number
  netRecoveryValue: number
}

export interface AnalyticsPoint {
  date: string
  value: number
  lane?: Lane
}

export interface LaneBreakdown {
  lane: Lane
  recovered: number
  rate: number
}

export interface OutcomeDistribution {
  label: string
  count: number
}

export interface SimulationStep {
  id: string
  time: string
  title: string
  detail: string
  state: string
  decision: string
  action: string
  expectedValue: number
  policyStatus: string
  outcome: string
  learning: string
}

export interface SimulationScenario {
  id: string
  name: string
  description: string
  customerId: string
  caseId: string
  steps: SimulationStep[]
}

export interface AuditEvent {
  id: string
  timestamp: string
  event: string
  type: AuditEventType
  customerName: string
  customerId: string
  caseId: string
  actor: string
  status: string
}

export interface AppNotification {
  id: string
  title: string
  body: string
  href: string
  read: boolean
  createdAt: string
}

export interface SearchResult {
  id: string
  type: 'customer' | 'case' | 'invoice' | 'subscription' | 'checkout'
  title: string
  subtitle: string
  href: string
  amount?: number
}

export interface SettingsState {
  maxContacts24h: number
  minContactGapHours: number
  maxHumanEscalations: number
  maxActiveIncentives: number
  humanEscalationThreshold: number
  emailNotifications: boolean
  slackNotifications: boolean
  webhookUrl: string
}

export interface RecoveryFilters {
  search?: string
  lane?: Lane | 'all'
  risk?: RiskLevel | 'all'
  state?: CaseState | 'all' | 'needs_action' | 'waiting' | 'recovered' | 'escalated' | 'deferred'
  sortBy?: 'updated' | 'amount' | 'risk' | 'expected'
  sortDir?: 'asc' | 'desc'
  page?: number
  pageSize?: number
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}
