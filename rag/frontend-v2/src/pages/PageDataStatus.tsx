import { useEffect, useState } from 'react'
import {
  Badge,
  Card,
  CardBody,
  CardHead,
  CardTitle,
  Grid4,
  InfoBox,
  MetricCard,
  SectionNote,
  WarnBox,
} from '../components/ui'
import {
  RagRecord,
  SyncSummaryItem,
  formatDateTime,
  ragApi,
  syncStatus,
} from '../lib/api'

type ViewStatus = 'ok' | 'syncing' | 'error'

interface SourceView {
  id: string
  label: string
  domain: 'C' | 'B' | 'K'
  target: string
  recordMode: 'current' | 'snapshot'
  knowledge: number
  lastSync: string
  status: ViewStatus
  task: SyncSummaryItem
}

const SOURCE_CONFIG: Array<Omit<SourceView, 'knowledge' | 'lastSync' | 'status' | 'task'>> = [
  { id: 'c_current', target: 'c_current', recordMode: 'current', label: 'Consumer Reviews and Owner Feedback (Current)', domain: 'C' },
  { id: 'c_history', target: 'c_history', recordMode: 'snapshot', label: 'Historical Consumer Knowledge Snapshots', domain: 'C' },
  { id: 'b_business', target: 'b_business', recordMode: 'current', label: 'Business Intelligence and Regulations', domain: 'B' },
  { id: 'kol', target: 'kol', recordMode: 'current', label: 'Creator and Partnership Information', domain: 'K' },
]

function latestRecordTime(records: RagRecord[]): string {
  return records.reduce((latest, record) => {
    const value = record.updated_at || record.source_updated_at || record.effective_at
    return !latest || new Date(value).valueOf() > new Date(latest).valueOf() ? value : latest
  }, '')
}

function statusLabel(status: ViewStatus): { text: string; color: 'green' | 'blue' | 'red'; dot: string } {
  if (status === 'error') return { text: 'Failed tasks', color: 'red', dot: '#DC2626' }
  if (status === 'syncing') return { text: 'Processing in background', color: 'blue', dot: '#2563EB' }
  return { text: 'Healthy', color: 'green', dot: '#059669' }
}

function sumTasks(tasks: SyncSummaryItem[]): SyncSummaryItem {
  return tasks.reduce((result, item) => ({
    pending: result.pending + item.pending,
    processing: result.processing + item.processing,
    completed: result.completed + item.completed,
    failed: result.failed + item.failed,
    timed_out: result.timed_out + item.timed_out,
  }), { pending: 0, processing: 0, completed: 0, failed: 0, timed_out: 0 })
}

interface PageDataStatusProps {
  showToast: (message: string) => void
  refreshToken?: number
}

