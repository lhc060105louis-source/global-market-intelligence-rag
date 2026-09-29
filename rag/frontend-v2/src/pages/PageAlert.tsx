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
  return [risk.brand, risk.vehicle_model, risk.part, risk.region, risk.risk_type].filter(Boolean).join(' · ') || '未命名风险对象'
}

function riskQuestion(risk: RiskItem): string {
  return `${riskTitle(risk)} 的 C 端风险事件，对 B 端商业项目和 KOL 合作有什么关联影响？`
}

function semanticCardValue(result: QueryResponse, field: SemanticFieldKey, value: string | null): string {
  const info = semanticFieldInfo(result, field)
  return info.source === 'none' ? info.notice || '本次无本域证据' : value || '未返回总结'
}

function semanticCardBadge(result: QueryResponse, field: SemanticFieldKey): { text: string; color: 'green' | 'amber' | 'gray' } {
  const source = semanticFieldInfo(result, field).source
  if (source === 'maxkb') return { text: 'LLM总结', color: 'green' }
  if (source === 'deterministic') return { text: '证据兜底', color: 'amber' }
  return { text: '无本域证据', color: 'gray' }
}

export default function PageAlert({ showToast, refreshToken = 0 }: PageAlertProps) {
  const [risks, setRisks] = useState<RiskItem[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState<RiskDetail | null>(null)
  const [ragResponse, setRagResponse] = useState<QueryResponse | null>(null)
  const [ragEvidence, setRagEvidence] = useState<AlertEvidence[]>([])
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [ragLoading, setRagLoading] = useState(false)
  const [error, setError] = useState('')
  const ragRequestSequence = useRef(0)
  const activeRagRequest = useRef<AbortController | null>(null)

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
        if (!controller.signal.aborted) setError(errorValue instanceof Error ? errorValue.message : '预警读取失败')
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
        if (!controller.signal.aborted) setError(errorValue instanceof Error ? errorValue.message : '预警详情读取失败')
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
    if (!trend.length) return '暂无趋势点'
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
      const references = result.output?.简化证据 || []
      const details = await Promise.allSettled(references.slice(0, 12).map(reference => ragApi.getRecord(reference.record_id, controller.signal)))
      if (sequence !== ragRequestSequence.current) return
      setRagEvidence(details.flatMap((item, index) => item.status === 'fulfilled'
        ? [{ record: item.value.record, score: references[index]?.score ?? null }]
        : []))
      showToast('已读取当前 RAG 跨域关联信息')
    } catch (errorValue) {
      if (controller.signal.aborted || sequence !== ragRequestSequence.current) return
      showToast(errorValue instanceof Error ? errorValue.message : '跨域查询失败')
    } finally {
      if (sequence === ragRequestSequence.current) {
        activeRagRequest.current = null
        setRagLoading(false)
      }
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px 40px' }}>
      <Grid4>
        <MetricCard label="活跃预警" value={loading ? '—' : activeCount} sub="仅来自C端风险事件" iconBg="#FEF2F2" iconColor="#DC2626" iconText="⚠" />
        <MetricCard label="已恢复风险" value={loading ? '—' : recoveredCount} sub="由上游恢复事件关闭" iconBg="#ECFDF5" iconColor="#059669" iconText="✓" />
        <MetricCard label="趋势点" value={selectedEpisode?.trend_points.length ?? '—'} sub="当前选中风险" iconBg="#EFF6FF" iconColor="#2563EB" iconText="↗" />
        <MetricCard label="跨域查询" value={ragResponse ? ragResponse.evidence_count : '—'} sub="按需检索证据条数" iconBg="#F5F0FF" iconColor="#7C3AED" iconText="◎" />
      </Grid4>

      {error && <WarnBox><strong>预警接口异常：</strong>{error}</WarnBox>}
      {loading && <InfoBox>正在读取 C 端正式风险事件…</InfoBox>}
      {!loading && risks.length === 0 && <InfoBox>当前没有达到阈值的正式风险预警；正常风险评估请在知识搜索中查看。预警由 C 端产生，RAG 页面不自行创建或修改预警。</InfoBox>}

      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 12 }}>
        <Card style={{ marginBottom: 0 }}>
          <CardHead><CardTitle icon="⚠">预警列表</CardTitle><Badge text={`${risks.length}条`} color={risks.length ? 'red' : 'gray'} /></CardHead>
          <CardBody style={{ padding: 8 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {risks.map(risk => (
                <button key={risk.id} onClick={() => setSelectedId(risk.id)}
                  style={{ display: 'flex', alignItems: 'flex-start', gap: 10, border: `0.5px solid ${selected?.id === risk.id ? '#93C5FD' : 'var(--border)'}`, background: selected?.id === risk.id ? '#F8FBFF' : '#fff', borderRadius: 8, padding: 11, textAlign: 'left', cursor: 'pointer', boxShadow: selected?.id === risk.id ? 'inset 2px 0 0 #2563EB' : 'none', width: '100%' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', gap: 5, marginBottom: 3 }}><Badge text={risk.open_episode_id ? '活跃' : '已恢复'} color={risk.open_episode_id ? 'red' : 'green'} /></div>
                    <strong style={{ fontSize: 11, color: '#111827', display: 'block', marginBottom: 3 }}>{riskTitle(risk)}</strong>
                    <p style={{ fontSize: 9, color: '#6B7280', margin: 0 }}>{risk.risk_type || '未标注风险类型'}</p>
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
                  <CardTitle icon="◎">预警详情</CardTitle>
                  <Badge text={selected.open_episode_id ? '活跃' : '已恢复'} color={selected.open_episode_id ? 'red' : 'green'} />
                </CardHead>
                <CardBody>
                  <h3 style={{ fontSize: 14, margin: '0 0 10px', color: '#111827' }}>{riskTitle(selected)}</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 12 }}>
                    {[
                      ['品牌', detail?.brand || selected.brand || '未标注'],
                      ['车型', detail?.vehicle_model || selected.vehicle_model || '未标注'],
                      ['地区 / 部件', [detail?.region || selected.region, detail?.part || selected.part].filter(Boolean).join(' · ') || '未标注'],
                    ].map(([label, value]) => (
                      <div key={label} style={{ background: '#F8FAFC', borderRadius: 6, padding: '9px 10px' }}><div style={{ fontSize: 9, color: '#6B7280', marginBottom: 3 }}>{label}</div><div style={{ fontSize: 11, fontWeight: 600 }}>{value}</div></div>
                    ))}
                  </div>
                  {detailLoading ? <InfoBox>正在读取风险详情…</InfoBox> : (
                    <div style={{ fontSize: 11, color: '#374151', lineHeight: 1.7 }}>
                      <div>风险类型：{detail?.risk_type || selected.risk_type || '未标注'}</div>
                      <div>事件状态：{selectedEpisode?.status || (selected.open_episode_id ? 'open' : '已恢复')}</div>
                      <div>趋势时间：{timeRange}</div>
                      {selectedEpisode && <div>当前值 / 阈值：{selectedEpisode.current_value ?? '—'} / {selectedEpisode.threshold ?? '—'}</div>}
                    </div>
                  )}
                </CardBody>
              </Card>

              <Card>
                <CardHead><CardTitle icon="◎">RAG 跨域补充</CardTitle><SectionNote>按需查询，不提前处理预警</SectionNote></CardHead>
                <CardBody>
                  {!ragResponse && !ragLoading && <InfoBox><strong>预警状态由 C 端负责。</strong>点击后才查询当前 B 端和 KOL 关联知识；RAG 不自行改变风险状态。</InfoBox>}
                  {ragLoading && <InfoBox>正在查询当前有效知识…</InfoBox>}
                  {ragResponse && (
                    <>
                      <div style={{ background: '#F8FAFC', borderRadius: 6, padding: 11, fontSize: 11, lineHeight: 1.7, marginBottom: 10 }}>
                        <strong>综合结论：</strong>{ragResponse.output.综合结论 || '未返回综合结论'}
                        <div style={{ fontSize: 9, color: '#6B7280', marginTop: 5 }}>{semanticStatusLabel(ragResponse)} · {ragResponse.evidence_count} 条证据 · {ragResponse.query_meta.total_ms} ms</div>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 7, marginBottom: 10 }}>
                        {[
                          { domain: 'C' as const, field: 'consumer_signal' as const, label: '消费者信号', value: ragResponse.output.C端消费者信号 },
                          { domain: 'B' as const, field: 'business_impact' as const, label: '商业影响', value: ragResponse.output.B端商业影响 },
                          { domain: 'K' as const, field: 'kol_impact' as const, label: '传播与合作影响', value: ragResponse.output.KOL传播与合作影响 },
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
                  <div style={{ marginTop: 10 }}><BtnPrimary onClick={() => void loadRag()} disabled={ragLoading}>{ragLoading ? '查询中…' : '查询跨域关联信息'}</BtnPrimary></div>
                </CardBody>
              </Card>
            </>
          ) : (
            <Card><CardBody><InfoBox>当前没有达到阈值的正式风险预警；正常风险评估请在知识搜索中查看。</InfoBox></CardBody></Card>
          )}
        </div>
      </div>

      <WarnBox><strong>边界：</strong>预警由 C 端风险引擎产生和恢复；本页面只读取风险和按需查询 RAG 证据，不提供修改预警状态或创建业务任务的假接口。</WarnBox>
    </div>
  )
}
