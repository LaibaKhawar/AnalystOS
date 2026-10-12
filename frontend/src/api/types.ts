/**
 * Strict types for every AnalystOS API response.
 * Mirrors backend/app/api/schemas.py and the dict-returning routes.
 */

export type ISODate = string
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }
export type JsonObject = { [key: string]: JsonValue }
export type CellValue = string | number | boolean | null

/* ---------- errors ---------- */
export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> }
}

/* ---------- auth ---------- */
export interface User {
  id: string
  email: string
  name: string
  is_admin: boolean
}
export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}
export interface RegisterInput {
  email: string
  name: string
  password: string
}
export interface LoginInput {
  email: string
  password: string
}

/* ---------- sources ---------- */
export type SourceKind = 'file' | 'postgresql' | 'mysql' | 'sqlite'
export type ConnectionKind = Exclude<SourceKind, 'file'>
export type SourceStatus = 'ready' | 'pending' | 'error' | (string & {})

export interface IngestionTableReport {
  name: string
  display_name?: string
  rows: number
  warnings: string[]
  details?: {
    encoding?: string
    delimiter?: string
    has_header?: boolean
    rejected_rows?: number
    coercions?: unknown[]
    sheet?: string
  }
}
export interface IngestionReport {
  tables: IngestionTableReport[]
  warnings?: string[]
}

export interface DataSource {
  id: string
  kind: SourceKind
  name: string
  status: SourceStatus
  error: string | null
  host: string | null
  port: number | null
  database: string | null
  username: string | null
  db_schema: string | null
  allowed_tables: string[] | null
  restricted_columns: string[]
  created_at: ISODate
  last_checked_at: ISODate | null
  has_password: boolean
  table_count: number
  row_count: number
  dataset_id: string | null
  file_type: string | null
  size_bytes: number | null
  ingestion_report: IngestionReport | null
}

export interface ConnectionInput {
  name: string
  kind: ConnectionKind
  host?: string | null
  port?: number | null
  database: string
  username?: string | null
  password?: string | null
  db_schema?: string | null
  allowed_tables?: string[] | null
  restricted_columns?: string[]
}

export type ColumnRole = 'metric' | 'dimension' | 'identifier' | 'time' | 'text' | 'other'

export interface TopValue {
  value: CellValue
  count: number
}

export interface ColumnStats {
  count?: number
  null_count?: number
  missing_pct?: number
  distinct_count?: number
  unique_ratio?: number
  min?: number | string
  max?: number | string
  mean?: number
  median?: number
  std?: number
  sum?: number
  q1?: number
  q3?: number
  zeros?: number
  negatives?: number
  outlier_count_iqr?: number
  outlier_bounds?: [number, number]
  top_values?: TopValue[]
  examples?: CellValue[]
  flags?: string[]
  granularity?: string
  span_days?: number
  avg_length?: number
  concept?: string
  [key: string]: unknown
}

export interface Column {
  id: string
  name: string
  original_name: string
  ordinal: number
  physical_type: string
  inferred_type: string
  role: ColumnRole | (string & {})
  semantic_type: string | null
  semantic_confidence: number
  semantic_source: string
  is_pii: boolean
  stats: ColumnStats
}

export interface TableProfile {
  warnings?: string[]
  row_count?: number
  column_count?: number
  duplicate_rows?: number
  missing_cells_pct?: number
  metric_columns?: string[]
  dimension_columns?: string[]
  time_columns?: string[]
  identifier_columns?: string[]
  text_columns?: string[]
  constant_columns?: string[]
  [key: string]: unknown
}

export interface SemanticEntry {
  column: string
  concept?: string
  confidence?: number
  semantic_type?: string
}
export interface TableSemantic {
  table?: string
  metrics?: SemanticEntry[]
  dimensions?: SemanticEntry[]
  time?: SemanticEntry[]
  identifiers?: SemanticEntry[]
  text?: SemanticEntry[]
  pii_columns?: string[]
  uncertain_columns?: string[]
  [key: string]: unknown
}

export interface Table {
  id: string
  name: string
  display_name: string
  row_count: number
  column_count: number
  profile: TableProfile
  semantic: TableSemantic
  columns: Column[]
}

export interface TablePreview {
  columns: string[]
  rows: CellValue[][]
  masked_columns: string[]
}

export interface ColumnPatch {
  semantic_type?: string | null
  role?: ColumnRole | null
  is_pii?: boolean | null
}

