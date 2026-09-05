import type {
  ActionEffectiveness,
  AnalyticsSummary,
  AuditEvent,
  CalibrationBucket,
  CapacityMeter,
  CrossLaneRow,
  EvidenceCard,
  LearningChange,
  LearningSummary,
  MatrixQuadrant,
  OpportunityBucket,
  OutcomeDistribution,
  OverviewKpis,
  PriorityItem,
  PulseEvent,
  RiskGroup,
  LaneBreakdown,
  TrendPoint,
  AppNotification,
  SearchResult,
  SettingsState,
  SimulationScenario,
  AnalyticsPoint,
} from '@/types/domain'
import { cases } from './cases'
import { customers } from './customers'

export const overviewKpis: OverviewKpis = {
  revenueAtRisk: 4790000,
  recovered: 3140000,
  recoveryRate: 65.6,
  expectedRecovery: 820000,
  revenueAtRiskDelta: 4.2,
  recoveredDelta: 8.1,
  recoveryRateDelta: 1.4,
  expectedRecoveryDelta: -2.3,
}

function buildTrend(days: number): TrendPoint[] {
  const points: TrendPoint[] = []
  const now = new Date('2026-09-05T12:00:00')
  for (let i = days - 1; i >= 0; i -= 1) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    const wave = Math.sin(i / 3) * 0.08
    const atRisk = Math.round(4200000 + i * 18000 + wave * 200000)
    const recovered = Math.round(atRisk * (0.58 + (days - i) * 0.0015 + wave * 0.05))
    points.push({
      date: d.toISOString().slice(0, 10),
      atRisk,
      recovered,
    })
  }
  return points
}

export const trends = {
  '7d': buildTrend(7),
  '30d': buildTrend(30),
  '90d': buildTrend(90),
}

export const opportunities: OpportunityBucket[] = [
  { lane: 'receivable', label: 'Receivables', amount: 182000, cases: 8 },
  { lane: 'failed_payment', label: 'Failed Payments', amount: 74000, cases: 7 },
  { lane: 'checkout', label: 'Checkout', amount: 42000, cases: 5 },
  { lane: 'subscription', label: 'Subscriptions', amount: 28000, cases: 4 },
]

export const pulseEvents: PulseEvent[] = [
  {
    id: 'p1',
    timestamp: '11:42:13',
    customerName: 'Priya Nair',
    customerId: 'C1029',
    caseId: 'case_inv_001',
    lane: 'receivable',
    amount: 38000,
    summary: [
      'Podium detected approval-delay pattern.',
      'Compared 4 recovery strategies.',
      'Payment Link had the highest expected net value.',
      'Customer was recently contacted.',
      'Invoice reminder selected.',
    ],
    status: 'Decided',
  },
  {
    id: 'p2',
    timestamp: '11:41:02',
    customerName: 'Priya Nair',
    customerId: 'C1029',
    caseId: 'case_sub_2381',
    lane: 'subscription',
    amount: 2499,
    summary: [
      'Retry failed.',
      'Podium re-planned the recovery strategy.',
      'New action: Payment Link',
      'Expected net value: ₹1,684',
    ],
    status: 'Replanned',
  },
  {
    id: 'p3',
    timestamp: '11:38:44',
    customerName: 'Arjun Mehta',
    customerId: 'C1842',
    caseId: 'case_sub_2381_arjun',
    lane: 'subscription',
    amount: 2499,
    summary: [
      'Insufficient funds detected.',
      'Smart retry window selected for evening.',
    ],
    status: 'Scheduled',
  },
  {
    id: 'p4',
    timestamp: '11:22:09',
    customerName: 'Kavya Shah',
    customerId: 'C2201',
    caseId: 'case_chk_kavya',
    lane: 'checkout',
    amount: 7400,
    summary: [
      'High-intent abandonment scored.',
      'Checkout reminder queued within conversion window.',
    ],
    status: 'Queued',
  },
  {
    id: 'p5',
    timestamp: '10:58:31',
    customerName: 'Vikram Rao',
    customerId: 'C5521',
    caseId: 'case_inv_vikram',
    lane: 'receivable',
    amount: 12400,
    summary: [
      'Policy approved human escalation.',
      'Case moved to escalated queue.',
    ],
    status: 'Escalated',
  },
]

