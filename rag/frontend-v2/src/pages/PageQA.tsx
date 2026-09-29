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
  '电池类投诉上升，哪些客户项目受影响？',
  '德国市场近期法规变化对采购项目的影响？',
  '哪些KOL合作需要暂缓？',
  '欧洲市场整体消费者情绪如何？',
]

const SCOPE_OPTIONS: { value: DomainScope; label: string }[] = [
  { value: 'auto', label: '自动判断范围' },
  { value: 'c', label: 'C端消费者信号' },
  { value: 'b', label: 'B端商业情报' },
  { value: 'kol', label: 'KOL合作信息' },
]

const LOAD_STEPS = [
  '解析问题意图…',
  '按选择范围检索当前知识…',
  '筛选主库校验后的有效证据…',
  '生成八类结构化回答…',
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
  return { auto: 'C + B + KOL', c: '仅C端', b: '仅B端', kol: '仅KOL' }[scope]
}

function splitActions(value: string | null | undefined): string[] {
  if (!value) return []
  return value.split(/[；;\n]/).map(item => item.trim()).filter(Boolean)
}

function outputValue(value: string | null | undefined): string {
  return value?.trim() || '本次选定范围内没有可展示的有效证据。'
}

function semanticValue(result: QueryResponse, field: SemanticFieldKey, value: string | null): string {
  const info = semanticFieldInfo(result, field)
  return info.source === 'none' ? info.notice || outputValue(value) : outputValue(value)
}

function semanticBadge(result: QueryResponse, field: SemanticFieldKey): { text: string; color: 'green' | 'amber' | 'gray' } {
  const source = semanticFieldInfo(result, field).source
  if (source === 'maxkb') return { text: 'LLM总结', color: 'green' }
  if (source === 'deterministic') return { text: '证据兜底', color: 'amber' }
  return { text: '无本域证据', color: 'gray' }
}

