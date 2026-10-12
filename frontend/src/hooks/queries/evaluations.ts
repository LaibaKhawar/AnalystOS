import { useQuery } from '@tanstack/react-query'
import { evaluationsApi } from '@/api/endpoints'
import { qk } from './keys'

export function useEvaluations() {
  return useQuery({ queryKey: qk.evaluations, queryFn: evaluationsApi.list })
}

export function useEvaluation(id: string | undefined) {
  return useQuery({
    queryKey: qk.evaluation(id ?? ''),
    queryFn: () => evaluationsApi.get(id ?? ''),
    enabled: Boolean(id),
  })
}
