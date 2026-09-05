import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '@/App'
import { ToastProvider } from '@/components/common/Toast'

function renderApp(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <App />
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('Podium frontend', () => {
  it('renders overview command center', async () => {
    renderApp('/')
    expect(screen.getByRole('heading', { name: 'Revenue Recovery' })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('Revenue at Risk')).toBeInTheDocument()
    })
  })

  it('navigates to recovery and filters by lane', async () => {
    const user = userEvent.setup()
    renderApp('/recovery')
    expect(screen.getByRole('heading', { name: 'Recovery' })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getAllByText('Priya Nair').length).toBeGreaterThan(0)
    })
    await user.selectOptions(screen.getByLabelText('Lane'), 'receivable')
    await waitFor(() => {
      expect(screen.getByText('INV-001')).toBeInTheDocument()
    })
  })

  it('opens customer 360 for Priya Nair', async () => {
    renderApp('/customers/C1029')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Priya Nair' })).toBeInTheDocument()
      expect(screen.getByText(/total revenue exposure/i)).toBeInTheDocument()
    })
  })

  it('opens case detail and Why Action drawer', async () => {
    const user = userEvent.setup()
    renderApp('/recovery/case_inv_001')
    await waitFor(() => {
      expect(screen.getByText('INV-001')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: 'Why this action?' }))
    expect(screen.getByText(/Why Podium chose Human Follow-up/i)).toBeInTheDocument()
  })

  it('advances simulator with step control', async () => {
    const user = userEvent.setup()
    renderApp('/simulator')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Podium Simulator' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /Step/i }))
    await waitFor(() => {
      expect(screen.getByText('Context Ready')).toBeInTheDocument()
    })
  })

  it('shows empty state for unmatched recovery search', async () => {
    const user = userEvent.setup()
    renderApp('/recovery')
    await waitFor(() => {
      expect(screen.getByLabelText('Search')).toBeInTheDocument()
    })
    await user.type(screen.getByLabelText('Search'), 'zzzz-no-match')
    await waitFor(() => {
      expect(screen.getByText('No matching cases')).toBeInTheDocument()
    })
  })
})