export const riskGroups: RiskGroup[] = [
  {
    id: 'failed',
    title: 'Failed Payments',
    cases: 1248,
    amount: 820000,
    description: 'Card and mandate failures awaiting recovery.',
  },
  {
    id: 'checkout',
    title: 'Checkout Abandonment',
    cases: 832,
    amount: 540000,
    description: 'High-intent sessions that did not complete payment.',
  },
  {
    id: 'subscription',
    title: 'Subscription Recovery',
    cases: 218,
    amount: 210000,
    description: 'Renewals and retries in active recovery.',
  },
  {
    id: 'receivable',
    title: 'Receivables',
    cases: 91,
    amount: 1280000,
    description: 'Overdue invoices across B2B customers.',
  },
]

export const matrixQuadrants: MatrixQuadrant[] = [
  { id: 'act_now', label: 'Act Now', count: 24, amount: 182000 },
  { id: 'automate', label: 'Automate', count: 186, amount: 94000 },
  { id: 'conserve', label: 'Conserve Capacity', count: 61, amount: 42000 },
  { id: 'stop', label: 'Stop Recovery', count: 38, amount: 18000 },
]

export const capacityMeters: CapacityMeter[] = [
  { id: 'contacts', label: 'Customer Contacts', utilized: 88 },
  { id: 'human', label: 'Human Escalation', utilized: 52 },
  { id: 'incentive', label: 'Incentive Budget', utilized: 41 },
]

export const priorityQueue: PriorityItem[] = [
  {
    rank: 1,
    lane: 'receivable',
    amount: 38000,
    expectedNet: 26420,
    caseId: 'case_inv_001',
    customerName: 'Priya Nair',
  },
  {
    rank: 2,
    lane: 'checkout',
    amount: 7400,
    expectedNet: 4180,
    caseId: 'case_chk_9812',
    customerName: 'Priya Nair',
  },
  {
    rank: 3,
    lane: 'subscription',
    amount: 2499,
    expectedNet: 1620,
    caseId: 'case_sub_2381',
    customerName: 'Priya Nair',
  },
]

export const learningSummary: LearningSummary = {
  outcomesObserved: 12842,
  actionsTracked: 18,
  highConfidenceActions: 11,
  calibrationScore: 0.084,
  lastUpdate: '2 minutes ago',
}

export const actionEffectiveness: ActionEffectiveness[] = [
  { action: 'Payment Link', attempts: 128, recoveryRate: 72, avgCost: 2, trend: 'up' },
  { action: 'Invoice Reminder', attempts: 214, recoveryRate: 64, avgCost: 2, trend: 'flat' },
  { action: 'Retry', attempts: 342, recoveryRate: 57, avgCost: 0, trend: 'up' },
  { action: 'Human Follow-up', attempts: 92, recoveryRate: 41, avgCost: 500, trend: 'down' },
  { action: 'Checkout Reminder', attempts: 186, recoveryRate: 58, avgCost: 1, trend: 'up' },
  { action: 'Statement Resend', attempts: 74, recoveryRate: 39, avgCost: 1, trend: 'flat' },
]

export const evidenceCards: EvidenceCard[] = [
  {
    action: 'Payment Link',
    observations: 128,
    recoveries: 92,
    observedRecovery: 72,
    confidence: 'high',
  },
  {
    action: 'Invoice Reminder',
    observations: 214,
    recoveries: 137,
    observedRecovery: 64,
    confidence: 'high',
  },
  {
    action: 'Human Follow-up',
    observations: 92,
    recoveries: 38,
    observedRecovery: 41,
    confidence: 'medium',
  },
]

export const calibrationBuckets: CalibrationBucket[] = [
  { predicted: '40–50%', observed: 47 },
  { predicted: '50–60%', observed: 55 },
  { predicted: '60–70%', observed: 66 },
  { predicted: '70–80%', observed: 74 },
  { predicted: '80–90%', observed: 84 },
]

export const learningChanges: LearningChange[] = [
  { action: 'Payment Link', delta: 6 },
  { action: 'Invoice Reminder', delta: 1 },
  { action: 'Human Follow-up', delta: -8 },
]

