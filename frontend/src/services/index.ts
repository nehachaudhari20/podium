import { isApiMode } from './http'
import {
  apiAnalyticsService,
  apiAuditService,
  apiCustomerService,
  apiLearningService,
  apiNotificationService,
  apiRecoveryService,
  apiRiskService,
  apiSearchService,
  apiSettingsService,
  apiSimulationService,
} from './api'
import { mockRecoveryService } from './mock/recoveryService'
import { mockCustomerService } from './mock/customerService'
import {
  mockAnalyticsService,
  mockAuditService,
  mockLearningService,
  mockNotificationService,
  mockRiskService,
  mockSearchService,
  mockSettingsService,
  mockSimulationService,
} from './mock'

const useApi = isApiMode()

/**
 * Service locator — VITE_DATA_MODE=api|mock
 * Default: api (Phase 10). Mock remains for frontend-only work.
 */
export const services = {
  recovery: useApi ? apiRecoveryService : mockRecoveryService,
  customers: useApi ? apiCustomerService : mockCustomerService,
  learning: useApi ? apiLearningService : mockLearningService,
  analytics: useApi ? apiAnalyticsService : mockAnalyticsService,
  risks: useApi ? apiRiskService : mockRiskService,
  simulation: useApi ? apiSimulationService : mockSimulationService,
  audit: useApi ? apiAuditService : mockAuditService,
  notifications: useApi ? apiNotificationService : mockNotificationService,
  search: useApi ? apiSearchService : mockSearchService,
  settings: useApi ? apiSettingsService : mockSettingsService,
}

export type Services = typeof services
export { isApiMode, apiBaseUrl } from './http'
