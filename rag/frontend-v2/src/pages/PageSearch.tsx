import { useEffect, useMemo, useState } from 'react'
import {
  Badge,
  BtnOutline,
  Card,
  CardBody,
  CardHead,
  CardTitle,
  DomainMark,
  InfoBox,
  SectionNote,
  WarnBox,
} from '../components/ui'
import {
  RagRecord,
  decodePayload,
  formatDateTime,
  ragApi,
  recordDomain,
  recordDisplayCategory,
  recordSummary,
  recordTime,
  recordTitle,
} from '../lib/api'

type SourceFilter = 'all' | 'c' | 'b' | 'kol'
type TypeFilter = 'all' | 'feedback' | 'risk_assessment' | 'risk_alert' | 'project' | 'policy' | 'kol_trend'

const TYPE_LABEL: Record<TypeFilter, string> = {
  all: '全部',
  feedback: '消费者反馈',
  risk_assessment: '风险评估（正常）',
  risk_alert: '风险预警',
  project: '客户项目',
  policy: '政策法规',
  kol_trend: 'KOL传播趋势',
}

const SOURCE_LABEL: Record<SourceFilter, string> = {
  all: '全部来源',
  c: 'C端消费者信号',
  b: 'B端商业情报',
  kol: 'KOL合作信息',
}

function sourceFilterFor(record: RagRecord): Exclude<SourceFilter, 'all'> {
  return record.source_system === 'C' ? 'c' : record.source_system === 'B' ? 'b' : 'kol'
}

function typeFor(record: RagRecord): Exclude<TypeFilter, 'all'> {
  return recordDisplayCategory(record)
}

function countryFor(record: RagRecord): string {
  const payload = decodePayload(record)
  const values = [payload.region, payload.country, payload.market, payload.audience_regions]
    .flatMap(value => Array.isArray(value) ? value : [value])
    .filter(value => value !== undefined && value !== null && String(value).trim())
  return values.map(String).join('、') || '未标注地区'
}

function shortId(record: RagRecord): string {
  return record.id.slice(0, 8)
}

interface PageSearchProps {
  showToast: (message: string) => void
  refreshToken?: number
}