export const crossLaneLearning: CrossLaneRow[] = [
  { action: 'Payment Link', subscription: 61, checkout: 54, receivable: 72 },
  { action: 'Reminder', subscription: 55, checkout: 62, receivable: 64 },
  { action: 'Human Follow-up', subscription: 70, checkout: 48, receivable: 81 },
]

export const analyticsSummary: AnalyticsSummary = {
  recoveryRate: 65.6,
  revenueRecovered: 3140000,
  revenueAtRisk: 4790000,
  expectedRecovery: 820000,
  interventionCost: 148000,
  netRecoveryValue: 2992000,
}

export const laneBreakdowns: LaneBreakdown[] = [
  { lane: 'receivable', recovered: 1280000, rate: 71 },
  { lane: 'subscription', recovered: 820000, rate: 63 },
  { lane: 'checkout', recovered: 640000, rate: 58 },
  { lane: 'failed_payment', recovered: 400000, rate: 55 },
]

export const outcomeDistribution: OutcomeDistribution[] = [
  { label: 'Recovered', count: 412 },
  { label: 'Partial', count: 86 },
  { label: 'Waiting', count: 124 },
  { label: 'Failed', count: 58 },
  { label: 'Replanned', count: 73 },
]

export const analyticsTrend: AnalyticsPoint[] = buildTrend(30).map((p) => ({
  date: p.date,
  value: p.recovered,
}))

export const auditEvents: AuditEvent[] = [
  {
    id: 'a1',
    timestamp: '11:42:03',
    event: 'Decision generated',
    type: 'decision',
    customerName: 'Priya Nair',
    customerId: 'C1029',
    caseId: 'case_inv_001',
    actor: 'Podium',
    status: 'Completed',
  },
  {
    id: 'a2',
    timestamp: '11:42:04',
    event: 'Policy evaluated',
    type: 'policy',
    customerName: 'Priya Nair',
    customerId: 'C1029',
    caseId: 'case_inv_001',
    actor: 'Policy',
    status: 'Passed',
  },
  {
    id: 'a3',
    timestamp: '11:42:05',
    event: 'Human follow-up executed',
    type: 'action',
    customerName: 'Priya Nair',
    customerId: 'C1029',
    caseId: 'case_inv_001',
    actor: 'Podium',
    status: 'Completed',
  },
  {
    id: 'a4',
    timestamp: '11:42:11',
    event: 'PTP outcome recorded',
    type: 'outcome',
    customerName: 'Priya Nair',
    customerId: 'C1029',
    caseId: 'case_inv_001',
    actor: 'Learning',
    status: 'Completed',
  },
  {
    id: 'a5',
    timestamp: '11:41:02',
    event: 'Recovery strategy re-planned',
    type: 'coordination',
    customerName: 'Priya Nair',
    customerId: 'C1029',
    caseId: 'case_sub_2381',
    actor: 'Podium',
    status: 'Completed',
  },
  {
    id: 'a6',
    timestamp: '11:41:04',
    event: 'Payment link executed',
    type: 'action',
    customerName: 'Priya Nair',
    customerId: 'C1029',
    caseId: 'case_sub_2381',
    actor: 'Podium',
    status: 'Completed',
  },
  {
    id: 'a7',
    timestamp: '11:22:10',
    event: 'Checkout reminder approved',
    type: 'policy',
    customerName: 'Kavya Shah',
    customerId: 'C2201',
    caseId: 'case_chk_kavya',
    actor: 'Policy',
    status: 'Passed',
  },
  {
    id: 'a8',
    timestamp: '10:58:40',
    event: 'Learning signal recorded',
    type: 'learning',
    customerName: 'Vikram Rao',
    customerId: 'C5521',
    caseId: 'case_inv_vikram',
    actor: 'Learning',
    status: 'Completed',
  },
]

export const notifications: AppNotification[] = [
  {
    id: 'n1',
    title: 'PTP due today',
    body: '₹38,000 — Priya Nair',
    href: '/recovery/case_inv_001',
    read: false,
    createdAt: '8m ago',
  },
  {
    id: 'n2',
    title: 'Recovery capacity 90% utilized',
    body: 'Customer contact budget is nearly exhausted.',
    href: '/revenue-risks',
    read: false,
    createdAt: '22m ago',
  },
  {
    id: 'n3',
    title: '3 cases require human review',
    body: 'Escalation queue needs attention.',
    href: '/recovery?state=escalated',
    read: false,
    createdAt: '1h ago',
  },
  {
    id: 'n4',
    title: 'Learning update completed',
    body: 'Action effectiveness recalibrated.',
    href: '/learning',
    read: true,
    createdAt: '2h ago',
  },
]

