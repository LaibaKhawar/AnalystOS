import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { conversationsApi } from '@/api/endpoints'
import type { Analysis, Conversation } from '@/api/types'
import { qk } from './keys'

export function useConversations(sourceId?: string, enabled = true) {
  return useQuery({
    queryKey: qk.conversations(sourceId),
    queryFn: () => conversationsApi.list(sourceId),
    enabled,
  })
}

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: qk.conversation(id ?? ''),
    queryFn: () => conversationsApi.get(id ?? ''),
    enabled: Boolean(id),
  })
}

export function useConversationAnalyses(id: string | undefined) {
  return useQuery({
    queryKey: qk.conversationAnalyses(id ?? ''),
    queryFn: () => conversationsApi.analyses(id ?? ''),
    enabled: Boolean(id),
  })
}

export function useCreateConversation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ sourceId, title }: { sourceId: string; title?: string }) => conversationsApi.create(sourceId, title),
    onSuccess: (conversation: Conversation) => {
      client.setQueryData(qk.conversation(conversation.id), conversation)
      void client.invalidateQueries({ queryKey: qk.conversationsAll })
    },
  })
}

export function useDeleteConversation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => conversationsApi.remove(id),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.conversationsAll }),
  })
}

export function useResetContext() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => conversationsApi.resetContext(id),
    onSuccess: (conversation: Conversation) => client.setQueryData(qk.conversation(conversation.id), conversation),
  })
}

export function useAsk(conversationId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (question: string) => conversationsApi.ask(conversationId, question),
    onSuccess: (analysis: Analysis) => {
      client.setQueryData<Analysis[]>(qk.conversationAnalyses(conversationId), (list) => [...(list ?? []), analysis])
      client.setQueryData(qk.analysis(analysis.id), analysis)
      void client.invalidateQueries({ queryKey: qk.conversationsAll })
      void client.invalidateQueries({ queryKey: qk.analysesAll })
      void client.invalidateQueries({ queryKey: qk.dashboard })
    },
  })
}
