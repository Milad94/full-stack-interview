import { Route, Routes } from 'react-router-dom'

import { AppLayout } from './components/AppLayout'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { AdjustmentsPage } from './features/adjustments/AdjustmentsPage'

export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/adjustments" element={<AdjustmentsPage />} />
      </Routes>
    </AppLayout>
  )
}
