export type DomainScope = 'auto' | 'c' | 'b' | 'kol'
export type RecordDomain = 'C' | 'B' | 'K'
export type DisplayCategory = 'feedback' | 'risk_assessment' | 'risk_alert' | 'policy' | 'project' | 'kol_trend'
export type RiskState = 'none' | 'normal' | 'alert'

export interface RagRecord {
  id: string
  source_system: 'C' | 'B' | 'KOL'
  source_record_id: string
  record_type: string
  record_mode: string
  business_key: string
  source_version: number
  status: string
  effective_at: string
  source_updated_at: string
  source_url: string | null
  business_date: string | null
  is_mock: boolean
  payload_json: Record<string, unknown> | string
  content_hash: string
  retrieval_text: string
  target_knowledge_base: string
  created_at: string
  updated_at: string
  display_category?: DisplayCategory | string
  risk_state?: RiskState | string
  display_summary?: string | null
}

export interface RecordsResponse {
  items: RagRecord[]
  page: number
  page_size: number
  total: number
}

export interface DashboardSummary {
  risks: {
    today_formal_alerts: number
    active: number
    pending_cross_domain: number | null
    recovered: number
  }
  knowledge: {
    upstream_current: number
    supplemental: number
    public_notes: number
    correction_feedback: number
  }
}

export interface SyncSummaryItem {
  pending: number
  processing: number
  completed: number
  failed: number
  timed_out: number
}

export interface SyncSummaryResponse {
  targets: Record<string, SyncSummaryItem>
}

export interface RiskItem {
  id: string
  vehicle_model: string | null
  part: string | null
  region: string | null
  risk_type: string | null
  brand: string | null
  open_episode_id: string | null
}

export interface RiskDetail {
  id: string
  vehicle_model: string | null
  part: string | null
  region: string | null
  risk_type: string | null
  brand: string | null
  open_episode: {
    id: string
    status: string
    started_at: string
    recovered_at: string | null
    current_value: number | null
    threshold: number | null
    trend_points: Array<{
      id: string
      business_time: string
      hit_value: number | null
      threshold: number | null
      source_record_id: string | null
      source_version: number | null
    }>
  } | null
  episodes: Array<Record<string, unknown>>
}

export interface RiskInvestigationTask {
  owner_domain: 'C' | 'B' | 'KOL'
  task_type: string
  assignee?: string | null
  expected_output_type: string
  is_required: boolean
}

export interface RiskInvestigationDraft {
  summary: string
  domain_impacts: Record<string, string>
  evidence: Array<{
    record_id: string
    domain: 'c_current' | 'c_history' | 'b_business' | 'kol'
    source_version: number
    source_url: string | null
    business_date: string | null
    title: string
    preview: string
  }>
  evidence_gaps: string[]
  limitations: string[]
  tasks: RiskInvestigationTask[]
}

export interface RiskInvestigationRun {
  id: string
  risk_object_id: string
  episode_id: string
  status: 'queued' | 'running' | 'awaiting_approval' | 'needs_clarification' | 'no_evidence' | 'failed' | 'approved' | 'rejected' | 'stale'
  object_version: number
  tool_trace: Array<Record<string, unknown>>
  draft: RiskInvestigationDraft | null
  decision: string | null
  decision_reason: string | null
  event_id: string | null
  candidate_id: string | null
  case_id: string | null
  error_code: string | null
}

export interface QueryOutput {
  summary: string | null
  consumer_signal: string | null
  business_impact: string | null
  kol_impact: string | null
  action_recommendations: string | null
  evidence: Array<{
    record_id: string
    target_knowledge_base: string
    score: number | null
    source_version: number
  }>
  data_time: string[]
  limitations: string | null
}

export type SemanticFieldKey = 'summary' | 'consumer_signal' | 'business_impact' | 'kol_impact' | 'actions'
export type SemanticFieldSource = 'maxkb' | 'deterministic' | 'none' | string

export interface SemanticFieldInfo {
  source: SemanticFieldSource
  notice: string | null
}

export type SemanticFields = Partial<Record<SemanticFieldKey, SemanticFieldInfo>>

export interface QueryMeta {
  retrieval_ms: number
  generation_ms: number
  total_ms: number
  generation_source: string
  generation_status: 'ok' | 'degraded' | 'no_evidence' | 'clarification' | 'error' | string
  degraded_reason: string | null
  semantic_fields?: SemanticFields
}

