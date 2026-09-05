import type {
  Customer,
  CustomerDetail,
  LaneExposure,
  TimelineEvent,
} from '@/types/domain'

export const HERO_CUSTOMER_ID = 'C1029'
export const HERO_CUSTOMER_NAME = 'Priya Nair'

export const customers: Customer[] = [
  {
    id: 'C1029',
    name: 'Priya Nair',
    email: 'priya.nair@novatech.io',
    segment: 'B2B',
    revenueAtRisk: 47899,
    activeCases: 3,
    lastActivity: '2m ago',
    recoveryStatus: 'Coordinated',
    totalExposure: 47899,
  },
  {
    id: 'C1842',
    name: 'Arjun Mehta',
    email: 'arjun@brightcart.in',
    segment: 'SMB',
    revenueAtRisk: 2499,
    activeCases: 1,
    lastActivity: '14m ago',
    recoveryStatus: 'Retry Scheduled',
    totalExposure: 2499,
  },
  {
    id: 'C2201',
    name: 'Kavya Shah',
    email: 'kavya@pixelworks.co',
    segment: 'Growth',
    revenueAtRisk: 7400,
    activeCases: 1,
    lastActivity: '32m ago',
    recoveryStatus: 'Abandoned',
    totalExposure: 7400,
  },
  {
    id: 'C3104',
    name: 'Rohan Desai',
    email: 'rohan@orbitpay.com',
    segment: 'Enterprise',
    revenueAtRisk: 56000,
    activeCases: 2,
    lastActivity: '1h ago',
    recoveryStatus: 'Needs Action',
    totalExposure: 56000,
  },
  {
    id: 'C4410',
    name: 'Ananya Iyer',
    email: 'ananya@cloudnest.in',
    segment: 'SMB',
    revenueAtRisk: 1890,
    activeCases: 1,
    lastActivity: '3h ago',
    recoveryStatus: 'Waiting',
    totalExposure: 1890,
  },
  {
    id: 'C5521',
    name: 'Vikram Rao',
    email: 'vikram@ledgerly.io',
    segment: 'B2B',
    revenueAtRisk: 12400,
    activeCases: 1,
    lastActivity: '5h ago',
    recoveryStatus: 'Escalated',
    totalExposure: 12400,
  },
  {
    id: 'C6612',
    name: 'Meera Kapoor',
    email: 'meera@flowstack.app',
    segment: 'Growth',
    revenueAtRisk: 0,
    activeCases: 0,
    lastActivity: '1d ago',
    recoveryStatus: 'Recovered',
    totalExposure: 9200,
  },
  {
    id: 'C7780',
    name: 'Siddharth Jain',
    email: 'sid@mintroute.com',
    segment: 'SMB',
    revenueAtRisk: 3200,
    activeCases: 1,
    lastActivity: '2d ago',
    recoveryStatus: 'Deferred',
    totalExposure: 3200,
  },
]

const priyaLanes: LaneExposure[] = [
  {
    lane: 'subscription',
    amount: 2499,
    status: 'Payment Failed',
    caseId: 'case_sub_2381',
  },
  {
    lane: 'checkout',
    amount: 7400,
    status: 'High-intent Abandonment',
    caseId: 'case_chk_9812',
  },
  {
    lane: 'receivable',
    amount: 38000,
    status: '12d Overdue',
    caseId: 'case_inv_001',
  },
]

const priyaTimeline: TimelineEvent[] = [
  {
    id: 't1',
    date: 'Sep 3',
    title: 'Subscription payment failed',
    description: 'Card decline on monthly plan renewal.',
    lane: 'subscription',
    amount: 2499,
    status: 'Failed',
    type: 'risk',
  },
  {
    id: 't2',
    date: 'Sep 4',
    title: 'High-intent checkout abandoned',
    description: 'Customer reached payment step then exited.',
    lane: 'checkout',
    amount: 7400,
    status: 'Abandoned',
    type: 'risk',
  },
  {
    id: 't3',
    date: 'Sep 4',
    title: 'Podium evaluated recovery options',
    description: 'Compared payment link, reminder, and human follow-up.',
    type: 'decision',
    status: 'Completed',
  },
  {
    id: 't4',
    date: 'Sep 5',
    title: 'Recent-contact collision detected',
    description: 'Customer was contacted in the last 24 hours.',
    type: 'coordination',
    status: 'Blocked',
  },
  {
    id: 't5',
    date: 'Sep 5',
    title: 'Receivable recovery deferred',
    description: 'Deferred invoice reminder to respect contact window.',
    lane: 'receivable',
    amount: 38000,
    type: 'decision',
    status: 'Deferred',
  },
  {
    id: 't6',
    date: 'Sep 6',
    title: 'Customer requested payment commitment',
    description: 'Ops call confirmed intent to clear INV-001.',
    lane: 'receivable',
    type: 'promise',
    status: 'Active',
  },
  {
    id: 't7',
    date: 'Sep 6',
    title: 'PTP created',
    description: 'Promise-to-pay recorded for ₹38,000.',
    lane: 'receivable',
    amount: 38000,
    type: 'promise',
    status: 'PTP Active',
  },
  {
    id: 't8',
    date: 'Sep 10',
    title: 'Promise due',
    description: 'Awaiting settlement against outstanding receivable.',
    lane: 'receivable',
    amount: 38000,
    type: 'outcome',
    status: 'Waiting',
  },
]

export const customerDetails: Record<string, CustomerDetail> = {
  C1029: {
    ...customers[0],
    lanes: priyaLanes,
    timeline: priyaTimeline,
    recovered: 0,
    recoveryState: 'Coordinated',
  },
  C1842: {
    ...customers[1],
    lanes: [
      {
        lane: 'subscription',
        amount: 2499,
        status: 'Retry Scheduled',
        caseId: 'case_sub_2381_arjun',
      },
    ],
    timeline: [
      {
        id: 'a1',
        date: 'Sep 5',
        title: 'Subscription payment failed',
        description: 'Insufficient funds on primary card.',
        lane: 'subscription',
        amount: 2499,
        type: 'risk',
        status: 'Failed',
      },
      {
        id: 'a2',
        date: 'Sep 5',
        title: 'Retry scheduled',
        description: 'Next smart retry queued for evening window.',
        lane: 'subscription',
        type: 'action',
        status: 'Scheduled',
      },
    ],
    recovered: 0,
    recoveryState: 'Retry Scheduled',
  },
  C2201: {
    ...customers[2],
    lanes: [
      {
        lane: 'checkout',
        amount: 7400,
        status: 'Abandoned',
        caseId: 'case_chk_9812',
      },
    ],
    timeline: [
      {
        id: 'k1',
        date: 'Sep 5',
        title: 'Checkout abandoned at payment',
        description: 'High-intent session with cart value ₹7,400.',
        lane: 'checkout',
        amount: 7400,
        type: 'risk',
        status: 'Abandoned',
      },
    ],
    recovered: 0,
    recoveryState: 'Abandoned',
  },
}

export function getCustomerDetail(id: string): CustomerDetail | undefined {
  if (customerDetails[id]) return customerDetails[id]
  const base = customers.find((c) => c.id === id)
  if (!base) return undefined
  return {
    ...base,
    lanes: [],
    timeline: [],
    recovered: base.revenueAtRisk === 0 ? base.totalExposure : 0,
    recoveryState: base.recoveryStatus,
  }
}
