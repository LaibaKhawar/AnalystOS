import { Navigate, useParams } from 'react-router'
import { ErrorState } from '@/components/common/States'
import { PageSkeleton } from '@/components/common/PageSkeleton'
import { useAnalysis } from '@/hooks/queries/analyses'

/** Resolve an analysis id to its conversation in the workspace. */
export default function AnalysisRedirect() {
  const { analysisId = '' } = useParams()
  const analysis = useAnalysis(analysisId)
  if (analysis.isPending) return <PageSkeleton />
  if (analysis.isError)
    return (
      <ErrorState error={analysis.error} title="Could not open this analysis" onRetry={() => void analysis.refetch()} />
    )
  return <Navigate to={`/workspace/${analysis.data.conversation_id}?analysis=${analysis.data.id}`} replace />
}
