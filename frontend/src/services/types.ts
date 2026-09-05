import type {
  AnalyticsSummary,
  AppNotification,
  AuditEvent,
  AuditEventType,
  CapacityMeter,
  Customer,
  CustomerDetail,
  Lane,
  LaneBreakdown,
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
  EvidenceCard,
  CalibrationBucket,
  LearningChange,
  CrossLaneRow,
  AnalyticsPoint,
} from '@/types/domain'

export interface RecoveryService {
  getOverviewKpis(): Promise<OverviewKpis>
  getTrend(range: '7d' | '30d' | '90d'): Promise<TrendPoint[]>
  getOpportunities(): Promise<OpportunityBucket[]>
  getPulse(): Promise<PulseEvent[]>
  listCases(filters?: RecoveryFilters): Promise<Paginated<RecoveryCase>>
  getCase(id: string): Promise<RecoveryCase | null>
  getActiveCases(): Promise<RecoveryCase[]>
}

export interface CustomerService {
  listCustomers(search?: string): Promise<Customer[]>
  getCustomer(id: string): Promise<CustomerDetail | null>
}

export interface LearningService {
  getSummary(): Promise<LearningSummary>
  getEffectiveness(): Promise<ActionEffectiveness[]>
  getEvidence(): Promise<EvidenceCard[]>
  getCalibration(): Promise<CalibrationBucket[]>
  getChanges(): Promise<LearningChange[]>
  getCrossLane(): Promise<CrossLaneRow[]>
}

export interface AnalyticsService {
  getSummary(range: '7d' | '30d' | '90d', lane: Lane | 'all'): Promise<AnalyticsSummary>
  getTrend(range: '7d' | '30d' | '90d', lane: Lane | 'all'): Promise<AnalyticsPoint[]>
  getLaneBreakdown(range: '7d' | '30d' | '90d'): Promise<LaneBreakdown[]>
  getOutcomes(range: '7d' | '30d' | '90d', lane: Lane | 'all'): Promise<OutcomeDistribution[]>
  getActionEffectiveness(lane: Lane | 'all'): Promise<ActionEffectiveness[]>
}

export interface RiskService {
  getRiskGroups(): Promise<RiskGroup[]>
  getMatrix(): Promise<MatrixQuadrant[]>
  getCapacity(): Promise<CapacityMeter[]>
  getPriorityQueue(): Promise<PriorityItem[]>
}

export interface SimulationService {
  listScenarios(): Promise<SimulationScenario[]>
  getScenario(id: string): Promise<SimulationScenario | null>
}

export interface AuditService {
  listEvents(filters?: {
    search?: string
    type?: AuditEventType | 'all'
  }): Promise<AuditEvent[]>
}

export interface NotificationService {
  list(): Promise<AppNotification[]>
  markRead(id: string): Promise<void>
}

export interface SearchService {
  search(query: string): Promise<SearchResult[]>
}

export interface SettingsService {
  get(): Promise<SettingsState>
  save(next: SettingsState): Promise<SettingsState>
}
