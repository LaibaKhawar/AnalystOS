import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { schedulesApi } from '@/api/endpoints'
import type { Schedule, ScheduleInput } from '@/api/types'
import { qk } from './keys'

export function useSchedules() {
  return useQuery({ queryKey: qk.schedules, queryFn: schedulesApi.list, refetchInterval: 60_000 })
}

function useInvalidateSchedules() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: qk.schedules })
    void client.invalidateQueries({ queryKey: qk.conversationsAll })
  }
}

/** Create when `id` is null, otherwise replace that schedule. */
export function useSaveSchedule() {
  const invalidate = useInvalidateSchedules()
  return useMutation({
    mutationFn: ({ id, input }: { id: string | null; input: ScheduleInput }) =>
      id ? schedulesApi.update(id, input) : schedulesApi.create(input),
    onSuccess: invalidate,
  })
}

export function useDeleteSchedule() {
  const invalidate = useInvalidateSchedules()
  return useMutation({ mutationFn: (id: string) => schedulesApi.remove(id), onSuccess: invalidate })
}

export function useRunSchedule() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => schedulesApi.run(id),
    onSuccess: (schedule: Schedule) => {
      client.setQueryData<Schedule[]>(qk.schedules, (list) => list?.map((s) => (s.id === schedule.id ? schedule : s)))
      void client.invalidateQueries({ queryKey: qk.schedules })
      void client.invalidateQueries({ queryKey: qk.analysesAll })
      void client.invalidateQueries({ queryKey: qk.dashboard })
      void client.invalidateQueries({ queryKey: qk.conversationAnalyses(schedule.conversation_id) })
      // Alerts are raised after the run finishes; check soon rather than waiting for the next poll.
      window.setTimeout(() => void client.invalidateQueries({ queryKey: qk.alertsAll }), 5_000)
    },
  })
}