export interface QueryResponse {
  request_id: string
  query: string
  selected_targets: string[]
  evidence_count: number
  output: QueryOutput
  query_meta: QueryMeta
  clarification?: {
    required: string[]
    reason: string
    question: string
  }
}

const SEMANTIC_OUTPUT_KEYS: Record<SemanticFieldKey, keyof QueryOutput> = {
  summary: 'summary',
  consumer_signal: 'consumer_signal',
  business_impact: 'business_impact',
  kol_impact: 'kol_impact',
  actions: 'action_recommendations',
}

const SEMANTIC_FALLBACK_NOTICES: Partial<Record<SemanticFieldKey, string>> = {
  consumer_signal: 'No valid evidence supports consumer signals in the selected scope.',
  business_impact: 'No valid evidence supports business impact in the selected scope.',
  kol_impact: 'No valid evidence supports creator impact in the selected scope.',
}

export function semanticFieldInfo(result: QueryResponse, field: SemanticFieldKey): SemanticFieldInfo {
  const explicit = result.query_meta?.semantic_fields?.[field]
  if (explicit) return explicit
  const value = result.output?.[SEMANTIC_OUTPUT_KEYS[field]]
  if (value) {
    return {
      source: result.query_meta?.generation_source === 'maxkb' ? 'maxkb' : 'deterministic',
      notice: null,
    }
  }
  return {
    source: 'none',
    notice: SEMANTIC_FALLBACK_NOTICES[field] || null,
  }
}

export function semanticStatusLabel(result: QueryResponse): string {
  const status = result.query_meta?.generation_status
  if (status === 'ok') {
  if (result.query_meta.generation_source === 'maxkb') return 'Analysis completed using current knowledge'
  if (result.query_meta.generation_source === 'mixed') return 'Partially summarized by the LLM; remaining fields use evidence-based fallbacks'
  return 'Evidence review completed'
  }
  if (status === 'degraded') {
    return result.query_meta.generation_source === 'mixed'
    ? 'Partially summarized by the LLM; remaining fields use evidence-based fallbacks'
    : 'Returned an evidence-based fallback'
  }
  if (status === 'clarification') return 'More query details needed'
  if (status === 'no_evidence') return 'No valid evidence found'
  return 'Query incomplete'
}

export class RagApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'RagApiError'
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  headers.set('Accept', 'application/json')
  const response = await fetch(`/backend${path}`, { ...init, headers })
  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = text
    }
  }
  if (!response.ok) {
    const payloadObject = typeof payload === 'object' && payload !== null ? payload as Record<string, unknown> : null
    const rawDetail = payloadObject?.detail ?? payloadObject
    const detail = typeof rawDetail === 'object' && rawDetail !== null && 'message' in rawDetail
      ? String((rawDetail as { message?: unknown }).message || (rawDetail as { error_code?: unknown }).error_code || `RAG Hub request failed (HTTP ${response.status})`)
      : typeof rawDetail === 'string' ? rawDetail : `RAG Hub request failed (HTTP ${response.status})`
    throw new RagApiError(response.status, detail)
  }
  return payload as T
}

