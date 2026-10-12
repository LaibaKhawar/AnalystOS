import { ErrorState } from '@/components/common/States'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { useClaimEvidence } from '@/hooks/queries/analyses'
import { EvidenceContent } from './EvidenceContent'

function EvidenceSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading evidence">
      <Skeleton className="h-5 w-24" />
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  )
}

export function EvidenceDrawer({
  analysisId,
  claimId,
  onClose,
}: {
  analysisId: string | null
  claimId: string | null
  onClose: () => void
}) {
  const query = useClaimEvidence(analysisId ?? undefined, claimId)
  return (
    <Sheet open={Boolean(claimId)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-xl lg:max-w-2xl" data-testid="evidence-drawer">
        <SheetHeader className="border-b px-5 py-4">
          <SheetTitle>Evidence</SheetTitle>
          <SheetDescription>How this statement was computed and checked against your data.</SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-5 py-5">
          {query.isPending && <EvidenceSkeleton />}
          {query.isError && (
            <ErrorState error={query.error} title="Could not load evidence" onRetry={() => void query.refetch()} />
          )}
          {query.data && analysisId && <EvidenceContent data={query.data} analysisId={analysisId} />}
        </div>
      </SheetContent>
    </Sheet>
  )
}
