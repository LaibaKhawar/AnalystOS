import type { DataSource, Relationship } from '@/api/types'

/** Join keys for a source: on the source itself (all kinds), falling back to the upload's ingestion report. */
export function sourceRelationships(source: Pick<DataSource, 'relationships' | 'ingestion_report'>): Relationship[] {
  if (source.relationships && source.relationships.length > 0) return source.relationships
  return source.ingestion_report?.relationships ?? []
}