/* ---------- conversations ---------- */
export interface ContextFilter {
  column?: string
  op?: string
  value?: JsonValue
}
export interface ConversationState {
  filters?: ContextFilter[]
  metric?: string | null
  dimension?: string | null
  period?: string | null
  history?: unknown[]
  last_analysis_id?: string
  [key: string]: unknown
}
export interface Conversation {
  id: string
  data_source_id: string
  title: string
  state: ConversationState
  created_at: ISODate
  updated_at: ISODate
}
export interface Message {
  id: string
  role: 'user' | 'assistant' | (string & {})
  content: string
  analysis_id: string | null
  created_at: ISODate
}

/* ---------- analyses ---------- */
export type AnalysisStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'needs_clarification'

export type StepStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped' | (string & {})

export interface PlanStep {
  id: string
  title: string
  tool: string
  args?: Record<string, unknown>
  depends_on?: string[]
  expected_output?: string
}
export interface Plan {
  goal?: string
  needs_clarification?: boolean
  clarification_question?: string | null
  assumptions?: string[]
  context_update?: {
    filters?: ContextFilter[]
    metric?: string | null
    dimension?: string | null
    period?: string | null
  }
  steps?: PlanStep[]
}

export interface Verification {
  claims_total?: number
  numeric_claims?: number
  verified?: number
  qualified?: number
  removed?: number
  repaired?: number
  draft_unsupported_rate?: number
  final_unsupported_rate?: number
  charts_verified?: number
  charts_total?: number
}

export interface ToolStats {
  tool_calls?: number
  tool_failures?: number
  retries?: number
  recovered_retries?: number
}

export interface Answer {
  headline?: string
  summary?: string[]
  caveats?: string[]
  assumptions?: string[]
  follow_up_questions?: string[]
  chart_ids?: string[]
  verification?: Verification
  failed_steps?: string[]
  tool_stats?: ToolStats
  clarification?: boolean
}

export interface AnalysisStep {
  id: string
  ordinal: number
  title: string
  tool: string
  purpose: string | null
  depends_on: string[]
  status: StepStatus
  added_by_replan: boolean
  result_summary: string | null
  started_at: ISODate | null
  completed_at: ISODate | null
}

export interface Analysis {
  id: string
  conversation_id: string
  data_source_id: string
  question: string
  status: AnalysisStatus
  plan: Plan
  answer: Answer
  summary: string | null
  error: string | null
  model: string | null
  input_tokens: number
  output_tokens: number
  llm_calls: number
  cost_usd: number
  latency_ms: number | null
  replans: number
  created_at: ISODate
  started_at: ISODate | null
  completed_at: ISODate | null
  steps: AnalysisStep[]
}

export type EventType =
  | 'status'
  | 'plan'
  | 'replan'
  | 'step_started'
  | 'step_completed'
  | 'step_failed'
  | 'step_skipped'
  | 'retry'
  | 'verification'
  | 'clarification'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | (string & {})

export interface AnalysisEvent {
  id: number
  type: EventType
  message: string
  payload: Record<string, unknown>
  created_at: ISODate
}

export type ChartType = 'line' | 'area' | 'bar' | 'stacked_bar' | 'scatter' | 'histogram' | 'box' | 'heatmap'

export interface ChartSpec {
  type?: string
  title?: string
  x: string
  y: string[]
  series?: string | null
  x_label?: string
  y_label?: string
  y_zero?: boolean
  note?: string
  source?: { sql?: string; name?: string; result_id?: string }
  [key: string]: unknown
}
export type ChartDatum = Record<string, CellValue>
export interface Chart {
  id: string
  title: string
  chart_type: ChartType | (string & {})
  spec: ChartSpec
  data: ChartDatum[]
  data_hash: string
  interpretation: string | null
  verified: boolean
  result_table_id: string | null
}

export type ClaimStatus = 'verified' | 'qualified' | 'no_numbers' | 'removed' | (string & {})
export type ClaimKind = 'fact' | 'interpretation' | 'recommendation' | 'caveat' | (string & {})

export interface ClaimMatch {
  token: string
  value: number
  value_key: string | null
  finding_id: string
  finding_label: string
  derived_formula: string | null
}
export interface ClaimVerification {
  matches?: ClaimMatch[]
  unsupported?: string[]
  notes?: string[]
  citations?: string[]
}
export interface EvidenceRef {
  id: string
  finding_id: string | null
  tool_execution_id: string | null
  result_table_id: string | null
  source_type: string
  values: Record<string, unknown>
  formula: string | null
  description: string | null
}
export interface Claim {
  id: string
  ordinal: number
  section: string
  kind: ClaimKind
  text: string
  original_text: string | null
  status: ClaimStatus
  numbers: string[]
  verification: ClaimVerification
  evidence: EvidenceRef[]
}

