import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { OverviewPage } from '@/pages/OverviewPage'
import { RecoveryPage } from '@/pages/RecoveryPage'
import { CustomersPage, CustomerDetailPage } from '@/pages/CustomersPage'
import { CaseDetailPage } from '@/pages/CaseDetailPage'
import { RevenueRisksPage } from '@/pages/RevenueRisksPage'
import { LearningPage } from '@/pages/LearningPage'
import { AnalyticsPage } from '@/pages/AnalyticsPage'
import { SimulatorPage } from '@/pages/SimulatorPage'
import { AuditPage } from '@/pages/AuditPage'
import { SettingsPage } from '@/pages/SettingsPage'

function CustomerRoute() {
  const { customerId } = useParams()
  if (!customerId) return <Navigate to="/customers" replace />
  return <CustomerDetailPage customerId={customerId} />
}

function CaseRoute() {
  const { caseId } = useParams()
  if (!caseId) return <Navigate to="/recovery" replace />
  return <CaseDetailPage caseId={caseId} />
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="recovery" element={<RecoveryPage />} />
        <Route path="recovery/:caseId" element={<CaseRoute />} />
        <Route path="customers" element={<CustomersPage />} />
        <Route path="customers/:customerId" element={<CustomerRoute />} />
        <Route path="revenue-risks" element={<RevenueRisksPage />} />
        <Route path="learning" element={<LearningPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="simulator" element={<SimulatorPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