export const ragApi = {
  health: () => request<{ status: string; database: string; adapter: string }>('/health'),

  dashboardSummary: () => request<{ knowledge: DashboardSummary['knowledge']; risks: DashboardSummary['risks'] }>('/api/v1/dashboard-summary'),

  listRecords: (params: Record<string, string | number | undefined> = {}, signal?: AbortSignal) => {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== '') query.set(key, String(value))
    }
    return request<RecordsResponse>(`/api/v1/records${query.size ? `?${query}` : ''}`, { signal })
  },

  getRecord: (recordId: string, signal?: AbortSignal) =>
    request<{ record: RagRecord }>(`/api/v1/records/${encodeURIComponent(recordId)}`, { signal }),

  listRisks: (status?: 'open' | 'recovered', signal?: AbortSignal) =>
    request<{ items: RiskItem[]; total: number }>(`/api/v1/risks${status ? `?status=${status}` : ''}`, { signal }),

  getRisk: (riskId: string, signal?: AbortSignal) =>
    request<{ risk: RiskDetail }>(`/api/v1/risks/${encodeURIComponent(riskId)}`, { signal }),

  startRiskInvestigation: (riskId: string, requestKey: string) =>
    request<{ run_id: string; status: string; object_version: number }>('/api/v1/agent/risk-investigations', {
      method: 'POST', body: JSON.stringify({ risk_object_id: riskId, request_key: requestKey }),
    }),

  getRiskInvestigation: (runId: string, signal?: AbortSignal) =>
    request<{ run: RiskInvestigationRun }>(`/api/v1/agent/risk-investigations/${encodeURIComponent(runId)}`, { signal }),

  decideRiskInvestigation: (runId: string, body: {
    decision: 'approve' | 'reject'
    expected_object_version: number
    reason?: string
    tasks?: RiskInvestigationTask[]
  }) => request<{ run: RiskInvestigationRun }>(`/api/v1/agent/risk-investigations/${encodeURIComponent(runId)}/decision`, {
    method: 'POST', body: JSON.stringify(body),
  }),

  query: (question: string, scope: DomainScope, signal?: AbortSignal) => {
    const domains = scope === 'auto' ? ['c', 'b', 'kol'] : [scope]
    return request<QueryResponse>('/api/v1/query', {
      method: 'POST',
      body: JSON.stringify({ query: question, domains }),
      signal,
    })
  },

  syncSummary: () => request<SyncSummaryResponse>('/api/v1/maintenance/sync-summary'),

  syncTasks: (signal?: AbortSignal) =>
    request<{ items: Array<Record<string, unknown>>; total: number }>('/api/v1/maintenance/sync-tasks?page=1&page_size=50', { signal }),

  processPending: () => request<Record<string, unknown>>('/api/v1/maintenance/sync-tasks/process-pending', {
    method: 'POST',
    body: JSON.stringify({ operator: 'rag-frontend-v2-background' }),
  }),

  addAnnotation: (recordId: string, annotationType: 'public_note' | 'private_note' | 'correction_feedback', content: string) =>
    request(`/api/v1/records/${encodeURIComponent(recordId)}/annotations`, {
      method: 'POST',
      body: JSON.stringify({ annotation_type: annotationType, content, author: 'rag-frontend-v2' }),
    }),
}

export function decodePayload(record: RagRecord): Record<string, unknown> {
  if (typeof record.payload_json === 'object' && record.payload_json !== null) return record.payload_json
  if (typeof record.payload_json === 'string') {
    try {
      const parsed = JSON.parse(record.payload_json)
      if (typeof parsed === 'object' && parsed !== null) return parsed as Record<string, unknown>
    } catch {
      // Keep the retrieval text as the safe fallback below.
    }
  }
  return {}
}

