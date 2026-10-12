import { UsersThreeIcon } from '@phosphor-icons/react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { User, UserRole } from '@/api/types'
import { AccessNotice } from '@/components/common/AccessNotice'
import { PageHeader } from '@/components/common/PageHeader'
import { EmptyState, ErrorState } from '@/components/common/States'
import { Pill } from '@/components/common/StatusBadge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useAdminUsers, useSetUserRole } from '@/hooks/queries/admin'
import { useRoleAbilities } from '@/hooks/usePermissions'
import { ROLE_DESCRIPTION, ROLE_LABEL, userRole } from '@/lib/permissions'
import { useAuth } from '@/providers/auth-context'

const ROLES: UserRole[] = ['admin', 'analyst', 'viewer']

function UserRow({ user, isSelf }: { user: User; isSelf: boolean }) {
  const setRole = useSetUserRole()
  const role = userRole(user)
  const change = (next: UserRole) =>
    setRole.mutate(
      { userId: user.id, role: next },
      { onSuccess: (u) => toast.success(`${u.name} is now ${ROLE_LABEL[userRole(u)].toLowerCase()}`) },
    )
  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-4" data-testid="admin-user-row">
      <div className="min-w-0 flex-1">
        <p className="text-foreground flex items-center gap-2 text-sm font-medium">
          <span className="truncate">{user.name}</span>
          {isSelf && <Pill tone="brand">You</Pill>}
        </p>
        <p className="text-muted-foreground truncate text-xs">{user.email}</p>
        {setRole.isError && (
          <p className="text-danger mt-1 text-xs" role="alert">
            {errorMessage(setRole.error)}
          </p>
        )}
      </div>
      <Select value={role} onValueChange={(v) => change(v as UserRole)} disabled={setRole.isPending}>
        <SelectTrigger className="w-full sm:w-36" aria-label={`Role for ${user.email}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {ROLES.map((r) => (
            <SelectItem key={r} value={r}>
              {ROLE_LABEL[r]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </li>
  )
}

function UsersSkeleton() {
  return (
    <div className="bg-card flex flex-col divide-y rounded-lg border" aria-busy="true" aria-label="Loading users">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3">
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-56 max-w-full" />
          </div>
          <Skeleton className="h-8 w-36" />
        </div>
      ))}
    </div>
  )
}

export default function AdminUsers() {
  const { isAdmin } = useRoleAbilities()
  const { user } = useAuth()
  const users = useAdminUsers(isAdmin && Boolean(user))

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Users" description="Everyone with an account on this workspace and what their role allows." />
      {user && !isAdmin ? (
        <AccessNotice title="Admins only">
          Only admins can see and change user roles. Ask an admin if your role needs to change.
        </AccessNotice>
      ) : (
        <>
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {ROLES.map((r) => (
              <div key={r} className="bg-muted/30 rounded-lg border p-3">
                <dt className="text-foreground text-sm font-medium">{ROLE_LABEL[r]}</dt>
                <dd className="text-muted-foreground mt-0.5 text-xs">{ROLE_DESCRIPTION[r]}</dd>
              </div>
            ))}
          </dl>
          {(users.isPending || !user) && <UsersSkeleton />}
          {users.isError && <ErrorState error={users.error} onRetry={() => void users.refetch()} />}
          {users.data?.length === 0 && (
            <EmptyState
              icon={<UsersThreeIcon className="size-4" />}
              title="No users yet"
              description="People appear here after they create an account."
            />
          )}
          {(users.data?.length ?? 0) > 0 && (
            <ul className="bg-card divide-y rounded-lg border" aria-label="Users">
              {users.data?.map((u) => (
                <UserRow key={u.id} user={u} isSelf={u.id === user?.id} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
