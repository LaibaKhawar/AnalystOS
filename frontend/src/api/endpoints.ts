import { request, requestBlob, uploadWithProgress, type UploadHandle } from './client'
import type {
  Analysis,
  AnalysisEvent,
  Chart,
  Claim,
  ClaimEvidence,
  Column,
  ColumnPatch,
  ConnectionInput,
  Conversation,
  DashboardStats,
  DataSource,
  EvaluationRun,
  EvaluationRunDetail,
  Execution,
  ExecutionDetail,
  Finding,
  LoginInput,
  Message,
  RegisterInput,
  Report,
  SystemStatus,
  Table,
  TablePreview,
  TokenResponse,
  User,
} from './types'

const enc = encodeURIComponent

export const authApi = {
  register: (input: RegisterInput) => request<TokenResponse>('/auth/register', { method: 'POST', body: input }),
  login: (input: LoginInput) => request<TokenResponse>('/auth/login', { method: 'POST', body: input }),
  me: () => request<User>('/auth/me'),
}

export const systemApi = {
  status: () => request<SystemStatus>('/system/status'),
  dashboard: () => request<DashboardStats>('/dashboard'),
}

export const sourcesApi = {
  list: () => request<DataSource[]>('/sources'),
  get: (id: string) => request<DataSource>(`/sources/${enc(id)}`),
  upload: (file: File, name: string | undefined, onProgress: (fraction: number) => void): UploadHandle<DataSource> => {
    const form = new FormData()
    form.append('file', file)
    if (name && name.trim()) form.append('name', name.trim())
    return uploadWithProgress<DataSource>('/sources/upload', form, onProgress)
  },
  createConnection: (input: ConnectionInput) =>
    request<DataSource>('/sources/connections', { method: 'POST', body: input }),
  refresh: (id: string) => request<DataSource>(`/sources/${enc(id)}/refresh`, { method: 'POST' }),
  remove: (id: string) => request<void>(`/sources/${enc(id)}`, { method: 'DELETE' }),
  tables: (id: string) => request<Table[]>(`/sources/${enc(id)}/tables`),
  preview: (id: string, tableId: string) => request<TablePreview>(`/sources/${enc(id)}/tables/${enc(tableId)}/preview`),
  patchColumn: (id: string, columnId: string, patch: ColumnPatch) =>
    request<Column>(`/sources/${enc(id)}/columns/${enc(columnId)}`, { method: 'PATCH', body: patch }),
}

export const conversationsApi = {
  list: (dataSourceId?: string) =>
    request<Conversation[]>('/conversations', { query: { data_source_id: dataSourceId } }),
  get: (id: string) => request<Conversation>(`/conversations/${enc(id)}`),
  create: (dataSourceId: string, title?: string) =>
    request<Conversation>('/conversations', { method: 'POST', body: { data_source_id: dataSourceId, title } }),
  remove: (id: string) => request<void>(`/conversations/${enc(id)}`, { method: 'DELETE' }),
  resetContext: (id: string) => request<Conversation>(`/conversations/${enc(id)}/reset-context`, { method: 'POST' }),
  messages: (id: string) => request<Message[]>(`/conversations/${enc(id)}/messages`),
  analyses: (id: string) => request<Analysis[]>(`/conversations/${enc(id)}/analyses`),
  ask: (id: string, question: string) =>
    request<Analysis>(`/conversations/${enc(id)}/ask`, { method: 'POST', body: { question } }),
}

export const analysesApi = {
  recent: (limit = 20) => request<Analysis[]>('/analyses', { query: { limit } }),
  get: (id: string) => request<Analysis>(`/analyses/${enc(id)}`),
  cancel: (id: string) => request<Analysis>(`/analyses/${enc(id)}/cancel`, { method: 'POST' }),
  retry: (id: string) => request<Analysis>(`/analyses/${enc(id)}/retry`, { method: 'POST' }),
  events: (id: string, after = 0) => request<AnalysisEvent[]>(`/analyses/${enc(id)}/events`, { query: { after } }),
  executions: (id: string) => request<Execution[]>(`/analyses/${enc(id)}/executions`),
  execution: (id: string, executionId: string) =>
    request<ExecutionDetail>(`/analyses/${enc(id)}/executions/${enc(executionId)}`),
  artifact: (id: string, pythonId: string, file: string) =>
    requestBlob(`/analyses/${enc(id)}/artifacts/${enc(pythonId)}/${enc(file)}`),
  charts: (id: string) => request<Chart[]>(`/analyses/${enc(id)}/charts`),
  claims: (id: string) => request<Claim[]>(`/analyses/${enc(id)}/claims`),
  findings: (id: string) => request<Finding[]>(`/analyses/${enc(id)}/findings`),
  claimEvidence: (id: string, claimId: string) =>
    request<ClaimEvidence>(`/analyses/${enc(id)}/claims/${enc(claimId)}/evidence`),
  resultCsvPath: (id: string, resultId: string) => `/analyses/${enc(id)}/results/${enc(resultId)}.csv`,
  createReport: (id: string) => request<Report>(`/analyses/${enc(id)}/report`, { method: 'POST' }),
}

export const reportsApi = {
  list: () => request<Report[]>('/reports'),
  get: (id: string) => request<Report>(`/reports/${enc(id)}`),
  html: (id: string) => requestBlob(`/reports/${enc(id)}/html`),
  htmlPath: (id: string) => `/reports/${enc(id)}/html`,
  pdfPath: (id: string) => `/reports/${enc(id)}/pdf`,
  xlsxPath: (id: string) => `/reports/${enc(id)}/results.xlsx`,
}

export const evaluationsApi = {
  list: () => request<EvaluationRun[]>('/evaluations'),
  get: (id: string) => request<EvaluationRunDetail>(`/evaluations/${enc(id)}`),
}
