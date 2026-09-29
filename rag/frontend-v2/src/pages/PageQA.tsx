import { useEffect, useRef, useState } from 'react'
import {
  Badge,
  BtnOutline,
  BtnPrimary,
  Card,
  CardBody,
  CardHead,
  CardTitle,
  DomainMark,
  Grid3,
  Grid4,
  InfoBox,
  MetricCard,
  SectionNote,
  WarnBox,
} from '../components/ui'
import {
  DashboardSummary,
  DomainScope,
  RagRecord,
  QueryResponse,
  SemanticFieldKey,
  formatDateTime,
  ragApi,
  recordDomain,
  recordSummary,
  recordTime,
  recordTitle,
  semanticFieldInfo,
  semanticStatusLabel,
} from '../lib/api'
import { downloadBriefHtml } from '../lib/briefHtml'

type QAState = 'idle' | 'loading' | 'success' | 'no_evidence' | 'clarification' | 'error'

const QUICK_QUESTIONS = [
  'Which client projects may be affected by rising battery complaints?',
  'How do recent regulatory changes in Germany affect procurement projects?',
  'Which creator partnerships should be paused?',
  'What is the overall consumer sentiment in Europe?',
]

const SCOPE_OPTIONS: { value: DomainScope; label: string }[] = [
  { value: 'auto', label: 'Detect scope automatically' },
  { value: 'c', label: 'Consumer signals' },
  { value: 'b', label: 'B2B business intelligence' },
  { value: 'kol', label: 'Creator partnerships' },
]

const LOAD_STEPS = [
  'Interpreting the question…',
  'Retrieving current knowledge for the selected scope…',
  'Filtering evidence validated by the primary database…',
  'Generating a structured response…',
]

interface EvidenceItem {
  record: RagRecord
  score: number | null
}

interface QueryHistoryItem {
  q: string
  scope: string
  time: string
}

interface PageQAProps {
  showToast: (message: string) => void
  refreshToken?: number
}

function scopeLabel(scope: DomainScope): string {
  return { auto: 'C + B + Creator', c: 'Consumer only', b: 'Business only', kol: 'Creator only' }[scope]
}

function splitActions(value: string | null | undefined): string[] {
  if (!value) return []
  return value.split(/[;\n]/).map(item => item.trim()).filter(Boolean)
}

function outputValue(value: string | null | undefined): string {
  return value?.trim() || 'No validated evidence is available for the selected scope.'
}

function semanticValue(result: QueryResponse, field: SemanticFieldKey, value: string | null): string {
  const info = semanticFieldInfo(result, field)
  return info.source === 'none' ? info.notice || outputValue(value) : outputValue(value)
}

function semanticBadge(result: QueryResponse, field: SemanticFieldKey): { text: string; color: 'green' | 'amber' | 'gray' } {
  const source = semanticFieldInfo(result, field).source
  if (source === 'maxkb') return { text: 'LLM summary', color: 'green' }
  if (source === 'deterministic') return { text: 'Evidence-based fallback', color: 'amber' }
  return { text: 'No domain-specific evidence', color: 'gray' }
}

