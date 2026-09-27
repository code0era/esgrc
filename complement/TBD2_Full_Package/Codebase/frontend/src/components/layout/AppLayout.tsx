import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { CopilotPanel } from '@/components/copilot/CopilotPanel'
import { useCopilotStore } from '@/store/copilot'
import { MessageSquare } from 'lucide-react'

export function AppLayout() {
  const toggle = useCopilotStore((s) => s.toggle)
  const isOpen = useCopilotStore((s) => s.isOpen)
  const location = useLocation()

  return (
    <div className="flex h-screen bg-bg-base overflow-hidden">
      <Sidebar />

      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto p-6">
          {/* key={pathname} forces a remount on navigation - ErrorBoundary has no
              other way to know the route changed (Outlet's children prop changes
              every render regardless), so without it a broken page's tripped
              boundary keeps showing "Something went wrong" over every
              subsequent page the user navigates to, until a manual reload. */}
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </div>
      </main>

      {/* Co-Pilot floating button */}
      <button
        id="copilot-toggle-btn"
        className="fixed bottom-6 right-6 w-14 h-14 rounded-full bg-gradient-primary
                   shadow-glow-primary flex items-center justify-center
                   hover:scale-110 active:scale-95 transition-all duration-200 z-40"
        onClick={toggle}
        aria-label="Open AI Co-Pilot"
      >
        <MessageSquare size={22} className="text-white" />
      </button>

      {/* Co-Pilot panel */}
      {isOpen && <CopilotPanel />}
    </div>
  )
}