export default function PageDataStatus({ showToast, refreshToken = 0 }: PageDataStatusProps) {
  const [sources, setSources] = useState<SourceView[]>([])
  const [overallTask, setOverallTask] = useState<SyncSummaryItem>({ pending: 0, processing: 0, completed: 0, failed: 0, timed_out: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void Promise.all([
      ragApi.syncSummary(),
      ...SOURCE_CONFIG.map(source => ragApi.listRecords({
        status: 'active',
        record_mode: source.recordMode,
        target_knowledge_base: source.target,
        page: 1,
        page_size: 200,
      }, controller.signal)),
    ]).then(([sync, ...recordResponses]) => {
      const taskValues = SOURCE_CONFIG.map(source => sync.targets[source.target] || { pending: 0, processing: 0, completed: 0, failed: 0, timed_out: 0 })
      setOverallTask(sumTasks(taskValues))
      setSources(SOURCE_CONFIG.map((source, index) => {
        const records = (recordResponses[index] as { items: RagRecord[] }).items
        const task = taskValues[index]
        return {
          ...source,
          knowledge: records.length,
          lastSync: latestRecordTime(records),
          status: syncStatus(task),
          task,
        }
      }))
    }).catch(errorValue => {
    if (!controller.signal.aborted) setError(errorValue instanceof Error ? errorValue.message : 'Failed to load data status')
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [refreshToken, reload])

  const healthyCount = sources.filter(source => source.status === 'ok').length
  const errorCount = sources.filter(source => source.status === 'error').length
  const totalKnowledge = sources.reduce((total, source) => total + source.knowledge, 0)
  const latestValues = sources.map(source => source.lastSync).filter(Boolean).sort()
  const latest = latestValues.length ? latestValues[latestValues.length - 1] : ''

  function refreshStatus() {
    setReload(value => value + 1)
    showToast('Background sync status refreshed')
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px 40px' }}>
      <Grid4>
      <MetricCard label="Healthy Source Rate" value={sources.length ? `${Math.round((healthyCount / sources.length) * 100)}%` : '—'} sub={`${healthyCount}/${sources.length || '—'} healthy sources`} iconBg="#ECFDF5" iconColor="#059669" iconText="✓" />
      <MetricCard label="Active Knowledge Records" value={loading ? '—' : totalKnowledge.toLocaleString()} sub="Current records in the FastAPI database" iconBg="#EFF6FF" iconColor="#2563EB" iconText="▤" />
      <MetricCard label="Failed or Timed-out Tasks" value={loading ? '—' : overallTask.failed + overallTask.timed_out} sub="Background maintenance status" iconBg={errorCount ? '#FEF2F2' : '#ECFDF5'} iconColor={errorCount ? '#DC2626' : '#059669'} iconText={errorCount ? '✕' : '✓'} />
      <MetricCard label="Latest Source Change" value={latest ? formatDateTime(latest) : '—'} sub="Ordered by primary database update time" iconBg="#F5F0FF" iconColor="#7C3AED" iconText="⇄" />
      </Grid4>

      {error && <WarnBox><strong>Failed to load status:</strong> {error}</WarnBox>}
      {loading && <InfoBox>Loading current records and background sync jobs…</InfoBox>}

      <Card>
        <CardHead>
          <CardTitle icon="⇄">Sync Status</CardTitle>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Badge text="Automatically maintained" color="blue" />
            <button onClick={refreshStatus} disabled={loading} style={{ fontSize: 11, padding: '5px 10px', borderRadius: 5, border: '0.5px solid var(--border)', background: '#F8FAFC', color: '#374151', cursor: loading ? 'not-allowed' : 'pointer' }}>↻ Refresh Status</button>
          </div>
        </CardHead>
        <CardBody>
          <div style={{ fontSize: 11, color: '#6B7280', lineHeight: 1.7 }}>
        Data delivery from the consumer, business, and creator modules and MaxKB synchronization are handled by backend jobs. The frontend only reads status and does not trigger synchronization or resynchronization.
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginTop: 10 }}>
      {['Received by All Modules', 'Version Check', 'Primary Database Write', 'MaxKB Background Sync', 'Index Status Update'].map((step, index, all) => (
              <span key={step} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ background: '#F8FAFC', border: '0.5px solid var(--border)', borderRadius: 6, padding: '5px 10px', fontSize: 10, color: '#374151' }}>{step}</span>
                {index < all.length - 1 && <span style={{ color: '#94A3B8' }}>→</span>}
              </span>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
      <CardHead><CardTitle icon="▤">Data Status by Module</CardTitle><SectionNote>{loading ? 'Loading…' : 'Data is provided by the production RAG Hub API'}</SectionNote></CardHead>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr>
              {['Data Source', 'Active Records', 'Latest Change', 'Status', 'Completed Tasks', 'Failed / Timed out'].map(title => (
                <th key={title} style={{ fontSize: 10, fontWeight: 500, color: '#6B7280', textAlign: 'left', padding: '8px 12px', background: '#F8FAFC', borderBottom: '0.5px solid var(--border)', whiteSpace: 'nowrap' }}>{title}</th>
              ))}
            </tr></thead>
            <tbody>
              {sources.map(source => {
                const display = statusLabel(source.status)
                return (
                  <tr key={source.id}>
                    <td style={{ padding: '10px 12px', borderBottom: '0.5px solid #F1F5F9' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                        <span style={{ width: 26, height: 22, borderRadius: 5, background: source.domain === 'C' ? '#ECFDF5' : source.domain === 'B' ? '#EFF6FF' : '#F5F0FF', color: source.domain === 'C' ? '#047857' : source.domain === 'B' ? '#1D4ED8' : '#6D28D9', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 8, fontWeight: 700 }}>{source.domain}</span>
                        <span style={{ fontSize: 11, fontWeight: 600, color: '#111827' }}>{source.label}</span>
                      </div>
                    </td>
        <td style={{ padding: '10px 12px', borderBottom: '0.5px solid #F1F5F9', fontSize: 12 }}>{source.knowledge.toLocaleString()} records</td>
                    <td style={{ padding: '10px 12px', borderBottom: '0.5px solid #F1F5F9', fontSize: 10, color: '#6B7280', whiteSpace: 'nowrap' }}>{formatDateTime(source.lastSync)}</td>
                    <td style={{ padding: '10px 12px', borderBottom: '0.5px solid #F1F5F9' }}><span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 6, height: 6, borderRadius: '50%', background: display.dot }} /><Badge text={display.text} color={display.color} /></span></td>
                    <td style={{ padding: '10px 12px', borderBottom: '0.5px solid #F1F5F9', fontSize: 11, color: '#059669' }}>{source.task.completed}</td>
                    <td style={{ padding: '10px 12px', borderBottom: '0.5px solid #F1F5F9', fontSize: 11, color: source.task.failed || source.task.timed_out ? '#DC2626' : '#6B7280' }}>{source.task.failed} / {source.task.timed_out}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <CardHead><CardTitle icon="⚠">Background Task Summary</CardTitle><Badge text={overallTask.failed || overallTask.timed_out ? 'Requires administrator attention' : 'No failed tasks'} color={overallTask.failed || overallTask.timed_out ? 'amber' : 'green'} /></CardHead>
        <CardBody>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
            {([
      ['Pending', overallTask.pending],
      ['Processing', overallTask.processing],
      ['Completed', overallTask.completed],
              ['Failed', overallTask.failed],
              ['Timed out', overallTask.timed_out],
            ] as const).map(([label, value]) => (
              <div key={label} style={{ background: '#F8FAFC', borderRadius: 6, padding: '9px 10px' }}>
                <div style={{ fontSize: 9, color: '#6B7280' }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: value && (label === 'Failed' || label === 'Timed out') ? '#DC2626' : '#111827' }}>{value}</div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      <WarnBox>
      <strong>Fault isolation:</strong> The RAG page displays status in read-only mode. Upstream consumer, business, and creator systems do not depend on page actions. Production sync, retries, and rebuilds are handled by backend maintenance APIs or the upstream outbox.
      </WarnBox>
    </div>
  )
}
