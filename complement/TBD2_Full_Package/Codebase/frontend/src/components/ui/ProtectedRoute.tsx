import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore, UserRole, hasModule } from '@/store/auth'
import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  requiredRole?: UserRole
  requiredModule?: string
}

export function ProtectedRoute({ children, requiredRole, requiredModule }: Props) {
  const { user } = useAuthStore()
  const location  = useLocation()

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (requiredRole) {
    const roleOrder: UserRole[] = ['viewer', 'analyst', 'admin', 'super_admin']
    const userLevel     = roleOrder.indexOf(user.role)
    const requiredLevel = roleOrder.indexOf(requiredRole)
    if (userLevel < requiredLevel) {
      return <Navigate to="/dashboard" replace />
    }
  }

  // /pipeline is module-agnostic (Pipeline Monitor + Reports work for every
  // module), so it's a safe landing spot that can't loop back here - unlike
  // /dashboard, which is itself esgrc-gated.
  if (requiredModule && !hasModule(user, requiredModule)) {
    return <Navigate to="/pipeline" replace />
  }

  return <>{children}</>
}
