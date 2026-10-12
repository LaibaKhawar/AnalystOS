import type { DataSource, SourceAccess, User, UserRole } from '@/api/types'

export const ROLE_LABEL: Record<UserRole, string> = { admin: 'Admin', analyst: 'Analyst', viewer: 'Viewer' }

export const ROLE_DESCRIPTION: Record<UserRole, string> = {
  admin: 'Full access, including user management and every data source.',
  analyst: 'Uploads data, connects databases, asks questions and schedules analyses.',
  viewer: 'Reads shared data sources and analyses. Cannot upload, connect, ask or schedule.',
}

/**
 * The account role. While the profile is still loading the user is treated as an analyst so actions do not
 * flicker; the server enforces roles on every request and the UI corrects itself once the profile arrives.
 */
export function userRole(user: User | null | undefined): UserRole {
  if (!user) return 'analyst'
  if (user.role === 'admin' || user.role === 'analyst' || user.role === 'viewer') return user.role
  return user.is_admin ? 'admin' : 'analyst'
}

/** Workspace-wide abilities that depend only on the account role. */
export interface RoleAbilities {
  role: UserRole
  isAdmin: boolean
  /** Upload files, connect databases, ask questions and create schedules. */
  canCreate: boolean
}

export function roleAbilities(user: User | null | undefined): RoleAbilities {
  const role = userRole(user)
  return { role, isAdmin: role === 'admin', canCreate: role !== 'viewer' }
}

/** Access to one source. Upload responses omit `access`: they are always the caller's own source. */
export function sourceAccess(source: Pick<DataSource, 'access' | 'owned'>): SourceAccess {
  if (source.access) return source.access
  return source.owned === false ? 'read' : 'manage'
}

export interface SourceAbilities {
  access: SourceAccess
  shared: boolean
  /** Delete, refresh, edit columns, manage metrics and sharing. */
  canManage: boolean
  /** Start conversations and schedules on this source. */
  canAsk: boolean
}

export function sourceAbilities(
  source: Pick<DataSource, 'access' | 'owned'>,
  user: User | null | undefined,
): SourceAbilities {
  const access = sourceAccess(source)
  const { canCreate } = roleAbilities(user)
  return {
    access,
    shared: source.owned === false,
    canManage: access === 'manage',
    canAsk: canCreate && (access === 'manage' || access === 'ask'),
  }
}

export const ACCESS_LABEL: Record<SourceAccess, string> = {
  manage: 'Can manage',
  ask: 'Can ask',
  read: 'Read only',
}

/** Why a viewer cannot do something, phrased for inline notices. */
export const VIEWER_EXPLANATION =
  'Your account has the viewer role, which can read shared data and analyses. Ask an admin for the analyst role to do this.'
