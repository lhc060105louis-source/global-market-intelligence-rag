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
  all: 'All',
  feedback: 'Consumer Feedback',
  risk_assessment: 'Risk Assessment (Normal)',
  risk_alert: 'Risk Alerts',
  project: 'client project',
  policy: 'regulations',
  kol_trend: 'KOLreachtrend',
}

const SOURCE_LABEL: Record<SourceFilter, string> = {
  all: 'All Sources',
  c: 'consumer_signal',
  b: 'Business Intelligence',
  kol: 'Creator Partnerships',
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
    return values.map(String).join(', ') || 'Unspecified region'
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
    if (!controller.signal.aborted) setError(errorValue instanceof Error ? errorValue.message : 'Failed to load knowledge records')
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
    showToast(`Search complete: ${filtered.length} active records found`)
  }

  function resetSearch() {
    setKeyword('')
    setSearched(false)
    setSourceFilter('all')
    setTypeFilter('all')
  }

  async function addAnnotation(annotationType: 'public_note' | 'correction_feedback') {
    if (!selected) return
    const content = window.prompt(annotationType === 'correction_feedback' ? 'Enter the correction' : 'Enter a public note')
    if (!content?.trim()) return
    try {
      await ragApi.addAnnotation(selected.id, annotationType, content.trim())
    showToast(annotationType === 'correction_feedback' ? 'Correction recorded' : 'Public note recorded')
    } catch (errorValue) {
    showToast(errorValue instanceof Error ? errorValue.message : 'Failed to save the record')
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px 40px' }}>
      <Card>
    <CardHead><CardTitle icon="⊞">Knowledge Search</CardTitle><SectionNote>Browse active records in the RAG Hub</SectionNote></CardHead>
        <CardBody>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <input
              value={keyword}
              onChange={event => setKeyword(event.target.value)}
              onKeyDown={event => { if (event.key === 'Enter') doSearch() }}
    placeholder="Enter keywords, e.g. battery, German market, procurement project, creator partnership…"
              style={{ flex: 1, height: 36, border: '0.5px solid #CBD5E1', borderRadius: 6, padding: '0 12px', fontSize: 12, outline: 'none' }}
            />
            <button onClick={doSearch} style={{ fontSize: 12, padding: '0 16px', borderRadius: 6, background: '#2563EB', color: '#fff', border: 'none', cursor: 'pointer', height: 36 }}>Search</button>
            <button onClick={resetSearch} style={{ fontSize: 11, padding: '0 12px', borderRadius: 6, background: '#F8FAFC', color: '#374151', border: '0.5px solid var(--border)', cursor: 'pointer', height: 36 }}>Reset</button>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ fontSize: 10, color: '#6B7280' }}>Source: </span>
            {(Object.keys(SOURCE_LABEL) as SourceFilter[]).map(value => (
              <BtnOutline key={value} active={sourceFilter === value} onClick={() => setSourceFilter(value)}>{SOURCE_LABEL[value]}</BtnOutline>
            ))}
            <span style={{ fontSize: 10, color: '#6B7280', marginLeft: 8 }}>Type: </span>
            {(Object.keys(TYPE_LABEL) as TypeFilter[]).map(value => (
              <BtnOutline key={value} active={typeFilter === value} onClick={() => setTypeFilter(value)}>{TYPE_LABEL[value]}</BtnOutline>
            ))}
          </div>
        </CardBody>
      </Card>

    {loading && <InfoBox>Loading active knowledge records…</InfoBox>}
    {error && <WarnBox><strong>Failed to load knowledge records:</strong> {error}</WarnBox>}

      <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
    <span style={{ fontSize: 11, color: '#6B7280' }}>{searched ? `Search results: ${filtered.length}` : `Active records: ${filtered.length}`}</span>
    <span style={{ fontSize: 10, color: '#9CA3AF' }}>{records.length} loaded</span>
          </div>
          {filtered.length === 0 && !loading ? (
            <Card><CardBody><div style={{ textAlign: 'center', padding: '24px 0', color: '#9CA3AF', fontSize: 12 }}>No active records match the selected criteria</div></CardBody></Card>
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
    <CardTitle icon="▤">Record Details</CardTitle>
                <div style={{ display: 'flex', gap: 5 }}>
                  <Badge text={SOURCE_LABEL[sourceFilterFor(selected)]} color={recordDomain(selected) === 'C' ? 'green' : recordDomain(selected) === 'B' ? 'blue' : 'purple'} />
                  <Badge text={TYPE_LABEL[typeFor(selected)]} color="gray" />
                </div>
              </CardHead>
              <CardBody>
                <h3 style={{ fontSize: 14, margin: '0 0 12px', color: '#111827', lineHeight: 1.4 }}>{recordTitle(selected)}</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 14 }}>
                  <div style={{ background: '#F8FAFC', borderRadius: 5, padding: '8px 10px' }}><div style={{ fontSize: 9, color: '#6B7280', marginBottom: 2 }}>Applicable Region</div><div style={{ fontSize: 11, fontWeight: 600 }}>{countryFor(selected)}</div></div>
                  <div style={{ background: '#F8FAFC', borderRadius: 5, padding: '8px 10px' }}><div style={{ fontSize: 9, color: '#6B7280', marginBottom: 2 }}>Last Updated</div><div style={{ fontSize: 10 }}>{formatDateTime(recordTime(selected))}</div></div>
                  <div style={{ background: '#F8FAFC', borderRadius: 5, padding: '8px 10px' }}><div style={{ fontSize: 9, color: '#6B7280', marginBottom: 2 }}>Record Version</div><div style={{ fontSize: 11, fontWeight: 600 }}>v{selected.source_version}</div></div>
                </div>
                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 6, fontWeight: 600 }}>Content Summary</div>
                  <div style={{ background: '#F8FAFC', border: '0.5px solid var(--border)', borderRadius: 6, padding: '12px 14px', fontSize: 11, color: '#374151', lineHeight: 1.75, whiteSpace: 'pre-wrap' }}>{recordSummary(selected)}</div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {selected.source_url && <a href={selected.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: '#2563EB', background: '#EFF6FF', border: '0.5px solid rgba(37,99,235,0.25)', borderRadius: 5, padding: '5px 12px' }}>↗ View original source</a>}
                  <button onClick={() => void addAnnotation('public_note')} style={{ fontSize: 11, color: '#374151', background: '#F8FAFC', border: '0.5px solid var(--border)', borderRadius: 5, padding: '5px 12px', cursor: 'pointer' }}>＋ Add public note</button>
                  <button onClick={() => void addAnnotation('correction_feedback')} style={{ fontSize: 11, color: '#92400E', background: '#FFFBEB', border: '0.5px solid rgba(180,83,9,0.25)', borderRadius: 5, padding: '5px 12px', cursor: 'pointer' }}>⚑ Submit correction</button>
                </div>
    <WarnBox><strong>Citation limitations:</strong> This record comes from active RAG Hub data for internal reference. It does not replace formal decisions in the source business system.</WarnBox>
    <div style={{ fontSize: 9, color: '#9CA3AF', lineHeight: 1.5 }}>Record ID: {shortId(selected)} · Source version: {selected.source_version} · {selected.is_mock ? 'Demo record' : 'Production record'}</div>
              </CardBody>
            </Card>
          ) : (
              <Card><CardBody><InfoBox>Select a record to view its details.</InfoBox></CardBody></Card>
          )}
        </div>
      </div>
    </div>
  )
}
