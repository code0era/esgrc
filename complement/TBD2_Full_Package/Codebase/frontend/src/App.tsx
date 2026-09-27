import { Routes, Route, Navigate } from 'react-router-dom'
import { Suspense, lazy, useEffect, useState } from 'react'
import { AppLayout } from '@/components/layout/AppLayout'
import { ProtectedRoute } from '@/components/ui/ProtectedRoute'
import { DashboardSkeleton } from '@/components/ui/Skeleton'
import { restoreSessionOnce } from '@/lib/session'
import { useAuthStore } from '@/store/auth'
import LoginPage    from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'

// Lazy-load pages for code splitting
const DashboardPage  = lazy(() => import('@/pages/DashboardPage'))
const RiskPage       = lazy(() => import('@/pages/RiskPage'))
const CompliancePage = lazy(() => import('@/pages/CompliancePage'))
const PipelinePage   = lazy(() => import('@/pages/PipelinePage'))
const ReportsPage    = lazy(() => import('@/pages/ReportsPage'))
const ProcessLogPage = lazy(() => import('@/pages/ProcessLogPage'))
const SettingsPage   = lazy(() => import('@/pages/SettingsPage'))

const PageLoader = () => <DashboardSkeleton />

export default function App() {
  // A reload starts with an empty store (the access token is memory-only by
  // design), but the httpOnly refresh cookie survives. Spend it once here so a
  // refresh keeps the session instead of bouncing the user to /login.
  //
  // The gate matters: ProtectedRoute reads the store synchronously, so without
  // it the first render redirects to /login before the restore resolves, and
  // the user sees a login screen flash even on success.
  const hasToken = useAuthStore((s) => s.token)
  const [restoring, setRestoring] = useState(!hasToken)

  useEffect(() => {
    if (!restoring) return
    let active = true
    restoreSessionOnce().finally(() => {
      if (active) setRestoring(false)
    })
    return () => {
      active = false
    }
    // Runs once on mount; restoreSessionOnce is itself idempotent per page load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (restoring) return <PageLoader />

  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login"    element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Protected routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />

        <Route path="dashboard" element={
          <ProtectedRoute requiredModule="esgrc">
            <Suspense fallback={<PageLoader />}>
              <DashboardPage />
            </Suspense>
          </ProtectedRoute>
        } />

        <Route path="risk" element={
          <ProtectedRoute requiredModule="esgrc">
            <Suspense fallback={<PageLoader />}>
              <RiskPage />
            </Suspense>
          </ProtectedRoute>
        } />

        <Route path="compliance" element={
          <ProtectedRoute requiredModule="esgrc">
            <Suspense fallback={<PageLoader />}>
              <CompliancePage />
            </Suspense>
          </ProtectedRoute>
        } />

        <Route path="pipeline" element={
          <Suspense fallback={<PageLoader />}>
            <PipelinePage />
          </Suspense>
        } />

        <Route path="reports" element={
          <Suspense fallback={<PageLoader />}>
            <ReportsPage />
          </Suspense>
        } />

        <Route path="process-log" element={
          <Suspense fallback={<PageLoader />}>
            <ProcessLogPage />
          </Suspense>
        } />

        <Route path="settings" element={
          <ProtectedRoute requiredRole="admin">
            <Suspense fallback={<PageLoader />}>
              <SettingsPage />
            </Suspense>
          </ProtectedRoute>
        } />
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
