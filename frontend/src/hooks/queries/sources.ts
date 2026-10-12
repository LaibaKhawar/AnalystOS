import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { sourcesApi } from '@/api/endpoints'
import type { ColumnPatch, ConnectionInput, DataSource, Table } from '@/api/types'
import { qk } from './keys'

export function useSources() {
  return useQuery({ queryKey: qk.sources, queryFn: sourcesApi.list })
}

export function useSource(id: string | undefined) {
  return useQuery({ queryKey: qk.source(id ?? ''), queryFn: () => sourcesApi.get(id ?? ''), enabled: Boolean(id) })
}

export function useTables(sourceId: string | undefined) {
  return useQuery({
    queryKey: qk.tables(sourceId ?? ''),
    queryFn: () => sourcesApi.tables(sourceId ?? ''),
    enabled: Boolean(sourceId),
  })
}

export function usePreview(sourceId: string, tableId: string | undefined) {
  return useQuery({
    queryKey: qk.preview(sourceId, tableId ?? ''),
    queryFn: () => sourcesApi.preview(sourceId, tableId ?? ''),
    enabled: Boolean(tableId),
  })
}

function useInvalidateSources() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: qk.sources })
    void client.invalidateQueries({ queryKey: qk.dashboard })
  }
}

export function useCreateConnection() {
  const invalidate = useInvalidateSources()
  return useMutation({
    mutationFn: (input: ConnectionInput) => sourcesApi.createConnection(input),
    onSuccess: invalidate,
  })
}

export function useRefreshSource() {
  const client = useQueryClient()
  const invalidate = useInvalidateSources()
  return useMutation({
    mutationFn: (id: string) => sourcesApi.refresh(id),
    onSuccess: (source: DataSource) => {
      client.setQueryData(qk.source(source.id), source)
      void client.invalidateQueries({ queryKey: qk.tables(source.id) })
      invalidate()
    },
  })
}

export function useDeleteSource() {
  const client = useQueryClient()
  const invalidate = useInvalidateSources()
  return useMutation({
    mutationFn: (id: string) => sourcesApi.remove(id),
    onSuccess: (_data, id) => {
      client.removeQueries({ queryKey: qk.source(id) })
      void client.invalidateQueries({ queryKey: qk.conversationsAll })
      invalidate()
    },
  })
}

export function usePatchColumn(sourceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ columnId, patch }: { columnId: string; patch: ColumnPatch }) =>
      sourcesApi.patchColumn(sourceId, columnId, patch),
    onSuccess: (column) => {
      client.setQueryData<Table[]>(qk.tables(sourceId), (tables) =>
        tables?.map((t) => ({ ...t, columns: t.columns.map((c) => (c.id === column.id ? column : c)) })),
      )
      void client.invalidateQueries({ queryKey: ['sources', sourceId, 'tables'] })
    },
  })
}
