import { request, requestBlob, uploadWithProgress, type UploadHandle } from './client'
import type {
  Alert,
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
  MetricDefinition,
  MetricInput,
  RegisterInput,
  Report,
  Schedule,
  ScheduleInput,
  ShareInput,
  SourceShare,
  SystemStatus,
  Table,
  TablePreview,
  TokenResponse,
  User,
  UserRole,
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
  shares: (id: string) => request<SourceShare[]>(`/sources/${enc(id)}/shares`),
  /** Creates a share, or changes the role of an existing one for the same email. */
  share: (id: string, input: ShareInput) =>
    request<SourceShare>(`/sources/${enc(id)}/shares`, { method: 'POST', body: input }),
  unshare: (id: string, shareId: string) =>
    request<void>(`/sources/${enc(id)}/shares/${enc(shareId)}`, { method: 'DELETE' }),
}

export const metricsApi = {
  list: (sourceId: string) => request<MetricDefinition[]>(`/sources/${enc(sourceId)}/metrics`),
  create: (sourceId: string, input: MetricInput) =>
    request<MetricDefinition>(`/sources/${enc(sourceId)}/metrics`, { method: 'POST', body: input }),
  update: (sourceId: string, metricId: string, input: MetricInput) =>
    request<MetricDefinition>(`/sources/${enc(sourceId)}/metrics/${enc(metricId)}`, { method: 'PUT', body: input }),
  remove: (sourceId: string, metricId: string) =>
    request<void>(`/sources/${enc(sourceId)}/metrics/${enc(metricId)}`, { method: 'DELETE' }),
}

export const adminApi = {
  users: () => request<User[]>('/admin/users'),
  setRole: (userId: string, role: UserRole) =>
    request<User>(`/admin/users/${enc(userId)}/role`, { method: 'PATCH', body: { role } }),
}

export const schedulesApi = {
  list: () => request<Schedule[]>('/schedules'),
  create: (input: ScheduleInput) => request<Schedule>('/schedules', { method: 'POST', body: input }),
  update: (id: string, input: ScheduleInput) =>
    request<Schedule>(`/schedules/${enc(id)}`, { method: 'PUT', body: input }),
  remove: (id: string) => request<void>(`/schedules/${enc(id)}`, { method: 'DELETE' }),
  run: (id: string) => request<Schedule>(`/schedules/${enc(id)}/run`, { method: 'POST' }),
}

export const alertsApi = {
  list: (unreadOnly = false) => request<Alert[]>('/alerts', { query: { unread_only: unreadOnly || undefined } }),
  unreadCount: () => request<{ unread: number }>('/alerts/unread-count'),
  markRead: (id: string) => request<Alert>(`/alerts/${enc(id)}/read`, { method: 'POST' }),
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
  /** The latest report generated for an analysis; 404 when there is none. */
  report: (id: string) => request<Report>(`/analyses/${enc(id)}/report`),
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