export interface Finding {
  id: string
  label: string
  kind: string
  statement: string
  values: Record<string, unknown>
  formula: string | null
  tool_execution_id: string | null
  result_table_id: string | null
}

export interface ResultColumn {
  name: string
  type?: string
}

export interface EvidenceItem {
  id: string
  source_type: string
  values: Record<string, unknown>
  formula: string | null
  description: string | null
  finding: { label: string; statement: string; kind: string } | null
  execution: {
    id: string
    tool: string
    status: string
    attempt: number
    input: Record<string, unknown>
    duration_ms: number
    created_at: ISODate
  } | null
  sql: {
    id: string
    sql: string
    status: string
    row_count: number | null
    duration_ms: number | null
    created_at: ISODate
  }[]
  python: { id: string; code: string; status: string; duration_ms: number | null }[]
  result: {
    id: string
    name: string
    columns: ResultColumn[]
    rows: CellValue[][]
    row_count: number
    truncated: boolean
  } | null
}
export interface ClaimEvidence {
  claim: Claim
  evidence: EvidenceItem[]
}

export interface Execution {
  id: string
  step_id: string | null
  tool: string
  input: Record<string, unknown>
  output: Record<string, unknown>
  status: string
  error: string | null
  error_kind: string | null
  attempt: number
  retry_of_id: string | null
  retry_reason: string | null
  duration_ms: number
  created_at: ISODate
}

export interface SqlValidation {
  ok?: boolean
  errors?: string[]
  warnings?: string[]
  tables?: string[]
  columns?: string[]
  applied_limit?: number
  statement_type?: string
}
export interface SqlRecord {
  id: string
  dialect: string
  sql_original: string
  sql_executed: string | null
  status: string
  row_count: number | null
  truncated: boolean
  error: string | null
  duration_ms: number | null
  validation: SqlValidation
  created_at: ISODate
}
export interface PythonRecord {
  id: string
  code: string
  status: string
  stdout: string | null
  stderr: string | null
  static_check: Record<string, unknown> | null
  limits: Record<string, unknown> | null
  duration_ms: number | null
  exit_code: number | null
  artifacts: { file: string; title: string | null }[]
}
export interface ResultRecord {
  id: string
  name: string
  columns: ResultColumn[]
  rows: CellValue[][]
  row_count: number
  truncated: boolean
  source: Record<string, unknown>
}
export interface ExecutionDetail {
  execution: Execution
  sql: SqlRecord[]
  python: PythonRecord[]
  results: ResultRecord[]
}

/* ---------- reports ---------- */
export interface Report {
  id: string
  analysis_id: string
  title: string
  content: {
    title?: string
    headline?: string
    question?: string
    generated_at?: string
    model?: string
    cost_usd?: number
    dataset?: { name?: string; kind?: string }
    [key: string]: unknown
  }
  created_at: ISODate
}

/* ---------- evaluations ---------- */
export type MetricValue = number | string | boolean | null | Record<string, unknown>
export interface EvaluationRun {
  id: string
  suite: string
  model: string | null
  status: string
  metrics: Record<string, MetricValue>
  config: Record<string, unknown>
  notes: string | null
  created_at: ISODate
  completed_at: ISODate | null
}
export interface EvaluationCase {
  id: string
  case_id: string
  category: string
  dataset: string
  question: string
  expected: unknown
  answer: unknown
  passed: boolean
  scores: Record<string, number | boolean | null>
  latency_ms: number | null
  input_tokens: number | null
  output_tokens: number | null
  cost_usd: number | null
  error: string | null
  analysis_id: string | null
}
export interface EvaluationRunDetail extends EvaluationRun {
  cases: EvaluationCase[]
}

/* ---------- system ---------- */
export interface SystemStatus {
  llm: { status: string; provider: string; model: string }
  sandbox: {
    status: string
    detail: string
    limits: { cpus: number; memory_mb: number; timeout_seconds: number; network: string }
  }
  sql: { max_rows: number; timeout_seconds: number }
  worker_mode: string
}
export interface DashboardStats {
  datasets: number
  connections: number
  connections_ready: number
  analyses: number
  total_cost_usd: number
  total_tokens: number
  avg_latency_ms: number | null
  analyses_by_status: Record<string, number>
  reports: number
}
