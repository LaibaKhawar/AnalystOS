import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { metricsApi } from '@/api/endpoints'
import type { MetricInput } from '@/api/types'
import { qk } from './keys'

export function useMetrics(sourceId: string) {
  return useQuery({
    queryKey: qk.metrics(sourceId),
    queryFn: () => metricsApi.list(sourceId),
    enabled: Boolean(sourceId),
  })
}

/** Create when `metricId` is null, otherwise replace that metric. */
export function useSaveMetric(sourceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ metricId, input }: { metricId: string | null; input: MetricInput }) =>
      metricId ? metricsApi.update(sourceId, metricId, input) : metricsApi.create(sourceId, input),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.metrics(sourceId) }),
  })
}

export function useDeleteMetric(sourceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (metricId: string) => metricsApi.remove(sourceId, metricId),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.metrics(sourceId) }),
  })
}
