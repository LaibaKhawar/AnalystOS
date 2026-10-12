import { ArrowLeftIcon, FlaskIcon } from '@phosphor-icons/react'
import { Link, useSearchParams } from 'react-router'
import { PageHeader } from '@/components/common/PageHeader'
import { EmptyState, ErrorState } from '@/components/common/States'
import { CompareTable } from '@/components/evaluations/CompareTable'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useEvaluations } from '@/hooks/queries/evaluations'
import { MIN_COMPARE, parseRunIds } from '@/lib/compare'

export default function EvaluationCompare() {
  const [params] = useSearchParams()
  const ids = parseRunIds(params.get('runs'))
  const runs = useEvaluations()
  const selected = ids.flatMap((id) => runs.data?.find((r) => r.id === id) ?? [])
  const missing = runs.data ? ids.length - selected.length : 0

  return (
    <div className="flex flex-col gap-6">
      <Link
        to="/evaluations"
        className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1.5 text-xs"
      >
        <ArrowLeftIcon className="size-3.5" /> All runs
      </Link>
      <PageHeader
        title="Compare runs"
        description="Key metrics side by side, for example the same suite on different models. The best value in each row is highlighted."
      />
      {runs.isPending && <Skeleton className="h-96" />}
      {runs.isError && <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />}
      {runs.data && selected.length < MIN_COMPARE && (
        <EmptyState
          icon={<FlaskIcon className="size-4" />}
          title="Choose at least two runs"
          description={
            missing > 0
              ? 'Some of the selected runs no longer exist. Pick two to four runs on the evaluations page.'
              : 'Pick two to four runs on the evaluations page, then choose Compare.'
          }
          action={
            <Button asChild variant="outline">
              <Link to="/evaluations">Pick runs</Link>
            </Button>
          }
        />
      )}
      {selected.length >= MIN_COMPARE && (
        <>
          {missing > 0 && (
            <p className="text-muted-foreground text-sm" role="status">
              {missing} selected {missing === 1 ? 'run was' : 'runs were'} not found and {missing === 1 ? 'is' : 'are'}{' '}
              left out.
            </p>
          )}
          <CompareTable runs={selected} />
        </>
      )}
    </div>
  )
}
