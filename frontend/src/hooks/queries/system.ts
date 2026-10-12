import { useQuery } from '@tanstack/react-query'
import { systemApi } from '@/api/endpoints'
import { qk } from './keys'

export function useDashboard() {
  return useQuery({ queryKey: qk.dashboard, queryFn: systemApi.dashboard })
}

export function useSystemStatus() {
  return useQuery({ queryKey: qk.systemStatus, queryFn: systemApi.status, refetchInterval: 60_000 })
}
