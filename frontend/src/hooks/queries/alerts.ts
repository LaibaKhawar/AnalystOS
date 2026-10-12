import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { alertsApi } from '@/api/endpoints'
import type { Alert } from '@/api/types'
import { qk } from './keys'

export const ALERT_POLL_MS = 60_000

export function useAlerts(unreadOnly = false, poll = false) {
  return useQuery({
    queryKey: qk.alerts(unreadOnly),
    queryFn: () => alertsApi.list(unreadOnly),
    refetchInterval: poll ? ALERT_POLL_MS : false,
  })
}

/** Latest unread alerts for the bell's panel (fetched when the panel opens). */
export const useUnreadAlerts = (enabled = true) =>
  useQuery({ queryKey: qk.alerts(true), queryFn: () => alertsApi.list(true), enabled })

/** Unread alert count, polled every minute for the bell in the app shell. */
export function useUnreadAlertCount() {
  return useQuery({
    queryKey: qk.alertsUnreadCount,
    queryFn: alertsApi.unreadCount,
    select: (data) => data.unread,
    refetchInterval: ALERT_POLL_MS,
  })
}

export function useMarkAlertRead() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => alertsApi.markRead(id),
    onSuccess: (alert: Alert) => {
      client.setQueryData<Alert[]>(qk.alerts(false), (list) => list?.map((a) => (a.id === alert.id ? alert : a)))
      client.setQueryData<Alert[]>(qk.alerts(true), (list) => list?.filter((a) => a.id !== alert.id))
      client.setQueryData<{ unread: number }>(qk.alertsUnreadCount, (data) =>
        data ? { unread: Math.max(0, data.unread - 1) } : data,
      )
      void client.invalidateQueries({ queryKey: qk.alertsAll })
    },
  })
}
