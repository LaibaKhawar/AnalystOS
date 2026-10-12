import { FlaskIcon } from '@phosphor-icons/react'
import { EmptyState } from '@/components/common/States'

export function EvalEmpty() {
  return (
    <EmptyState
      icon={<FlaskIcon className="size-4" />}
      title="No evaluation runs yet"
      description={
        <>
          The evaluation suite asks a fixed set of questions with known answers and scores accuracy, unsupported claims,
          tool success, latency and cost. Run it from the backend directory with{' '}
          <code className="bg-muted text-foreground rounded-xs px-1 font-mono">make eval</code> or{' '}
          <code className="bg-muted text-foreground rounded-xs px-1 font-mono">python -m evals.run</code>. Results
          appear here when it finishes.
        </>
      }
    />
  )
}