export default function PageQA({ showToast, refreshToken = 0 }: PageQAProps) {
  const [question, setQuestion] = useState('Synthesize the current evidence and summarize key consumer feedback, business compliance impacts, and creator reach and partnership impacts.')
  const [scope, setScope] = useState<DomainScope>('auto')
  const [qaState, setQaState] = useState<QAState>('idle')
  const [loadStep, setLoadStep] = useState(0)
  const [response, setResponse] = useState<QueryResponse | null>(null)
  const [evidence, setEvidence] = useState<EvidenceItem[]>([])
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [history, setHistory] = useState<QueryHistoryItem[]>([])
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [currentRecords, setCurrentRecords] = useState<RagRecord[]>([])
  const requestSequence = useRef(0)
  const activeRequest = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([
      ragApi.dashboardSummary(),
      ragApi.listRecords({ status: 'active', record_mode: 'current', page: 1, page_size: 200 }, controller.signal),
    ]).then(([dashboard, records]) => {
      setSummary(dashboard)
      setCurrentRecords(records.items)
    }).catch(() => {
      // The query page reports the actionable error when the user submits a question.
    })
    return () => controller.abort()
  }, [refreshToken])

  useEffect(() => () => activeRequest.current?.abort(), [])

  async function startAnalysis() {
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion) {
      showToast('Enter a business question first')
      return
    }

    const sequence = ++requestSequence.current
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    setQaState('loading')
    setLoadStep(1)
    setResponse(null)
    setEvidence([])
    setSelectedEvidence(null)
    setErrorMessage('')

    try {
      const result = await ragApi.query(trimmedQuestion, scope, controller.signal)
      if (sequence !== requestSequence.current) return
      setLoadStep(2)
      const references = result.output?.evidence || []
      const details = await Promise.allSettled(
        references.slice(0, 12).map(reference => ragApi.getRecord(reference.record_id, controller.signal)),
      )
      if (sequence !== requestSequence.current) return
      setEvidence(details.flatMap((item, index) => item.status === 'fulfilled'
        ? [{ record: item.value.record, score: references[index]?.score ?? null }]
        : []))
      setLoadStep(LOAD_STEPS.length)
      setResponse(result)
      const status = result.query_meta?.generation_status
      setQaState(status === 'clarification' ? 'clarification' : status === 'no_evidence' ? 'no_evidence' : 'success')
      setHistory(items => [
        { q: trimmedQuestion, scope: scopeLabel(scope), time: 'Just now' },
        ...items.filter(item => item.q !== trimmedQuestion).slice(0, 19),
      ])
      showToast(semanticStatusLabel(result))
    } catch (error) {
      if (controller.signal.aborted || sequence !== requestSequence.current) return
      setQaState('error')
      setErrorMessage(error instanceof Error ? error.message : 'RAG Hub Request failed')
      showToast('Query failed. Please try again later.')
    } finally {
      if (sequence === requestSequence.current) activeRequest.current = null
    }
  }

  function exportBrief() {
    if (!response) return
    downloadBriefHtml(response, evidence)
    showToast('HTML brief downloaded')
  }

  const cCount = currentRecords.filter(record => recordDomain(record) === 'C').length
  const bCount = currentRecords.filter(record => recordDomain(record) === 'B').length
  const kCount = currentRecords.filter(record => recordDomain(record) === 'K').length
  const output = response?.output
  const actions = splitActions(output?.action_recommendations)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px 40px' }}>
      <Grid4>
      <MetricCard label="Consumer Knowledge Records" value={summary ? cCount : '—'} sub="Active records" iconBg="#ECFDF5" iconColor="#059669" iconText="C" />
      <MetricCard label="Business Intelligence" value={summary ? bCount : '—'} sub="Active records" iconBg="#EFF6FF" iconColor="#2563EB" iconText="B" />
      <MetricCard label="Creator Intelligence" value={summary ? kCount : '—'} sub="Active records" iconBg="#F5F0FF" iconColor="#7C3AED" iconText="K" />
      <MetricCard label="Active Alerts" value={summary ? summary.risks.active : '—'} sub="Reported by the consumer risk service" iconBg="#FEF2F2" iconColor="#DC2626" iconText="⚠" />
      </Grid4>

      <InfoBox>
      <strong>About this feature:</strong> Enter a business question to search the production RAG Hub for consumer signals, B2B intelligence, and creator partnership information. Response status, evidence, and fallback reasons come from the API; this page does not use demo data.
      </InfoBox>

      <Card>
    <CardHead><CardTitle icon="✦">Cross-Domain Questions</CardTitle><SectionNote>Select a scope, then choose Analyze.</SectionNote></CardHead>
        <CardBody>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              value={question}
              onChange={event => setQuestion(event.target.value)}
              onKeyDown={event => { if (event.key === 'Enter') void startAnalysis() }}
    placeholder="Enter a business question, e.g. Which projects may be affected by rising battery complaints?"
              style={{ flex: 1, height: 38, border: '0.5px solid #CBD5E1', borderRadius: 6, padding: '0 12px', fontSize: 12, outline: 'none' }}
            />
            <select value={scope} onChange={event => setScope(event.target.value as DomainScope)}
              style={{ fontSize: 11, padding: '6px 8px', border: '0.5px solid var(--border)', borderRadius: 5, background: '#fff', height: 38 }}>
              {SCOPE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <BtnPrimary onClick={() => void startAnalysis()} disabled={qaState === 'loading'}>
              {qaState === 'loading' ? 'Analyzing…' : '⊞ Analyze'}
            </BtnPrimary>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            {QUICK_QUESTIONS.map(item => (
              <button key={item} onClick={() => setQuestion(item)}
                style={{ fontSize: 10, color: '#4B5563', border: '0.5px solid var(--border)', background: '#F8FAFC', borderRadius: 14, padding: '4px 9px', cursor: 'pointer' }}>
                {item}
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      {qaState === 'loading' && (
        <Card>
          <CardHead><CardTitle icon="◎">Analyzing</CardTitle></CardHead>
          <CardBody>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {LOAD_STEPS.map((step, index) => (
                <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 18, height: 18, borderRadius: '50%', flexShrink: 0, background: index < loadStep ? '#059669' : index === loadStep ? '#2563EB' : '#E2E8F0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, color: index <= loadStep ? '#fff' : '#6B7280' }}>
                    {index < loadStep ? '✓' : index + 1}
                  </div>
                  <span style={{ fontSize: 11, color: index < loadStep ? '#059669' : index === loadStep ? '#1D4ED8' : '#9CA3AF' }}>{step}</span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {(qaState === 'no_evidence' || qaState === 'clarification') && (
        <Card>
    <CardHead><CardTitle icon="○">{qaState === 'clarification' ? 'More Query Details Needed' : 'No Valid Evidence Found'}</CardTitle></CardHead>
          <CardBody>
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                {response?.clarification?.question || response?.output.summary || 'No evidence supporting an answer was found in the current knowledge base.'}
              </div>
              <div style={{ fontSize: 11, color: '#6B7280', lineHeight: 1.7 }}>
    Search completed for {response ? response.selected_targets.join(', ') : 'the selected scope'}. Add an entity, clarify the question, or expand the query scope.
              </div>
              <div style={{ marginTop: 14 }}>
                <BtnOutline onClick={() => setScope('auto')}>Expand to all domains</BtnOutline>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {qaState === 'error' && (
        <Card>
          <CardHead><CardTitle icon="✕">System Error</CardTitle><Badge text="Service unavailable" color="red" /></CardHead>
          <CardBody>
            <div style={{ background: '#FEF2F2', border: '0.5px solid rgba(185,28,28,0.2)', borderRadius: 7, padding: 14, color: '#7F1D1D', fontSize: 11, lineHeight: 1.7 }}>
              <strong style={{ display: 'block', marginBottom: 4 }}>RAG Hub Request failed</strong>
    {errorMessage || 'Check the RAG Hub, MaxKB, and local proxy status.'}
            </div>
            <div style={{ marginTop: 12 }}><BtnPrimary onClick={() => setQaState('idle')}>Try Again</BtnPrimary></div>
          </CardBody>
        </Card>
      )}

      {qaState === 'success' && response && output && (
        <div>
          <Card>
            <CardHead>
              <CardTitle icon="◎">RAG Integrated Answer</CardTitle>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <Badge text={semanticStatusLabel(response)} color={response.query_meta.generation_status === 'degraded' ? 'amber' : 'green'} />
    <BtnOutline onClick={exportBrief}>Export HTML Brief</BtnOutline>
              </div>
            </CardHead>
            <CardBody>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <div style={{ width: 38, height: 38, borderRadius: 8, background: '#EFF6FF', color: '#2563EB', display: 'grid', placeItems: 'center', fontSize: 17, flexShrink: 0 }}>✦</div>
                <div style={{ flex: 1 }}>
                  <h3 style={{ fontSize: 14, margin: '0 0 6px', color: '#111827' }}>{outputValue(output.summary)}</h3>
                  <p style={{ fontSize: 10, color: '#6B7280', lineHeight: 1.7, margin: 0 }}>
          {semanticStatusLabel(response)} · {response.evidence_count} evidence items · {response.query_meta.total_ms} ms
          {response.query_meta.degraded_reason ? ` · Reason: ${response.query_meta.degraded_reason}` : ''}
                  </p>
                </div>
                <span style={{ fontSize: 10, color: '#047857', background: '#ECFDF5', border: '0.5px solid rgba(4,120,87,0.25)', borderRadius: 15, padding: '3px 8px', whiteSpace: 'nowrap' }}>
                  {formatDateTime(new Date().toISOString())}
                </span>
              </div>
            </CardBody>
          </Card>

          <Grid3>
            {([
              { domain: 'C' as const, field: 'consumer_signal' as const, title: 'Consumer signals', value: output.consumer_signal },
              { domain: 'B' as const, field: 'business_impact' as const, title: 'Business impact', value: output.business_impact },
              { domain: 'K' as const, field: 'kol_impact' as const, title: 'Creator impact', value: output.kol_impact },
            ]).map(item => {
              const badge = semanticBadge(response, item.field)
              return (
                <div key={item.domain} style={{ background: '#fff', border: '0.5px solid var(--border)', borderRadius: 9, padding: 13 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 10 }}>
                    <DomainMark domain={item.domain} />
                    <strong style={{ fontSize: 11 }}>{item.title}</strong>
                    <Badge text={badge.text} color={badge.color} />
                  </div>
                  <div style={{ fontSize: 10, color: '#4B5563', lineHeight: 1.7 }}>{semanticValue(response, item.field, item.value)}</div>
                </div>
              )
            })}
          </Grid3>

          <Card>
    <CardHead><CardTitle icon="✓">Action Recommendations</CardTitle><SectionNote>Displays API results without adding frontend-generated content.</SectionNote></CardHead>
            <CardBody>
              {actions.length ? actions.map((action, index) => (
                <div key={action} style={{ display: 'flex', gap: 9, alignItems: 'flex-start', padding: '8px 0', borderBottom: index < actions.length - 1 ? '0.5px solid #F1F5F9' : 0 }}>
    <Badge text={`Recommendation ${index + 1}`} color="gray" />
                  <span style={{ fontSize: 11, color: '#374151', lineHeight: 1.6 }}>{action}</span>
                </div>
    )) : <InfoBox>No action recommendations are available.</InfoBox>}
            </CardBody>
          </Card>

          <Card>
    <CardHead><CardTitle icon="▤">Key Evidence</CardTitle><SectionNote>Select an item to view the source record.</SectionNote></CardHead>
            <CardBody style={{ padding: '4px 14px' }}>
              {evidence.length ? evidence.map(item => (
                <button key={item.record.id} onClick={() => setSelectedEvidence(item)}
                  style={{ width: '100%', display: 'flex', gap: 9, alignItems: 'flex-start', padding: '9px 0', border: 0, borderBottom: '0.5px solid #F1F5F9', background: '#fff', textAlign: 'left', cursor: 'pointer' }}>
                  <DomainMark domain={recordDomain(item.record)} />
                  <span style={{ flex: 1 }}>
                    <strong style={{ display: 'block', fontSize: 11, color: '#111827' }}>{recordTitle(item.record)}</strong>
                    <span style={{ display: 'block', fontSize: 9, color: '#6B7280', marginTop: 2, lineHeight: 1.5 }}>{recordSummary(item.record)}</span>
                    <span style={{ display: 'block', fontSize: 9, color: '#94A3B8', marginTop: 3 }}>{formatDateTime(recordTime(item.record))} · {item.record.target_knowledge_base}</span>
                  </span>
    {item.score !== null && <Badge text={`Relevance ${item.score.toFixed(2)}`} color="blue" />}
                </button>
    )) : <InfoBox>The API returned evidence references, but the details are temporarily unavailable.</InfoBox>}
            </CardBody>
          </Card>

          {selectedEvidence && (
            <Card>
              <CardHead>
                <CardTitle icon="◎">Evidence Details</CardTitle>
    <BtnOutline onClick={() => setSelectedEvidence(null)}>Close</BtnOutline>
              </CardHead>
              <CardBody>
                <strong style={{ display: 'block', fontSize: 12, marginBottom: 7 }}>{recordTitle(selectedEvidence.record)}</strong>
                <div style={{ fontSize: 11, color: '#374151', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{selectedEvidence.record.retrieval_text}</div>
                {selectedEvidence.record.source_url && <a href={selectedEvidence.record.source_url} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 10, fontSize: 10, color: '#2563EB' }}>Open source</a>}
              </CardBody>
            </Card>
          )}

          <WarnBox>
    <strong>Limitations:</strong> {output.limitations || 'This response is based only on active knowledge. It does not replace quality assessment, legal judgment, or formal business decisions.'}
          </WarnBox>
        </div>
      )}

      {history.length > 0 && (
        <Card>
    <CardHead><CardTitle icon="↺">Recent Queries</CardTitle><SectionNote>Saved for this page session only.</SectionNote></CardHead>
          <CardBody style={{ padding: '4px 14px' }}>
            {history.map((item, index) => (
    <button key={`${item.q}-${index}`} onClick={() => { setQuestion(item.q); setScope(item.scope === 'Consumer only' ? 'c' : item.scope === 'Business only' ? 'b' : item.scope === 'Creator only' ? 'kol' : 'auto') }}
                style={{ width: '100%', display: 'flex', gap: 8, padding: '8px 0', border: 0, borderBottom: '0.5px solid #F1F5F9', background: '#fff', textAlign: 'left', cursor: 'pointer', fontSize: 10, color: '#4B5563' }}>
                <span style={{ flex: 1 }}>{item.q}</span><Badge text={item.scope} color="gray" /><span style={{ color: '#9CA3AF' }}>{item.time}</span>
              </button>
            ))}
          </CardBody>
        </Card>
      )}
    </div>
  )
}
