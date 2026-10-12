import { ChatCenteredTextIcon } from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router'
import type { Claim } from '@/api/types'
import { AnalysisTurn } from '@/components/analysis/AnalysisTurn'
import { EvidenceDrawer } from '@/components/analysis/EvidenceDrawer'
import { EmptyState, ErrorState } from '@/components/common/States'
import { Inspector } from '@/components/inspector/Inspector'
import { Skeleton } from '@/components/ui/skeleton'
import { ContinuousTabs } from '@/components/watermelon/continuous-tabs'
import { tabPanelProps } from '@/lib/tabs'
import { AskBox } from '@/components/workspace/AskBox'
import { SourcePanel } from '@/components/workspace/SourcePanel'
import { isActive } from '@/hooks/queries/analyses'
import { useAsk, useConversation, useConversationAnalyses } from '@/hooks/queries/conversations'
import { useSource } from '@/hooks/queries/sources'
import { useSourceAbilities } from '@/hooks/usePermissions'
import { errorMessage } from '@/api/client'
import { forgetConversation, rememberConversation } from '@/lib/last-conversation'
import { noDashes } from '@/lib/format'
import { cn } from '@/lib/utils'

type MobileTab = 'data' | 'thread' | 'inspect'

function ThreadSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-label="Loading conversation">
      {[0, 1].map((i) => (
        <div key={i} className="flex flex-col gap-3">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-64 w-full" />
        </div>
      ))}
    </div>
  )
}

export default function Workspace() {
  const { conversationId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const conversation = useConversation(conversationId)
  const analyses = useConversationAnalyses(conversationId)
  const source = useSource(conversation.data?.data_source_id)
  const ask = useAsk(conversationId)
  const abilities = useSourceAbilities(source.data)
  const readOnly = abilities !== null && !abilities.canAsk
  const [draft, setDraft] = useState('')
  const [focusKey, setFocusKey] = useState(0)
  const [evidence, setEvidence] = useState<{ analysisId: string; claimId: string } | null>(null)
  const [mobileTab, setMobileTab] = useState<MobileTab>('thread')
  const threadEnd = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (conversation.data) rememberConversation(conversation.data.id)
    if (conversation.isError) forgetConversation(conversationId)
  }, [conversation.data, conversation.isError, conversationId])

  const list = useMemo(() => analyses.data ?? [], [analyses.data])
  const selectedId = params.get('analysis') ?? list[list.length - 1]?.id ?? null
  const selected = list.find((a) => a.id === selectedId) ?? list[list.length - 1] ?? null
  const busy = list.some((a) => isActive(a.status))

  const count = list.length
  useEffect(() => {
    if (count) threadEnd.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [count])

  const select = (id: string) => {
    if (id === selectedId) return
    const next = new URLSearchParams(params)
    next.set('analysis', id)
    setParams(next, { replace: true })
  }

  const submit = async (question: string) => {
    try {
      const analysis = await ask.mutateAsync(question)
      const next = new URLSearchParams(params)
      next.set('analysis', analysis.id)
      setParams(next, { replace: true })
      setMobileTab('thread')
    } catch (error) {
      throw new Error(errorMessage(error), { cause: error })
    }
  }

  const followUp = (q: string) => {
    setDraft(q)
    setFocusKey((k) => k + 1)
  }

  const openClaim = (analysisId: string, claim: Claim) => setEvidence({ analysisId, claimId: claim.id })

  if (conversation.isError) {
    return (
      <div className="p-6">
        <ErrorState
          error={conversation.error}
          title="Could not open this conversation"
          onRetry={() => void conversation.refetch()}
        />
      </div>
    )
  }

  const left = conversation.data ? (
    <SourcePanel source={source.data} conversation={conversation.data} />
  ) : (
    <Skeleton className="h-96" />
  )
  const right = <Inspector analysis={selected} />

  return (
    <div className="flex h-[calc(100dvh-3rem)] flex-col lg:h-dvh">
      <div className="border-b px-3 py-2 lg:hidden">
        <ContinuousTabs<MobileTab>
          ariaLabel="Workspace sections"
          idPrefix="ws"
          value={mobileTab}
          onChange={setMobileTab}
          stretch
          tabs={[
            { id: 'data', label: 'Data' },
            { id: 'thread', label: 'Thread' },
            { id: 'inspect', label: 'Inspect' },
          ]}
        />
      </div>
      <div className="grid min-h-0 flex-1 lg:grid-cols-[260px_minmax(0,1fr)_360px] xl:grid-cols-[280px_minmax(0,1fr)_400px]">
        <aside
          {...tabPanelProps('ws', 'data')}
          aria-label="Data source and conversations"
          className={cn('min-h-0 overflow-y-auto border-r p-4', mobileTab === 'data' ? 'block' : 'hidden lg:block')}
        >
          {left}
        </aside>

        <section
          {...tabPanelProps('ws', 'thread')}
          aria-label="Analysis thread"
          className={cn('min-h-0 flex-col', mobileTab === 'thread' ? 'flex' : 'hidden lg:flex')}
        >
          <div className="flex items-center gap-2 border-b px-4 py-2.5 sm:px-6">
            <span className="text-muted-foreground text-xs">Analyzing</span>
            <span className="text-foreground truncate text-sm font-medium" data-testid="workspace-source-name">
              {source.data?.name ?? <Skeleton className="inline-block h-4 w-32 align-middle" />}
            </span>
            {conversation.data && (
              <span className="text-muted-foreground hidden truncate text-xs sm:inline">
                / {noDashes(conversation.data.title)}
              </span>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
            <div className="mx-auto flex max-w-3xl flex-col gap-10">
              {analyses.isPending && <ThreadSkeleton />}
              {analyses.isError && <ErrorState error={analyses.error} onRetry={() => void analyses.refetch()} />}
              {analyses.data && list.length === 0 && (
                <EmptyState
                  icon={<ChatCenteredTextIcon className="size-4" />}
                  title="Ask your first question"
                  description="Write a business question below. The analyst plans the work, runs read-only SQL or sandboxed Python, verifies every number and cites its source. Expect one to five minutes."
                />
              )}
              {list.map((a) => (
                <AnalysisTurn
                  key={a.id}
                  initial={a}
                  selected={a.id === selected?.id}
                  onSelect={select}
                  onOpenClaim={openClaim}
                  onFollowUp={followUp}
                  onClarify={submit}
                  conversationBusy={busy || readOnly}
                />
              ))}
              <div ref={threadEnd} />
            </div>
          </div>
          <div className="bg-background border-t px-4 py-3 sm:px-6">
            <div className="mx-auto max-w-3xl">
              <AskBox
                value={draft}
                onChange={setDraft}
                onSubmit={submit}
                disabled={busy || !conversation.data || readOnly}
                disabledReason={
                  readOnly
                    ? 'You have read-only access to this data source, so you cannot ask new questions here.'
                    : 'An analysis is running in this conversation. You can ask again when it finishes.'
                }
                sourceName={source.data?.name}
                focusKey={focusKey}
              />
            </div>
          </div>
        </section>

        <aside
          {...tabPanelProps('ws', 'inspect')}
          aria-label="Inspector"
          className={cn('min-h-0 overflow-y-auto border-l p-4', mobileTab === 'inspect' ? 'block' : 'hidden lg:block')}
        >
          {right}
        </aside>
      </div>
      <EvidenceDrawer
        analysisId={evidence?.analysisId ?? null}
        claimId={evidence?.claimId ?? null}
        onClose={() => setEvidence(null)}
      />
    </div>
  )
}
