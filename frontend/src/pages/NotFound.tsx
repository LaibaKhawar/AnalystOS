import { Link } from 'react-router'
import { EmptyState } from '@/components/common/States'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <EmptyState
      title="This page does not exist"
      description="The link may be outdated, or the item was deleted."
      action={
        <Button asChild variant="outline">
          <Link to="/">Back to dashboard</Link>
        </Button>
      }
    />
  )
}