export const defaultSettings: SettingsState = {
  maxContacts24h: 1,
  minContactGapHours: 24,
  maxHumanEscalations: 1,
  maxActiveIncentives: 1,
  humanEscalationThreshold: 25000,
  emailNotifications: true,
  slackNotifications: false,
  webhookUrl: 'https://hooks.example.com/podium',
}

export const scenarios: SimulationScenario[] = [
  {
    id: 'priya-multi',
    name: 'Priya Nair — Multi-Revenue Crisis',
    description: 'Subscription, checkout, and receivable risks collide.',
    customerId: 'C1029',
    caseId: 'case_inv_001',
    steps: [
      {
        id: 's0',
        time: '10:00',
        title: 'Revenue risk detected',
        detail: 'Three open exposures totaling ₹47,899.',
        state: 'Detected',
        decision: '—',
        action: '—',
        expectedValue: 0,
        policyStatus: '—',
        outcome: '—',
        learning: '—',
      },
      {
        id: 's1',
        time: '10:01',
        title: 'Context assembled',
        detail: 'Customer segment, contact history, and lane exposures loaded.',
        state: 'Context Ready',
        decision: 'Assemble context',
        action: '—',
        expectedValue: 0,
        policyStatus: '—',
        outcome: '—',
        learning: '—',
      },
      {
        id: 's2',
        time: '10:02',
        title: 'Diagnosis completed',
        detail: 'Approval delay identified on receivable INV-001.',
        state: 'Diagnosed',
        decision: 'Approval delay (82%)',
        action: '—',
        expectedValue: 0,
        policyStatus: '—',
        outcome: '—',
        learning: '—',
      },
      {
        id: 's3',
        time: '10:03',
        title: 'Recovery candidates evaluated',
        detail: 'Payment link, reminder, human follow-up, statement resend.',
        state: 'Candidates Ranked',
        decision: '4 candidates',
        action: '—',
        expectedValue: 29520,
        policyStatus: '—',
        outcome: '—',
        learning: '—',
      },
      {
        id: 's4',
        time: '10:04',
        title: 'Economics evaluated',
        detail: 'Human follow-up maximizes expected net value.',
        state: 'Economics Selected',
        decision: 'Human Follow-up',
        action: 'Human Follow-up',
        expectedValue: 29520,
        policyStatus: 'Pending',
        outcome: '—',
        learning: '—',
      },
      {
        id: 's5',
        time: '10:05',
        title: 'Coordination completed',
        detail: 'Recent-contact collision resolved; lanes sequenced.',
        state: 'Coordinated',
        decision: 'Sequence receivable first',
        action: 'Human Follow-up',
        expectedValue: 29520,
        policyStatus: 'Pending',
        outcome: '—',
        learning: '—',
      },
      {
        id: 's6',
        time: '10:06',
        title: 'Policy approved action',
        detail: 'Contact, cooldown, capacity, and incentive checks passed.',
        state: 'Policy Approved',
        decision: 'Human Follow-up',
        action: 'Human Follow-up',
        expectedValue: 29520,
        policyStatus: 'Approved',
        outcome: '—',
        learning: '—',
      },
      {
        id: 's7',
        time: '10:07',
        title: 'Action executed',
        detail: 'Ops follow-up completed; customer committed to pay.',
        state: 'Action Executed',
        decision: 'Human Follow-up',
        action: 'Human Follow-up',
        expectedValue: 29520,
        policyStatus: 'Approved',
        outcome: 'PTP Created',
        learning: '—',
      },
      {
        id: 's8',
        time: '10:08',
        title: 'Outcome observed',
        detail: 'Promise-to-pay active for ₹38,000 due Sep 10.',
        state: 'PTP Active',
        decision: 'Wait on promise',
        action: 'Wait',
        expectedValue: 25458,
        policyStatus: 'Approved',
        outcome: 'Waiting',
        learning: 'Pending',
      },
      {
        id: 's9',
        time: '10:09',
        title: 'Learning signal recorded',
        detail: 'Interim learning attached; final outcome pending settlement.',
        state: 'Learning Pending',
        decision: 'Human Follow-up',
        action: 'Wait',
        expectedValue: 25458,
        policyStatus: 'Approved',
        outcome: 'Waiting',
        learning: 'Signal recorded',
      },
    ],
  },
  {
    id: 'high-intent',
    name: 'High-Intent Checkout',
    description: 'Abandoned payment with strong conversion window.',
    customerId: 'C2201',
    caseId: 'case_chk_kavya',
    steps: [
      {
        id: 'h0',
        time: '10:00',
        title: 'Revenue risk detected',
        detail: 'Checkout abandoned at payment for ₹7,400.',
        state: 'Detected',
        decision: '—',
        action: '—',
        expectedValue: 0,
        policyStatus: '—',
        outcome: '—',
        learning: '—',
      },
      {
        id: 'h1',
        time: '10:02',
        title: 'Diagnosis completed',
        detail: 'High-intent abandonment scored.',
        state: 'Diagnosed',
        decision: 'High-intent abandon',
        action: '—',
        expectedValue: 0,
        policyStatus: '—',
        outcome: '—',
        learning: '—',
      },
      {
        id: 'h2',
        time: '10:04',
        title: 'Economics evaluated',
        detail: 'Checkout reminder selected.',
        state: 'Economics Selected',
        decision: 'Checkout Reminder',
        action: 'Checkout Reminder',
        expectedValue: 3280,
        policyStatus: 'Pending',
        outcome: '—',
        learning: '—',
      },
      {
        id: 'h3',
        time: '10:06',
        title: 'Policy approved action',
        detail: 'Reminder allowed within contact policy.',
        state: 'Policy Approved',
        decision: 'Checkout Reminder',
        action: 'Checkout Reminder',
        expectedValue: 3280,
        policyStatus: 'Approved',
        outcome: '—',
        learning: '—',
      },
      {
        id: 'h4',
        time: '10:08',
        title: 'Outcome observed',
        detail: 'Customer returned and completed payment.',
        state: 'Recovered',
        decision: 'Checkout Reminder',
        action: 'Checkout Reminder',
        expectedValue: 3280,
        policyStatus: 'Approved',
        outcome: 'Recovered ₹7,400',
        learning: 'Positive signal',
      },
    ],
  },
  {
    id: 'broken-retry',
    name: 'Broken Subscription Retry',
    description: 'Retry fails and strategy is re-planned.',
    customerId: 'C1029',
    caseId: 'case_sub_2381',
    steps: [
      {
        id: 'b0',
        time: '10:00',
        title: 'Revenue risk detected',
        detail: 'Subscription payment failed for ₹2,499.',
        state: 'Detected',
        decision: '—',
        action: '—',
        expectedValue: 0,
        policyStatus: '—',
        outcome: '—',
        learning: '—',
      },
      {
        id: 'b1',
        time: '10:03',
        title: 'Action executed',
        detail: 'Smart retry attempted.',
        state: 'Action Executed',
        decision: 'Retry',
        action: 'Retry',
        expectedValue: 1299,
        policyStatus: 'Approved',
        outcome: 'Failed',
        learning: '—',
      },
      {
        id: 'b2',
        time: '10:05',
        title: 'Recovery strategy re-planned',
        detail: 'Payment link selected after retry failure.',
        state: 'Replanned',
        decision: 'Payment Link',
        action: 'Payment Link',
        expectedValue: 1684,
        policyStatus: 'Approved',
        outcome: 'Waiting',
        learning: 'Retry dampened',
      },
    ],
  },
  {
    id: 'ptp',
    name: 'Receivable — Promise-to-Pay',
    description: 'Human follow-up creates an active PTP.',
    customerId: 'C1029',
    caseId: 'case_inv_001',
    steps: [
      {
        id: 'p0',
        time: '10:00',
        title: 'Revenue risk detected',
        detail: 'INV-001 overdue by 12 days.',
        state: 'Detected',
        decision: '—',
        action: '—',
        expectedValue: 0,
        policyStatus: '—',
        outcome: '—',
        learning: '—',
      },
      {
        id: 'p1',
        time: '10:06',
        title: 'Policy approved action',
        detail: 'Human follow-up approved.',
        state: 'Policy Approved',
        decision: 'Human Follow-up',
        action: 'Human Follow-up',
        expectedValue: 29520,
        policyStatus: 'Approved',
        outcome: '—',
        learning: '—',
      },
      {
        id: 'p2',
        time: '10:08',
        title: 'Outcome observed',
        detail: 'PTP created for Sep 10.',
        state: 'PTP Active',
        decision: 'Wait',
        action: 'Wait',
        expectedValue: 25458,
        policyStatus: 'Approved',
        outcome: 'PTP Active',
        learning: 'Pending',
      },
    ],
  },
  {
    id: 'ptp-broken',
    name: 'PTP Broken — Re-plan',
    description: 'Broken promise triggers a new recovery plan.',
    customerId: 'C1029',
    caseId: 'case_inv_001',
    steps: [
      {
        id: 'x0',
        time: '10:00',
        title: 'Outcome observed',
        detail: 'Promise due date passed without payment.',
        state: 'PTP Broken',
        decision: 'Re-plan',
        action: '—',
        expectedValue: 0,
        policyStatus: '—',
        outcome: 'Broken',
        learning: 'Negative signal',
      },
      {
        id: 'x1',
        time: '10:03',
        title: 'Economics evaluated',
        detail: 'Payment link selected for second-wave recovery.',
        state: 'Replanned',
        decision: 'Payment Link',
        action: 'Payment Link',
        expectedValue: 21800,
        policyStatus: 'Approved',
        outcome: 'Waiting',
        learning: 'PTP dampened',
      },
    ],
  },
  {
    id: 'capacity',
    name: 'Capacity Constrained Recovery',
    description: 'Lower-value actions deferred to preserve capacity.',
    customerId: 'C7780',
    caseId: 'case_chk_sid',
    steps: [
      {
        id: 'c0',
        time: '10:00',
        title: 'Coordination completed',
        detail: 'Contact capacity at 88%.',
        state: 'Capacity Tight',
        decision: 'Defer low EV',
        action: 'Deferred',
        expectedValue: 1100,
        policyStatus: 'Deferred',
        outcome: 'Deferred',
        learning: '—',
      },
      {
        id: 'c1',
        time: '10:02',
        title: 'Policy approved action',
        detail: '₹11,400 capacity preserved across 3 deferred actions.',
        state: 'Deferred',
        decision: 'Conserve capacity',
        action: 'Deferred',
        expectedValue: 0,
        policyStatus: 'Deferred',
        outcome: 'Capacity preserved',
        learning: '—',
      },
    ],
  },
]