function valueAsText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(valueAsText).filter(Boolean).join(', ')
  if (typeof value === 'object') return ''
  return String(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function payloadResult(record: RagRecord): Record<string, unknown> {
  const result = decodePayload(record).result
  if (isRecord(result)) return result
  if (typeof result === 'string') {
    try {
      const parsed: unknown = JSON.parse(result)
      return isRecord(parsed) ? parsed : {}
    } catch {
      return {}
    }
  }
  return {}
}

const C_FEEDBACK_RECORD_TYPES = new Set([
  'consumer_journey_sentiment',
  'consumer_nps_prediction',
  'consumer_key_complaints',
  'consumer_brand_attitude',
])
const C_RISK_RECORD_TYPES = new Set(['consumer_recall_risk', 'consumer_legal_risk'])

function isTrue(value: unknown): boolean {
  return value === true || value === 'true' || value === 1
}

export function recordRiskState(record: RagRecord): RiskState {
  if (record.risk_state === 'none' || record.risk_state === 'normal' || record.risk_state === 'alert') return record.risk_state
  if (record.source_system === 'C' && C_RISK_RECORD_TYPES.has(record.record_type)) {
    return isTrue(payloadResult(record).threshold_exceeded) ? 'alert' : 'normal'
  }
  return 'none'
}

export function recordDisplayCategory(record: RagRecord): DisplayCategory {
  if (record.display_category && ['feedback', 'risk_assessment', 'risk_alert', 'policy', 'project', 'kol_trend'].includes(record.display_category)) {
    return record.display_category as DisplayCategory
  }
  if (record.source_system === 'C') {
    if (C_RISK_RECORD_TYPES.has(record.record_type)) return recordRiskState(record) === 'alert' ? 'risk_alert' : 'risk_assessment'
    if (C_FEEDBACK_RECORD_TYPES.has(record.record_type)) return 'feedback'
    return 'project'
  }
  if (record.source_system === 'B') return record.record_type === 'business_policy' ? 'policy' : 'project'
  if (record.source_system === 'KOL') return 'kol_trend'
  return 'project'
}

export function recordDomain(record: RagRecord): RecordDomain {
  return record.source_system === 'C' ? 'C' : record.source_system === 'B' ? 'B' : 'K'
}

export function recordTitle(record: RagRecord): string {
  const payload = decodePayload(record)
  const explicit = ['title', 'name', 'display_name', 'project_name', 'entry_title']
    .map(key => valueAsText(payload[key]))
    .find(Boolean)
  if (explicit) return explicit
  const parts = ['dimension', 'entry_type', 'brand', 'vehicle_model', 'region']
    .map(key => valueAsText(payload[key]))
    .filter(Boolean)
  return parts.length ? parts.join(' · ') : `${record.source_system} · ${record.record_type}`
}

export function recordSummary(record: RagRecord): string {
  if (typeof record.display_summary === 'string' && record.display_summary.trim()) return record.display_summary.trim()
  const payload = decodePayload(record)
  const result = payloadResult(record)
  const explicit = ['summary', 'conclusion', 'published_summary', 'business_impact', 'recommended_action', 'cooperation_conclusion', 'review_conclusion']
    .map(key => valueAsText(payload[key]))
    .find(Boolean)
  if (explicit) return explicit

  // Compatibility for older responses without display_summary. Only known
  // scalar fields are rendered; an object such as journey_curve is never
  // serialized into a list or detail-page summary.
  const scalar = (value: unknown): string => valueAsText(value)
  if (record.record_type === 'consumer_journey_sentiment') {
  const parts = [scalar(payload.journey_stage), scalar(payload.signal_count) ? `${scalar(payload.signal_count)} feedback items` : '', scalar(result.trend_direction) ? `Trend: ${scalar(result.trend_direction)}` : ''].filter(Boolean)
  return parts.length ? parts.join('; ') : 'No summary available.'
  }
  if (record.record_type === 'consumer_nps_prediction') {
  const parts = [result.nps_value !== undefined ? `NPS forecast: ${scalar(result.nps_value)}` : '', result.change_from_previous !== undefined ? `Change from previous period: ${scalar(result.change_from_previous)}` : ''].filter(Boolean)
  return parts.length ? parts.join('; ') : 'No summary available.'
  }
  if (record.record_type === 'consumer_key_complaints') {
    const complaints = Array.isArray(result.complaints) ? result.complaints.filter(isRecord).slice(0, 3) : []
    const topics = complaints.map(item => scalar(item.part) || scalar(item.topic_name)).filter(Boolean)
  return topics.length ? `Key complaints: ${topics.join(', ')}` : 'No summary available.'
  }
  if (record.record_type === 'consumer_brand_attitude') {
    const attitude = scalar(result.attitude)
  return attitude ? `Current brand sentiment: ${attitude}` : 'No summary available.'
  }
  if (record.source_system === 'C' && C_RISK_RECORD_TYPES.has(record.record_type)) {
    const subject = scalar(result.part) || scalar(result.risk_type)
  const state = recordRiskState(record) === 'alert' ? 'Risk alert triggered' : 'Risk assessment is normal'
  return subject ? `${subject}: ${state}` : state
  }
  const fallback = ['attitude', 'trend_direction', 'risk_status', 'title', 'name']
    .map(key => scalar(payload[key]) || scalar(result[key]))
    .find(Boolean)
  return fallback || 'No summary available.'
}

export function recordTime(record: RagRecord): string {
  return record.business_date || record.source_updated_at || record.effective_at || record.updated_at
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return value
  return date.toLocaleString('en-US', { hour12: false })
}

export function syncStatus(item?: SyncSummaryItem): 'ok' | 'syncing' | 'error' {
  if (!item) return 'ok'
  if (item.failed > 0 || item.timed_out > 0) return 'error'
  if (item.pending > 0 || item.processing > 0) return 'syncing'
  return 'ok'
}
