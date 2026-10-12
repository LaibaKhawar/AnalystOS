import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { analysesApi } from '@/api/endpoints'
import type { Analysis, AnalysisStatus } from '@/api/types'
import { qk } from './keys'

export const ACTIVE_STATUSES: AnalysisStatus[] = ['queued', 'running']
export const isActive = (status: string | undefined) => status === 'queued' || status === 'running'

export function useRecentAnalyses(limit = 8) {
  return useQuery({
    queryKey: qk.analysesRecent(limit),
    queryFn: () => analysesApi.recent(limit),
    refetchInterval: (query) => (query.state.data?.some((a) => isActive(a.status)) ? 5000 : false),
  })
}

export function useAnalysis(id: string | undefined, initial?: Analysis) {
  return useQuery({
    queryKey: qk.analysis(id ?? ''),
    queryFn: () => analysesApi.get(id ?? ''),
    enabled: Boolean(id),
    initialData: initial,
  })
}

const done = (status: string | undefined) => status === 'completed'
const settled = (status: string | undefined) => Boolean(status) && !isActive(status)

export function useCharts(id: string, status: string | undefined) {
  return useQuery({ queryKey: qk.charts(id), queryFn: () => analysesApi.charts(id), enabled: settled(status) })
}

export function useClaims(id: string, status: string | undefined) {
  return useQuery({ queryKey: qk.claims(id), queryFn: () => analysesApi.claims(id), enabled: done(status) })
}

export function useFindings(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: qk.findings(id ?? ''),
    queryFn: () => analysesApi.findings(id ?? ''),
    enabled: Boolean(id) && enabled,
  })
}

export function useExecutions(id: string | undefined, active: boolean) {
  return useQuery({
    queryKey: qk.executions(id ?? ''),
    queryFn: () => analysesApi.executions(id ?? ''),
    enabled: Boolean(id),
    refetchInterval: active ? 4000 : false,
  })
}

export function useExecution(id: string, execId: string | null) {
  return useQuery({
    queryKey: qk.execution(id, execId ?? ''),
    queryFn: () => analysesApi.execution(id, execId ?? ''),
    enabled: Boolean(execId),
  })
}

export function useClaimEvidence(id: string | undefined, claimId: string | null) {
  return useQuery({
    queryKey: qk.evidence(id ?? '', claimId ?? ''),
    queryFn: () => analysesApi.claimEvidence(id ?? '', claimId ?? ''),
    enabled: Boolean(id && claimId),
  })
}

export function useArtifact(id: string, pythonId: string, file: string) {
  return useQuery({
    queryKey: qk.artifact(id, pythonId, file),
    queryFn: async () => URL.createObjectURL(await analysesApi.artifact(id, pythonId, file)),
    staleTime: Infinity,
  })
}

function useAnalysisMutation(fn: (id: string) => Promise<Analysis>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (analysis: Analysis) => {
      client.setQueryData(qk.analysis(analysis.id), analysis)
      void client.invalidateQueries({ queryKey: qk.conversationAnalyses(analysis.conversation_id) })
      void client.invalidateQueries({ queryKey: qk.analysesAll })
      void client.invalidateQueries({ queryKey: qk.dashboard })
    },
  })
}

export const useCancelAnalysis = () => useAnalysisMutation(analysesApi.cancel)
export const useRetryAnalysis = () => useAnalysisMutation(analysesApi.retry)

export function useCreateReport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (analysisId: string) => analysesApi.createReport(analysisId),
    onSuccess: (report) => {
      client.setQueryData(qk.report(report.id), report)
      void client.invalidateQueries({ queryKey: qk.reports })
      void client.invalidateQueries({ queryKey: qk.dashboard })
    },
  })
}
