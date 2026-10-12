import type { DataSource } from '@/api/types'
import { roleAbilities, sourceAbilities, type RoleAbilities, type SourceAbilities } from '@/lib/permissions'
import { useAuth } from '@/providers/auth-context'

export function useRoleAbilities(): RoleAbilities {
  const { user } = useAuth()
  return roleAbilities(user)
}

export function useSourceAbilities(source: DataSource | undefined): SourceAbilities | null {
  const { user } = useAuth()
  return source ? sourceAbilities(source, user) : null
}
