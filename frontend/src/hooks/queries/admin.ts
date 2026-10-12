import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '@/api/endpoints'
import type { User, UserRole } from '@/api/types'
import { qk } from './keys'

export function useAdminUsers(enabled = true) {
  return useQuery({ queryKey: qk.adminUsers, queryFn: adminApi.users, enabled })
}

export function useSetUserRole() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: UserRole }) => adminApi.setRole(userId, role),
    onSuccess: (user) => {
      client.setQueryData<User[]>(qk.adminUsers, (list) => list?.map((u) => (u.id === user.id ? user : u)))
      void client.invalidateQueries({ queryKey: qk.adminUsers })
      void client.invalidateQueries({ queryKey: qk.me })
    },
  })
}
