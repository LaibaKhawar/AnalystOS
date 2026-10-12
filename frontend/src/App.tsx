import { QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, useState, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router'
import { AppShell } from '@/components/layout/AppShell'
import { PageSkeleton } from '@/components/common/PageSkeleton'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { createQueryClient } from '@/lib/query-client'
import { safeNext } from '@/lib/validation'
import { AuthProvider } from '@/providers/AuthProvider'
import { useAuth } from '@/providers/auth-context'
import { ThemeProvider } from '@/providers/ThemeProvider'

const Landing = lazy(() => import('@/pages/Landing'))
const Login = lazy(() => import('@/pages/Login'))
const Register = lazy(() => import('@/pages/Register'))
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Datasets = lazy(() => import('@/pages/Datasets'))
const Connections = lazy(() => import('@/pages/Connections'))
const Explorer = lazy(() => import('@/pages/Explorer'))
const WorkspaceIndex = lazy(() => import('@/pages/WorkspaceIndex'))
const Workspace = lazy(() => import('@/pages/Workspace'))
const Reports = lazy(() => import('@/pages/Reports'))
const ReportView = lazy(() => import('@/pages/ReportView'))
const Evaluations = lazy(() => import('@/pages/Evaluations'))
const EvaluationDetail = lazy(() => import('@/pages/EvaluationDetail'))
const AnalysisRedirect = lazy(() => import('@/pages/AnalysisRedirect'))
const Schedules = lazy(() => import('@/pages/Schedules'))
const Alerts = lazy(() => import('@/pages/Alerts'))
const AdminUsers = lazy(() => import('@/pages/AdminUsers'))
const EvaluationCompare = lazy(() => import('@/pages/EvaluationCompare'))
const NotFound = lazy(() => import('@/pages/NotFound'))

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()
  if (!isAuthenticated) {
    const next = location.pathname + location.search
    return <Navigate to={location.pathname === '/' ? '/welcome' : `/login?next=${encodeURIComponent(next)}`} replace />
  }
  return <>{children}</>
}

/** Signed-in users skip auth pages: new accounts go to Datasets, sign-ins return to `next`. */
function PublicOnly({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()
  if (!isAuthenticated) return <>{children}</>
  const target =
    location.pathname === '/register' ? '/datasets' : safeNext(new URLSearchParams(location.search).get('next'))
  return <Navigate to={target} replace />
}

function AppRoutes() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route path="/welcome" element={<Landing />} />
        <Route
          path="/login"
          element={
            <PublicOnly>
              <Login />
            </PublicOnly>
          }
        />
        <Route
          path="/register"
          element={
            <PublicOnly>
              <Register />
            </PublicOnly>
          }
        />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="datasets" element={<Datasets />} />
          <Route path="connections" element={<Connections />} />
          <Route path="sources/:sourceId" element={<Explorer />} />
          <Route path="workspace" element={<WorkspaceIndex />} />
          <Route path="workspace/by-analysis/:analysisId" element={<AnalysisRedirect />} />
          <Route path="workspace/:conversationId" element={<Workspace />} />
          <Route path="reports" element={<Reports />} />
          <Route path="reports/:reportId" element={<ReportView />} />
          <Route path="schedules" element={<Schedules />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="admin/users" element={<AdminUsers />} />
          <Route path="evaluations" element={<Evaluations />} />
          <Route path="evaluations/compare" element={<EvaluationCompare />} />
          <Route path="evaluations/:runId" element={<EvaluationDetail />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  )
}

export function App() {
  const [queryClient] = useState(createQueryClient)
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || undefined}>
          <AuthProvider>
            <TooltipProvider delayDuration={200}>
              <AppRoutes />
              <Toaster position="bottom-right" />
            </TooltipProvider>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
