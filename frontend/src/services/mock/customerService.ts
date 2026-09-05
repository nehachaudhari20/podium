import { customers, getCustomerDetail } from '@/mock/customers'
import { delay } from '@/lib/format'
import type { CustomerService } from '../types'

export const mockCustomerService: CustomerService = {
  async listCustomers(search = '') {
    await delay()
    const q = search.trim().toLowerCase()
    if (!q) return customers
    return customers.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q) ||
        c.email.toLowerCase().includes(q),
    )
  },
  async getCustomer(id) {
    await delay()
    return getCustomerDetail(id) ?? null
  },
}
