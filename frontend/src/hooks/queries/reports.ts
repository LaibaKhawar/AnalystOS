import { useQuery } from '@tanstack/react-query'
import { reportsApi } from '@/api/endpoints'
import { qk } from './keys'

export function useReports() {
  return useQuery({ queryKey: qk.reports, queryFn: reportsApi.list })
}

export function useReport(id: string | undefined) {
  return useQuery({ queryKey: qk.report(id ?? ''), queryFn: () => reportsApi.get(id ?? ''), enabled: Boolean(id) })
}

/** Report HTML fetched with auth and exposed as a blob URL for a sandboxed iframe. */
export function useReportHtml(id: string | undefined) {
  return useQuery({
    queryKey: qk.reportHtml(id ?? ''),
    queryFn: async () => {
      const blob = await reportsApi.html(id ?? '')
      return URL.createObjectURL(new Blob([blob], { type: 'text/html' }))
    },
    enabled: Boolean(id),
    staleTime: Infinity,
    gcTime: 60_000,
  })
}
