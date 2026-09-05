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

/**
 * Service locator — swap mock* implementations for API adapters in Phase 10.
 */
export const services = {
  recovery: mockRecoveryService,
  customers: mockCustomerService,
  learning: mockLearningService,
  analytics: mockAnalyticsService,
  risks: mockRiskService,
  simulation: mockSimulationService,
  audit: mockAuditService,
  notifications: mockNotificationService,
  search: mockSearchService,
  settings: mockSettingsService,
}

export type Services = typeof services
