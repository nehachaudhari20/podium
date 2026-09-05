import { cases } from '@/mock/cases'
import {
  opportunities,
  overviewKpis,
  pulseEvents,
  trends,
} from '@/mock/data'
import type {
  Paginated,
  RecoveryCase,
  RecoveryFilters,
  CaseState,
} from '@/types/domain'
import { delay } from '@/lib/format'
import type { RecoveryService } from '../types'

const riskOrder = { high: 3, medium: 2, low: 1 }

function matchesState(state: CaseState, filter: string): boolean {
  if (filter === 'all') return true
  if (filter === 'needs_action') {
    return state === 'needs_action' || state === 'abandoned'
  }
  if (filter === 'waiting') {
    return state === 'waiting' || state === 'ptp_active' || state === 'retry_scheduled'
  }
  return state === filter
}

export const mockRecoveryService: RecoveryService = {
  async getOverviewKpis() {
    await delay()
    return overviewKpis
  },
  async getTrend(range) {
    await delay()
    return trends[range]
  },
  async getOpportunities() {
    await delay()
    return opportunities
  },
  async getPulse() {
    await delay()
    return pulseEvents
  },
  async listCases(filters: RecoveryFilters = {}) {
    await delay()
    const {
      search = '',
      lane = 'all',
      risk = 'all',
      state = 'all',
      sortBy = 'updated',
      sortDir = 'desc',
      page = 1,
      pageSize = 8,
    } = filters

    let items = [...cases]

    if (lane !== 'all') {
      items = items.filter((c) => c.lane === lane)
    }
    if (risk !== 'all') {
      items = items.filter((c) => c.risk === risk)
    }
    if (state !== 'all') {
      items = items.filter((c) => matchesState(c.state, state))
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      items = items.filter(
        (c) =>
          c.customerName.toLowerCase().includes(q) ||
          c.caseRef.toLowerCase().includes(q) ||
          c.id.toLowerCase().includes(q),
      )
    }

    items.sort((a, b) => {
      let cmp = 0
      if (sortBy === 'amount') cmp = a.amountAtRisk - b.amountAtRisk
      else if (sortBy === 'risk') cmp = riskOrder[a.risk] - riskOrder[b.risk]
      else if (sortBy === 'expected') cmp = a.expectedValue - b.expectedValue
      else cmp = cases.indexOf(a) - cases.indexOf(b)

      // Seeded list is already newest-first; preserve that for updated:desc.
      if (sortBy === 'updated') {
        return sortDir === 'desc' ? cmp : -cmp
      }
      return sortDir === 'asc' ? cmp : -cmp
    })

    const total = items.length
    const start = (page - 1) * pageSize
    const pageItems = items.slice(start, start + pageSize)

    return {
      items: pageItems,
      total,
      page,
      pageSize,
    } satisfies Paginated<RecoveryCase>
  },
  async getCase(id) {
    await delay()
    return cases.find((c) => c.id === id) ?? null
  },
  async getActiveCases() {
    await delay()
    return cases.filter((c) => c.state !== 'recovered').slice(0, 8)
  },
}
