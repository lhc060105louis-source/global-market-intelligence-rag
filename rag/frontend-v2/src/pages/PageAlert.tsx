import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Badge,
  BtnOutline,
  BtnPrimary,
  Card,
  CardBody,
  CardHead,
  CardTitle,
  DomainMark,
  Grid4,
  InfoBox,
  MetricCard,
  SectionNote,
  WarnBox,
} from '../components/ui'
import {
  RagRecord,
  QueryResponse,
  RiskDetail,
  RiskInvestigationRun,
  RiskInvestigationTask,
  RiskItem,
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

interface AlertEvidence {
  record: RagRecord
  score: number | null
}

interface PageAlertProps {
  showToast: (message: string) => void
  refreshToken?: number
}

function riskTitle(risk: RiskItem): string {
  return [risk.brand, risk.vehicle_model, risk.part, risk.region, risk.risk_type].filter(Boolean).join(' · ') || 'Unnamed risk subject'
}

function riskQuestion(risk: RiskItem): string {
  return `How might the consumer risk event for ${riskTitle(risk)} affect business projects and creator partnerships?`
}

function semanticCardValue(result: QueryResponse, field: SemanticFieldKey, value: string | null): string {
  const info = semanticFieldInfo(result, field)
  return info.source === 'none' ? info.notice || 'No evidence is available for this domain.' : value || 'No summary returned'
}

function semanticCardBadge(result: QueryResponse, field: SemanticFieldKey): { text: string; color: 'green' | 'amber' | 'gray' } {
  const source = semanticFieldInfo(result, field).source
  if (source === 'maxkb') return { text: 'LLM summary', color: 'green' }
  if (source === 'deterministic') return { text: 'Evidence-based fallback', color: 'amber' }
  return { text: 'No domain-specific evidence', color: 'gray' }
}

export default function PageAlert({ showToast, refreshToken = 0 }: PageAlertProps) {
  const [risks, setRisks] = useState<RiskItem[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState<RiskDetail | null>(null)
  const [ragResponse, setRagResponse] = useState<QueryResponse | null>(null)
  const [ragEvidence, setRagEvidence] = useState<AlertEvidence[]>([])
  const [investigationRun, setInvestigationRun] = useState<RiskInvestigationRun | null>(null)
  const [investigationStarting, setInvestigationStarting] = useState(false)
  const [investigationTasks, setInvestigationTasks] = useState<RiskInvestigationTask[]>([])
  const [rejectionReason, setRejectionReason] = useState('')
  const [decisionBusy, setDecisionBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [ragLoading, setRagLoading] = useState(false)
  const [error, setError] = useState('')
  const ragRequestSequence = useRef(0)
  const activeRagRequest = useRef<AbortController | null>(null)
  const selectedIdRef = useRef(selectedId)
  selectedIdRef.current = selectedId

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void ragApi.listRisks(undefined, controller.signal)
      .then(result => {
        setRisks(result.items)
        setSelectedId(current => current && result.items.some(item => item.id === current) ? current : result.items[0]?.id || '')
      })
      .catch(errorValue => {
    if (!controller.signal.aborted) setError(errorValue instanceof Error ? errorValue.message : 'Failed to load alerts')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [refreshToken])

  useEffect(() => {
    ragRequestSequence.current += 1
    activeRagRequest.current?.abort()
    activeRagRequest.current = null
    setRagResponse(null)
    setRagEvidence([])
    setRagLoading(false)
  }, [selectedId])

  useEffect(() => {
    setInvestigationRun(null)
    setInvestigationTasks([])
    setRejectionReason('')
  }, [selectedId])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    const savedRunId = sessionStorage.getItem(`risk-investigation:${selectedId}`)
    if (savedRunId) {
      void ragApi.getRiskInvestigation(savedRunId, controller.signal)
        .then(result => {
          if (controller.signal.aborted) return
          setInvestigationRun(result.run)
          if (result.run.draft) setInvestigationTasks(result.run.draft.tasks)
        })
        .catch(() => {
          if (!controller.signal.aborted) sessionStorage.removeItem(`risk-investigation:${selectedId}`)
        })
    }
    return () => controller.abort()
  }, [selectedId])

  useEffect(() => {
    if (!investigationRun || !['queued', 'running'].includes(investigationRun.status)) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    const refresh = async () => {
      try {
        const result = await ragApi.getRiskInvestigation(investigationRun.id, controller.signal)
        if (controller.signal.aborted || selectedIdRef.current !== investigationRun.risk_object_id) return
        setInvestigationRun(result.run)
        if (result.run.draft) setInvestigationTasks(result.run.draft.tasks)
        if (['queued', 'running'].includes(result.run.status)) timer = setTimeout(() => void refresh(), 1000)
      } catch (errorValue) {
        if (!controller.signal.aborted) {
          showToast(errorValue instanceof Error ? errorValue.message : 'Could not refresh the investigation')
          timer = setTimeout(() => void refresh(), 2000)
        }
      }
    }
    timer = setTimeout(() => void refresh(), 1000)
    return () => {
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [investigationRun?.id, investigationRun?.status, showToast])

  useEffect(() => () => activeRagRequest.current?.abort(), [])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    const controller = new AbortController()
    setDetailLoading(true)
    void ragApi.getRisk(selectedId, controller.signal)
      .then(result => setDetail(result.risk))
      .catch(errorValue => {
    if (!controller.signal.aborted) setError(errorValue instanceof Error ? errorValue.message : 'Failed to load alert details')
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false)
      })
    return () => controller.abort()
  }, [selectedId])

  const selected = risks.find(risk => risk.id === selectedId) || risks[0]
  const activeCount = risks.filter(risk => risk.open_episode_id).length
  const recoveredCount = risks.length - activeCount
  const selectedEpisode = detail?.open_episode
  const trend = selectedEpisode?.trend_points || []

  const timeRange = useMemo(() => {
    if (!trend.length) return 'No trend data'
    return `${formatDateTime(trend[0].business_time)} — ${formatDateTime(trend[trend.length - 1].business_time)}`
  }, [trend])

  async function loadRag() {
    if (!selected) return
    const sequence = ++ragRequestSequence.current
    activeRagRequest.current?.abort()
    const controller = new AbortController()
    activeRagRequest.current = controller
    setRagLoading(true)
    setRagResponse(null)
    setRagEvidence([])
    try {
      const result = await ragApi.query(riskQuestion(selected), 'auto', controller.signal)
      if (sequence !== ragRequestSequence.current) return
      setRagResponse(result)
      const references = result.output?.evidence || []
      const details = await Promise.allSettled(references.slice(0, 12).map(reference => ragApi.getRecord(reference.record_id, controller.signal)))
      if (sequence !== ragRequestSequence.current) return
      setRagEvidence(details.flatMap((item, index) => item.status === 'fulfilled'
        ? [{ record: item.value.record, score: references[index]?.score ?? null }]
        : []))
    showToast('Loaded related information from the RAG Hub')
    } catch (errorValue) {
      if (controller.signal.aborted || sequence !== ragRequestSequence.current) return
    showToast(errorValue instanceof Error ? errorValue.message : 'Cross-domain query failed')
    } finally {
      if (sequence === ragRequestSequence.current) {
        activeRagRequest.current = null
        setRagLoading(false)
      }
    }
  }

  async function startInvestigation() {
    if (!selected || investigationStarting) return
    const riskId = selected.id
    setInvestigationStarting(true)
    try {
      const requestKey = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
      const result = await ragApi.startRiskInvestigation(riskId, requestKey)
      sessionStorage.setItem(`risk-investigation:${riskId}`, result.run_id)
      const refreshed = await ragApi.getRiskInvestigation(result.run_id)
      if (selectedIdRef.current !== riskId) return
      setInvestigationRun(refreshed.run)
      showToast('Investigation started')
    } catch (errorValue) {
      showToast(errorValue instanceof Error ? errorValue.message : 'Could not start the investigation')
    } finally {
      setInvestigationStarting(false)
    }
  }

  async function decideInvestigation(decision: 'approve' | 'reject') {
    if (!investigationRun || decisionBusy) return
    const riskId = investigationRun.risk_object_id
    const runId = investigationRun.id
    if (decision === 'reject' && !rejectionReason.trim()) {
      showToast('Add a short reason before rejecting this proposal')
      return
    }
    setDecisionBusy(true)
    try {
      await ragApi.decideRiskInvestigation(runId, {
        decision,
        expected_object_version: investigationRun.object_version,
        ...(decision === 'reject' ? { reason: rejectionReason.trim() } : { tasks: investigationTasks }),
      })
      const refreshed = await ragApi.getRiskInvestigation(runId)
      if (selectedIdRef.current !== riskId) return
      setInvestigationRun(refreshed.run)
      showToast(refreshed.run.status === 'stale'
        ? 'Evidence changed; start a new investigation before approval'
        : decision === 'approve' ? 'Investigation approved and case created' : 'Investigation proposal rejected')
    } catch (errorValue) {
      showToast(errorValue instanceof Error ? errorValue.message : 'Could not save the decision')
      try {
        const refreshed = await ragApi.getRiskInvestigation(runId)
        if (selectedIdRef.current === riskId) setInvestigationRun(refreshed.run)
      } catch { /* keep the last visible run state */ }
    } finally {
      setDecisionBusy(false)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px 40px' }}>
      <Grid4>
        <MetricCard label="Active Alerts" value={loading ? '—' : activeCount} sub="Reported by the consumer risk service" iconBg="#FEF2F2" iconColor="#DC2626" iconText="⚠" />
        <MetricCard label="Resolved Risks" value={loading ? '—' : recoveredCount} sub="Closed by upstream recovery events" iconBg="#ECFDF5" iconColor="#059669" iconText="✓" />
        <MetricCard label="Trend Points" value={selectedEpisode?.trend_points.length ?? '—'} sub="Selected risk" iconBg="#EFF6FF" iconColor="#2563EB" iconText="↗" />
        <MetricCard label="Cross-domain Queries" value={ragResponse ? ragResponse.evidence_count : '—'} sub="Evidence retrieved on demand" iconBg="#F5F0FF" iconColor="#7C3AED" iconText="◎" />
      </Grid4>

      {error && <WarnBox><strong>Alert API error:</strong> {error}</WarnBox>}
      {loading && <InfoBox>Loading current consumer risk events…</InfoBox>}
      {!loading && risks.length === 0 && <InfoBox>There are no production alerts above the threshold. View normal risk assessments in Knowledge Search. Alerts are generated by the consumer service; the RAG Hub does not create or modify them.</InfoBox>}

      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 12 }}>
        <Card style={{ marginBottom: 0 }}>
        <CardHead><CardTitle icon="⚠">Alert List</CardTitle><Badge text={`${risks.length}`} color={risks.length ? 'red' : 'gray'} /></CardHead>
          <CardBody style={{ padding: 8 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {risks.map(risk => (
                <button key={risk.id} onClick={() => setSelectedId(risk.id)}
                  style={{ display: 'flex', alignItems: 'flex-start', gap: 10, border: `0.5px solid ${selected?.id === risk.id ? '#93C5FD' : 'var(--border)'}`, background: selected?.id === risk.id ? '#F8FBFF' : '#fff', borderRadius: 8, padding: 11, textAlign: 'left', cursor: 'pointer', boxShadow: selected?.id === risk.id ? 'inset 2px 0 0 #2563EB' : 'none', width: '100%' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', gap: 5, marginBottom: 3 }}><Badge text={risk.open_episode_id ? 'Active' : 'Resolved'} color={risk.open_episode_id ? 'red' : 'green'} /></div>
                    <strong style={{ fontSize: 11, color: '#111827', display: 'block', marginBottom: 3 }}>{riskTitle(risk)}</strong>
                    <p style={{ fontSize: 9, color: '#6B7280', margin: 0 }}>{risk.risk_type || 'Unspecified risk type'}</p>
                  </div>
                </button>
              ))}
            </div>
          </CardBody>
        </Card>

        <div>
          {selected ? (
            <>
              <Card>
                <CardHead>
                  <CardTitle icon="◎">Alert Details</CardTitle>
                  <Badge text={selected.open_episode_id ? 'Active' : 'Resolved'} color={selected.open_episode_id ? 'red' : 'green'} />
                </CardHead>
                <CardBody>
                  <h3 style={{ fontSize: 14, margin: '0 0 10px', color: '#111827' }}>{riskTitle(selected)}</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 12 }}>
                    {[
                      ['brand', detail?.brand || selected.brand || 'Unspecified'],
                      ['vehicle model', detail?.vehicle_model || selected.vehicle_model || 'Unspecified'],
                      ['region / component', [detail?.region || selected.region, detail?.part || selected.part].filter(Boolean).join(' · ') || 'Unspecified'],
                    ].map(([label, value]) => (
                      <div key={label} style={{ background: '#F8FAFC', borderRadius: 6, padding: '9px 10px' }}><div style={{ fontSize: 9, color: '#6B7280', marginBottom: 3 }}>{label}</div><div style={{ fontSize: 11, fontWeight: 600 }}>{value}</div></div>
                    ))}
                  </div>
                  {detailLoading ? <InfoBox>Loading risk details…</InfoBox> : (
                    <div style={{ fontSize: 11, color: '#374151', lineHeight: 1.7 }}>
                      <div>riskType: {detail?.risk_type || selected.risk_type || 'Unspecified'}</div>
                      <div>Event status: {selectedEpisode?.status || (selected.open_episode_id ? 'open' : 'Resolved')}</div>
                      <div>Trend time: {timeRange}</div>
                      {selectedEpisode && <div>Current value / threshold: {selectedEpisode.current_value ?? '—'} / {selectedEpisode.threshold ?? '—'}</div>}
                    </div>
                  )}
                </CardBody>
              </Card>

              <Card>
                <CardHead>
                  <CardTitle icon="✦">Risk Investigation Agent</CardTitle>
                  {investigationRun && <Badge text={investigationRun.status.replaceAll('_', ' ')} color={investigationRun.status === 'awaiting_approval' ? 'amber' : investigationRun.status === 'approved' ? 'green' : 'gray'} />}
                </CardHead>
                <CardBody>
                  {!investigationRun && <InfoBox>Investigate this active risk across consumer, business, and creator records. Every proposed case and task requires your approval.</InfoBox>}
                  {investigationRun?.status === 'queued' && <InfoBox>The investigation is queued…</InfoBox>}
                  {investigationRun?.status === 'running' && <InfoBox>Reviewing available evidence…</InfoBox>}
                  {investigationRun?.status === 'needs_clarification' && <WarnBox>The risk subject needs a brand and vehicle model before the Agent can investigate.</WarnBox>}
                  {investigationRun?.status === 'no_evidence' && <WarnBox>No current evidence passed source and version checks. No case or tasks were created.</WarnBox>}
                  {investigationRun?.status === 'failed' && <WarnBox>Investigation stopped ({investigationRun.error_code || 'agent_error'}). No case or tasks were created.</WarnBox>}
                  {investigationRun?.status === 'stale' && <WarnBox>The evidence changed after this draft was created. Start a new investigation.</WarnBox>}
                  {investigationRun?.draft && (
                    <>
                      <div style={{ background: '#F8FAFC', borderRadius: 6, padding: 11, fontSize: 11, lineHeight: 1.7 }}><strong>Investigation brief</strong><p style={{ margin: '5px 0 0' }}>{investigationRun.draft.summary}</p></div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 7, marginTop: 9 }}>
                        {Object.entries(investigationRun.draft.domain_impacts || {}).map(([domain, impact]) => <div key={domain} style={{ border: '0.5px solid var(--border)', borderRadius: 7, padding: 9 }}><strong style={{ fontSize: 10 }}>{domain}</strong><p style={{ fontSize: 9, color: '#6B7280', lineHeight: 1.5, margin: '5px 0 0' }}>{impact}</p></div>)}
                      </div>
                      {investigationRun.draft.evidence.length > 0 && <div style={{ marginTop: 10 }}><strong style={{ fontSize: 10 }}>Verified evidence</strong>{investigationRun.draft.evidence.map(item => <div key={item.record_id} style={{ padding: '7px 0', borderBottom: '0.5px solid #F1F5F9', fontSize: 9 }}><div><DomainMark domain={item.domain.startsWith('c_') ? 'C' : item.domain === 'b_business' ? 'B' : 'K'} /> <strong>{item.title}</strong> · v{item.source_version} · {item.business_date || 'date unavailable'}</div><div style={{ color: '#6B7280', marginTop: 3 }}>{item.preview}</div>{item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">Open source</a>}</div>)}</div>}
                      {(investigationRun.draft.evidence_gaps.length > 0 || investigationRun.draft.limitations.length > 0) && <WarnBox><strong>Evidence gaps:</strong> {investigationRun.draft.evidence_gaps.join(' · ') || 'None stated'}<br /><strong>Limitations:</strong> {investigationRun.draft.limitations.join(' · ') || 'None stated'}</WarnBox>}
                      {investigationRun.tool_trace.length > 0 && <details style={{ marginTop: 8, fontSize: 9, color: '#64748B' }}><summary>Investigation steps ({investigationRun.tool_trace.length})</summary>{investigationRun.tool_trace.map((step, index) => <div key={index} style={{ padding: '4px 0' }}>{String(step.tool || 'read-only tool')}{typeof step.arguments === 'object' && step.arguments !== null && 'target' in step.arguments ? ` · ${String((step.arguments as { target: unknown }).target)}` : ''}</div>)}</details>}
                      <div style={{ marginTop: 10 }}><strong style={{ fontSize: 10 }}>Proposed tasks</strong>{investigationTasks.map((task, index) => <div key={`${index}-${task.task_type}`} style={{ display: 'grid', gridTemplateColumns: '72px 1fr 1fr 1fr', gap: 6, marginTop: 6 }}><select aria-label="Task domain" value={task.owner_domain} onChange={event => setInvestigationTasks(items => items.map((item, itemIndex) => itemIndex === index ? { ...item, owner_domain: event.target.value as RiskInvestigationTask['owner_domain'] } : item))}><option value="C">C</option><option value="B">B</option><option value="KOL">KOL</option></select><input aria-label="Task type" value={task.task_type} onChange={event => setInvestigationTasks(items => items.map((item, itemIndex) => itemIndex === index ? { ...item, task_type: event.target.value } : item))} /><input aria-label="Assignee" placeholder="Assignee" value={task.assignee || ''} onChange={event => setInvestigationTasks(items => items.map((item, itemIndex) => itemIndex === index ? { ...item, assignee: event.target.value } : item))} /><input aria-label="Expected output" value={task.expected_output_type} onChange={event => setInvestigationTasks(items => items.map((item, itemIndex) => itemIndex === index ? { ...item, expected_output_type: event.target.value } : item))} /></div>)}</div>
                    </>
                  )}
                  {investigationRun?.status === 'awaiting_approval' && <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 7 }}><input aria-label="Rejection reason" placeholder="Reason required to reject" value={rejectionReason} onChange={event => setRejectionReason(event.target.value)} /><div style={{ display: 'flex', gap: 8 }}><BtnPrimary onClick={() => void decideInvestigation('approve')} disabled={decisionBusy || !investigationTasks.length}>Approve and create case</BtnPrimary><BtnOutline onClick={() => void decideInvestigation('reject')} disabled={decisionBusy}>Reject proposal</BtnOutline></div></div>}
                  {investigationRun?.status === 'approved' && <InfoBox>Approved. Case ID: {investigationRun.case_id || '—'}</InfoBox>}
                  {investigationRun?.status === 'rejected' && <InfoBox>Proposal rejected. No coordination case or tasks were created.</InfoBox>}
                  {selected.open_episode_id && (!investigationRun || ['failed', 'stale', 'no_evidence', 'needs_clarification', 'rejected'].includes(investigationRun.status)) && <div style={{ marginTop: 10 }}><BtnPrimary onClick={() => void startInvestigation()} disabled={investigationStarting}>{investigationStarting ? 'Starting…' : investigationRun ? 'Start a new investigation' : 'Investigate risk'}</BtnPrimary></div>}
                </CardBody>
              </Card>

              <Card>
      <CardHead><CardTitle icon="◎">RAG Context</CardTitle><SectionNote>Query on demand; alerts are not processed in advance.</SectionNote></CardHead>
                <CardBody>
      {!ragResponse && !ragLoading && <InfoBox><strong>Alert status is managed by the consumer service.</strong> Select the button to search related business and creator knowledge. The RAG Hub does not change alert status.</InfoBox>}
      {ragLoading && <InfoBox>Searching current knowledge…</InfoBox>}
                  {ragResponse && (
                    <>
                      <div style={{ background: '#F8FAFC', borderRadius: 6, padding: 11, fontSize: 11, lineHeight: 1.7, marginBottom: 10 }}>
        <strong>Summary:</strong> {ragResponse.output.summary || 'No summary returned'}
                  <div style={{ fontSize: 9, color: '#6B7280', marginTop: 5 }}>{semanticStatusLabel(ragResponse)} · {ragResponse.evidence_count} evidence items · {ragResponse.query_meta.total_ms} ms</div>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 7, marginBottom: 10 }}>
                        {[
                          { domain: 'C' as const, field: 'consumer_signal' as const, label: 'consumer signals', value: ragResponse.output.consumer_signal },
                          { domain: 'B' as const, field: 'business_impact' as const, label: 'business impact', value: ragResponse.output.business_impact },
                          { domain: 'K' as const, field: 'kol_impact' as const, label: 'creator reach and partnership impact', value: ragResponse.output.kol_impact },
                        ].map(item => {
                          const badge = semanticCardBadge(ragResponse, item.field)
                          return (
                            <div key={item.domain} style={{ border: '0.5px solid var(--border)', borderRadius: 7, padding: 10 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                                <DomainMark domain={item.domain} /><strong style={{ fontSize: 10 }}>{item.label}</strong><Badge text={badge.text} color={badge.color} />
                              </div>
                              <p style={{ fontSize: 9, color: '#6B7280', lineHeight: 1.5, margin: '7px 0 0' }}>{semanticCardValue(ragResponse, item.field, item.value)}</p>
                            </div>
                          )
                        })}
                      </div>
                      {ragEvidence.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                          {ragEvidence.map(item => <div key={item.record.id} style={{ display: 'flex', gap: 8, padding: '7px 0', borderBottom: '0.5px solid #F1F5F9' }}><DomainMark domain={recordDomain(item.record)} /><div style={{ flex: 1 }}><strong style={{ fontSize: 10 }}>{recordTitle(item.record)}</strong><div style={{ fontSize: 9, color: '#6B7280', marginTop: 2 }}>{recordSummary(item.record)}</div><div style={{ fontSize: 9, color: '#94A3B8', marginTop: 2 }}>{formatDateTime(recordTime(item.record))}</div></div></div>)}
                        </div>
                      )}
                    </>
                  )}
      <div style={{ marginTop: 10 }}><BtnPrimary onClick={() => void loadRag()} disabled={ragLoading}>{ragLoading ? 'Querying…' : 'Search Related Information'}</BtnPrimary></div>
                </CardBody>
              </Card>
            </>
          ) : (
      <Card><CardBody><InfoBox>There are no production alerts above the threshold. View normal risk assessments in Knowledge Search.</InfoBox></CardBody></Card>
          )}
        </div>
      </div>

      <WarnBox><strong>Scope:</strong> Alerts are opened and resolved by the consumer risk engine. The investigation Agent can propose coordination tasks, but creates a case and tasks only after an operator approves the cited draft.</WarnBox>
    </div>
  )
}