export default function PageSearch({ showToast, refreshToken = 0 }: PageSearchProps) {
  const [records, setRecords] = useState<RagRecord[]>([])
  const [keyword, setKeyword] = useState('')
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [searched, setSearched] = useState(false)
  const [selectedId, setSelectedId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void ragApi.listRecords({ status: 'active', record_mode: 'current', page: 1, page_size: 200 }, controller.signal)
      .then(result => {
        setRecords(result.items)
        setSelectedId(current => current && result.items.some(item => item.id === current) ? current : result.items[0]?.id || '')
      })
      .catch(errorValue => {
        if (!controller.signal.aborted) setError(errorValue instanceof Error ? errorValue.message : '知识记录读取失败')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [refreshToken])

  const filtered = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase()
    return records.filter(record => {
      if (sourceFilter !== 'all' && sourceFilterFor(record) !== sourceFilter) return false
      if (typeFilter !== 'all' && typeFor(record) !== typeFilter) return false
      if (!searched || !normalizedKeyword) return true
      const haystack = [recordTitle(record), recordSummary(record), countryFor(record), record.record_type].join(' ').toLowerCase()
      return haystack.includes(normalizedKeyword)
    })
  }, [keyword, records, searched, sourceFilter, typeFilter])

  const selected = records.find(record => record.id === selectedId) || filtered[0]

  function doSearch() {
    setSearched(true)
    showToast(`检索完成，共找到 ${filtered.length} 条当前有效记录`)
  }

  function resetSearch() {
    setKeyword('')
    setSearched(false)
    setSourceFilter('all')
    setTypeFilter('all')
  }

  async function addAnnotation(annotationType: 'public_note' | 'correction_feedback') {
    if (!selected) return
    const content = window.prompt(annotationType === 'correction_feedback' ? '请输入纠错内容' : '请输入公开备注')
    if (!content?.trim()) return
    try {
      await ragApi.addAnnotation(selected.id, annotationType, content.trim())
      showToast(annotationType === 'correction_feedback' ? '纠错反馈已记录' : '公开备注已记录')
    } catch (errorValue) {
      showToast(errorValue instanceof Error ? errorValue.message : '记录失败')
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px 40px' }}>
      <Card>
        <CardHead><CardTitle icon="⊞">知识搜索</CardTitle><SectionNote>读取 RAG Hub 当前有效记录</SectionNote></CardHead>
        <CardBody>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <input
              value={keyword}
              onChange={event => setKeyword(event.target.value)}
              onKeyDown={event => { if (event.key === 'Enter') doSearch() }}
              placeholder="输入关键词，例如：电池、德国市场、采购项目、KOL合作…"
              style={{ flex: 1, height: 36, border: '0.5px solid #CBD5E1', borderRadius: 6, padding: '0 12px', fontSize: 12, outline: 'none' }}
            />
            <button onClick={doSearch} style={{ fontSize: 12, padding: '0 16px', borderRadius: 6, background: '#2563EB', color: '#fff', border: 'none', cursor: 'pointer', height: 36 }}>搜索</button>
            <button onClick={resetSearch} style={{ fontSize: 11, padding: '0 12px', borderRadius: 6, background: '#F8FAFC', color: '#374151', border: '0.5px solid var(--border)', cursor: 'pointer', height: 36 }}>重置</button>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ fontSize: 10, color: '#6B7280' }}>来源：</span>
            {(Object.keys(SOURCE_LABEL) as SourceFilter[]).map(value => (
              <BtnOutline key={value} active={sourceFilter === value} onClick={() => setSourceFilter(value)}>{SOURCE_LABEL[value]}</BtnOutline>
            ))}
            <span style={{ fontSize: 10, color: '#6B7280', marginLeft: 8 }}>类型：</span>
            {(Object.keys(TYPE_LABEL) as TypeFilter[]).map(value => (
              <BtnOutline key={value} active={typeFilter === value} onClick={() => setTypeFilter(value)}>{TYPE_LABEL[value]}</BtnOutline>
            ))}
          </div>
        </CardBody>
      </Card>

      {loading && <InfoBox>正在读取当前有效知识记录…</InfoBox>}
      {error && <WarnBox><strong>知识记录读取失败：</strong>{error}</WarnBox>}

      <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: '#6B7280' }}>{searched ? `搜索结果：${filtered.length} 条` : `当前有效记录：${filtered.length} 条`}</span>
            <span style={{ fontSize: 10, color: '#9CA3AF' }}>{records.length} 条已加载</span>
          </div>
          {filtered.length === 0 && !loading ? (
            <Card><CardBody><div style={{ textAlign: 'center', padding: '24px 0', color: '#9CA3AF', fontSize: 12 }}>没有符合条件的当前有效记录</div></CardBody></Card>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {filtered.map(record => {
                const domain = recordDomain(record)
                return (
                  <button key={record.id} onClick={() => setSelectedId(record.id)}
                    style={{ border: `0.5px solid ${selected?.id === record.id ? '#93C5FD' : 'var(--border)'}`, background: selected?.id === record.id ? '#F8FBFF' : '#fff', borderRadius: 8, padding: 11, textAlign: 'left', cursor: 'pointer', boxShadow: selected?.id === record.id ? 'inset 2px 0 0 #2563EB' : 'none', width: '100%' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 5 }}>
                      <DomainMark domain={domain} />
                      <Badge text={TYPE_LABEL[typeFor(record)]} color="gray" />
                      <Badge text={countryFor(record)} color="blue" />
                      <span style={{ fontSize: 9, color: '#9CA3AF', marginLeft: 'auto' }}>{formatDateTime(recordTime(record))}</span>
                    </div>
                    <strong style={{ fontSize: 11, color: '#111827', display: 'block', marginBottom: 3, lineHeight: 1.4 }}>{recordTitle(record)}</strong>
                    <p style={{ fontSize: 9, color: '#6B7280', margin: 0, lineHeight: 1.5 }}>{recordSummary(record)}</p>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        <div>
          {selected ? (
            <Card style={{ marginBottom: 0, position: 'sticky', top: 0 }}>
              <CardHead>
                <CardTitle icon="▤">资料详情</CardTitle>
                <div style={{ display: 'flex', gap: 5 }}>
                  <Badge text={SOURCE_LABEL[sourceFilterFor(selected)]} color={recordDomain(selected) === 'C' ? 'green' : recordDomain(selected) === 'B' ? 'blue' : 'purple'} />
                  <Badge text={TYPE_LABEL[typeFor(selected)]} color="gray" />
                </div>
              </CardHead>
              <CardBody>
                <h3 style={{ fontSize: 14, margin: '0 0 12px', color: '#111827', lineHeight: 1.4 }}>{recordTitle(selected)}</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 14 }}>
                  <div style={{ background: '#F8FAFC', borderRadius: 5, padding: '8px 10px' }}><div style={{ fontSize: 9, color: '#6B7280', marginBottom: 2 }}>适用地区</div><div style={{ fontSize: 11, fontWeight: 600 }}>{countryFor(selected)}</div></div>
                  <div style={{ background: '#F8FAFC', borderRadius: 5, padding: '8px 10px' }}><div style={{ fontSize: 9, color: '#6B7280', marginBottom: 2 }}>最近更新</div><div style={{ fontSize: 10 }}>{formatDateTime(recordTime(selected))}</div></div>
                  <div style={{ background: '#F8FAFC', borderRadius: 5, padding: '8px 10px' }}><div style={{ fontSize: 9, color: '#6B7280', marginBottom: 2 }}>记录版本</div><div style={{ fontSize: 11, fontWeight: 600 }}>v{selected.source_version}</div></div>
                </div>
                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 6, fontWeight: 600 }}>内容摘要</div>
                  <div style={{ background: '#F8FAFC', border: '0.5px solid var(--border)', borderRadius: 6, padding: '12px 14px', fontSize: 11, color: '#374151', lineHeight: 1.75, whiteSpace: 'pre-wrap' }}>{recordSummary(selected)}</div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {selected.source_url && <a href={selected.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: '#2563EB', background: '#EFF6FF', border: '0.5px solid rgba(37,99,235,0.25)', borderRadius: 5, padding: '5px 12px' }}>↗ 查看原业务来源</a>}
                  <button onClick={() => void addAnnotation('public_note')} style={{ fontSize: 11, color: '#374151', background: '#F8FAFC', border: '0.5px solid var(--border)', borderRadius: 5, padding: '5px 12px', cursor: 'pointer' }}>＋ 添加公开备注</button>
                  <button onClick={() => void addAnnotation('correction_feedback')} style={{ fontSize: 11, color: '#92400E', background: '#FFFBEB', border: '0.5px solid rgba(180,83,9,0.25)', borderRadius: 5, padding: '5px 12px', cursor: 'pointer' }}>⚑ 提交纠错反馈</button>
                </div>
                <WarnBox><strong>引用边界：</strong>本资料来自 RAG Hub 当前有效记录，仅供内部参考，不能直接替代原业务系统的正式判断。</WarnBox>
                <div style={{ fontSize: 9, color: '#9CA3AF', lineHeight: 1.5 }}>记录 ID：{shortId(selected)} · 来源版本：{selected.source_version} · {selected.is_mock ? '演示标记' : '正式标记'}</div>
              </CardBody>
            </Card>
          ) : (
            <Card><CardBody><InfoBox>请选择一条记录查看详情。</InfoBox></CardBody></Card>
          )}
        </div>
      </div>
    </div>
  )
}