export default function PageQA({ showToast, refreshToken = 0 }: PageQAProps) {
  const [question, setQuestion] = useState('请综合当前证据，说明消费者反馈、商业合规影响以及 KOL 达人传播与合作影响分别有哪些重点？')
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
      showToast('请先输入业务问题')
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
      const references = result.output?.简化证据 || []
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
        { q: trimmedQuestion, scope: scopeLabel(scope), time: '刚刚' },
        ...items.filter(item => item.q !== trimmedQuestion).slice(0, 19),
      ])
      showToast(semanticStatusLabel(result))
    } catch (error) {
      if (controller.signal.aborted || sequence !== requestSequence.current) return
      setQaState('error')
      setErrorMessage(error instanceof Error ? error.message : 'RAG Hub 请求失败')
      showToast('查询失败，请稍后重试')
    } finally {
      if (sequence === requestSequence.current) activeRequest.current = null
    }
  }

  function exportBrief() {
    if (!response) return
    downloadBriefHtml(response, evidence)
    showToast('HTML 简报已下载')
  }

  const cCount = currentRecords.filter(record => recordDomain(record) === 'C').length
  const bCount = currentRecords.filter(record => recordDomain(record) === 'B').length
  const kCount = currentRecords.filter(record => recordDomain(record) === 'K').length
  const output = response?.output
  const actions = splitActions(output?.文字行动建议)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px 40px' }}>
      <Grid4>
        <MetricCard label="C端知识条目" value={summary ? cCount : '—'} sub="当前有效记录" iconBg="#ECFDF5" iconColor="#059669" iconText="C" />
        <MetricCard label="B端商业情报" value={summary ? bCount : '—'} sub="当前有效记录" iconBg="#EFF6FF" iconColor="#2563EB" iconText="B" />
        <MetricCard label="KOL运营知识" value={summary ? kCount : '—'} sub="当前有效记录" iconBg="#F5F0FF" iconColor="#7C3AED" iconText="K" />
        <MetricCard label="当前活跃预警" value={summary ? summary.risks.active : '—'} sub="由C端风险事件提供" iconBg="#FEF2F2" iconColor="#DC2626" iconText="⚠" />
      </Grid4>

      <InfoBox>
        <strong>功能说明：</strong>输入业务问题，系统调用正式 RAG Hub 检索 C 端消费者信号、B 端商业情报和 KOL 合作信息；回答状态、证据和降级原因均来自接口，不使用页面演示数据。
      </InfoBox>

      <Card>
        <CardHead><CardTitle icon="✦">跨域业务提问</CardTitle><SectionNote>选择查询范围后点击开始分析</SectionNote></CardHead>
        <CardBody>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              value={question}
              onChange={event => setQuestion(event.target.value)}
              onKeyDown={event => { if (event.key === 'Enter') void startAnalysis() }}
              placeholder="输入业务问题，例如：电池类投诉上升会影响哪些项目？"
              style={{ flex: 1, height: 38, border: '0.5px solid #CBD5E1', borderRadius: 6, padding: '0 12px', fontSize: 12, outline: 'none' }}
            />
            <select value={scope} onChange={event => setScope(event.target.value as DomainScope)}
              style={{ fontSize: 11, padding: '6px 8px', border: '0.5px solid var(--border)', borderRadius: 5, background: '#fff', height: 38 }}>
              {SCOPE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <BtnPrimary onClick={() => void startAnalysis()} disabled={qaState === 'loading'}>
              {qaState === 'loading' ? '分析中…' : '⊞ 开始分析'}
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
          <CardHead><CardTitle icon="◎">正在分析中</CardTitle></CardHead>
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
          <CardHead><CardTitle icon="○">{qaState === 'clarification' ? '需要补充查询条件' : '未检索到有效证据'}</CardTitle></CardHead>
          <CardBody>
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                {response?.clarification?.question || response?.output.综合结论 || '当前知识库未检索到可支持回答的内容'}
              </div>
              <div style={{ fontSize: 11, color: '#6B7280', lineHeight: 1.7 }}>
                已在 {response ? response.selected_targets.join('、') : '选定范围'} 内完成检索。请补充实体、调整问题描述或扩展查询范围。
              </div>
              <div style={{ marginTop: 14 }}>
                <BtnOutline onClick={() => setScope('auto')}>扩展至全部范围</BtnOutline>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {qaState === 'error' && (
        <Card>
          <CardHead><CardTitle icon="✕">系统异常</CardTitle><Badge text="服务不可用" color="red" /></CardHead>
          <CardBody>
            <div style={{ background: '#FEF2F2', border: '0.5px solid rgba(185,28,28,0.2)', borderRadius: 7, padding: 14, color: '#7F1D1D', fontSize: 11, lineHeight: 1.7 }}>
              <strong style={{ display: 'block', marginBottom: 4 }}>RAG Hub 请求失败</strong>
              {errorMessage || '请检查 RAG Hub、MaxKB 和本机代理状态。'}
            </div>
            <div style={{ marginTop: 12 }}><BtnPrimary onClick={() => setQaState('idle')}>重新尝试</BtnPrimary></div>
          </CardBody>
        </Card>
      )}

      {qaState === 'success' && response && output && (
        <div>
          <Card>
            <CardHead>
              <CardTitle icon="◎">RAG 综合回答</CardTitle>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <Badge text={semanticStatusLabel(response)} color={response.query_meta.generation_status === 'degraded' ? 'amber' : 'green'} />
                <BtnOutline onClick={exportBrief}>导出 HTML 简报</BtnOutline>
              </div>
            </CardHead>
            <CardBody>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <div style={{ width: 38, height: 38, borderRadius: 8, background: '#EFF6FF', color: '#2563EB', display: 'grid', placeItems: 'center', fontSize: 17, flexShrink: 0 }}>✦</div>
                <div style={{ flex: 1 }}>
                  <h3 style={{ fontSize: 14, margin: '0 0 6px', color: '#111827' }}>{outputValue(output.综合结论)}</h3>
                  <p style={{ fontSize: 10, color: '#6B7280', lineHeight: 1.7, margin: 0 }}>
                    {semanticStatusLabel(response)} · {response.evidence_count} 条证据 · {response.query_meta.total_ms} ms
                    {response.query_meta.degraded_reason ? ` · 原因：${response.query_meta.degraded_reason}` : ''}
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
              { domain: 'C' as const, field: 'consumer_signal' as const, title: 'C端消费者信号', value: output.C端消费者信号 },
              { domain: 'B' as const, field: 'business_impact' as const, title: 'B端商业影响', value: output.B端商业影响 },
              { domain: 'K' as const, field: 'kol_impact' as const, title: 'KOL传播与合作影响', value: output.KOL传播与合作影响 },
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
            <CardHead><CardTitle icon="✓">文字行动建议</CardTitle><SectionNote>只展示后端返回内容，不由前端补造</SectionNote></CardHead>
            <CardBody>
              {actions.length ? actions.map((action, index) => (
                <div key={action} style={{ display: 'flex', gap: 9, alignItems: 'flex-start', padding: '8px 0', borderBottom: index < actions.length - 1 ? '0.5px solid #F1F5F9' : 0 }}>
                  <Badge text={`建议 ${index + 1}`} color="gray" />
                  <span style={{ fontSize: 11, color: '#374151', lineHeight: 1.6 }}>{action}</span>
                </div>
              )) : <InfoBox>本次没有可展示的行动建议。</InfoBox>}
            </CardBody>
          </Card>

          <Card>
            <CardHead><CardTitle icon="▤">关键证据</CardTitle><SectionNote>点击查看正式记录详情</SectionNote></CardHead>
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
                  {item.score !== null && <Badge text={`相关度 ${item.score.toFixed(2)}`} color="blue" />}
                </button>
              )) : <InfoBox>接口返回了证据引用，但详情暂时不可用。</InfoBox>}
            </CardBody>
          </Card>

          {selectedEvidence && (
            <Card>
              <CardHead>
                <CardTitle icon="◎">证据详情</CardTitle>
                <BtnOutline onClick={() => setSelectedEvidence(null)}>关闭</BtnOutline>
              </CardHead>
              <CardBody>
                <strong style={{ display: 'block', fontSize: 12, marginBottom: 7 }}>{recordTitle(selectedEvidence.record)}</strong>
                <div style={{ fontSize: 11, color: '#374151', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{selectedEvidence.record.retrieval_text}</div>
                {selectedEvidence.record.source_url && <a href={selectedEvidence.record.source_url} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 10, fontSize: 10, color: '#2563EB' }}>打开来源</a>}
              </CardBody>
            </Card>
          )}

          <WarnBox>
            <strong>结论边界：</strong>{output.结论边界 || '本回答仅依据当前有效知识生成，不代替质量鉴定、法律判断或正式业务决策。'}
          </WarnBox>
        </div>
      )}

      {history.length > 0 && (
        <Card>
          <CardHead><CardTitle icon="↺">本次页面查询记录</CardTitle><SectionNote>仅保存在当前页面会话</SectionNote></CardHead>
          <CardBody style={{ padding: '4px 14px' }}>
            {history.map((item, index) => (
              <button key={`${item.q}-${index}`} onClick={() => { setQuestion(item.q); setScope(item.scope === '仅C端' ? 'c' : item.scope === '仅B端' ? 'b' : item.scope === '仅KOL' ? 'kol' : 'auto') }}
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
