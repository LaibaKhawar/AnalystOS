import { ChatCenteredTextIcon } from '@phosphor-icons/react'
import { Link, Navigate } from 'react-router'
import { EmptyState, ErrorState } from '@/components/common/States'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSkeleton } from '@/components/common/PageSkeleton'
import { Button } from '@/components/ui/button'
import { useConversations } from '@/hooks/queries/conversations'
import { lastConversation } from '@/lib/last-conversation'

export default function WorkspaceIndex() {
  const remembered = lastConversation()
  const conversations = useConversations(undefined, !remembered)
  if (remembered) return <Navigate to={`/workspace/${remembered}`} replace />
  if (conversations.isPending) return <PageSkeleton />
  if (conversations.isError)
    return <ErrorState error={conversations.error} onRetry={() => void conversations.refetch()} />
  const first = conversations.data[0]
  if (first) return <Navigate to={`/workspace/${first.id}`} replace />
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Workspace" description="Where questions become verified answers." />
      <EmptyState
        icon={<ChatCenteredTextIcon className="size-4" />}
        title="No conversations yet"
        description="Open a dataset or connection and choose Ask a question to start a conversation about it."
        action={
          <Button asChild>
            <Link to="/datasets">Choose a dataset</Link>
          </Button>
        }
      />
    </div>
  )
}