export function buildSearchIndex(): SearchResult[] {
  const results: SearchResult[] = []

  for (const c of customers) {
    results.push({
      id: `cust-${c.id}`,
      type: 'customer',
      title: c.name,
      subtitle: c.id,
      href: `/customers/${c.id}`,
      amount: c.revenueAtRisk,
    })
  }

  for (const item of cases) {
    results.push({
      id: `case-${item.id}`,
      type: 'case',
      title: `${item.customerName} · ${item.caseRef}`,
      subtitle: item.lane,
      href: `/recovery/${item.id}`,
      amount: item.amountAtRisk,
    })

    if (item.lane === 'receivable') {
      results.push({
        id: `inv-${item.id}`,
        type: 'invoice',
        title: `Invoice ${item.caseRef}`,
        subtitle: item.customerName,
        href: `/recovery/${item.id}`,
        amount: item.amountAtRisk,
      })
    }
    if (item.lane === 'subscription') {
      results.push({
        id: `sub-${item.id}`,
        type: 'subscription',
        title: `Subscription ${item.caseRef}`,
        subtitle: item.customerName,
        href: `/recovery/${item.id}`,
        amount: item.amountAtRisk,
      })
    }
    if (item.lane === 'checkout') {
      results.push({
        id: `chk-${item.id}`,
        type: 'checkout',
        title: `Checkout ${item.caseRef}`,
        subtitle: item.customerName,
        href: `/recovery/${item.id}`,
        amount: item.amountAtRisk,
      })
    }
  }

  return results
}
