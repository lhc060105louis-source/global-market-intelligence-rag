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
  { id: 'c_current', target: 'c_current', recordMode: 'current', label: 'C端消费者评论与车主反馈（当前）', domain: 'C' },
  { id: 'c_history', target: 'c_history', recordMode: 'snapshot', label: 'C端历史快照知识库', domain: 'C' },
  { id: 'b_business', target: 'b_business', recordMode: 'current', label: 'B端商业情报与政策法规', domain: 'B' },
  { id: 'kol', target: 'kol', recordMode: 'current', label: 'KOL端达人与合作信息', domain: 'K' },
]

function latestRecordTime(records: RagRecord[]): string {
  return records.reduce((latest, record) => {
    const value = record.updated_at || record.source_updated_at || record.effective_at
    return !latest || new Date(value).valueOf() > new Date(latest).valueOf() ? value : latest
  }, '')
}

function statusLabel(status: ViewStatus): { text: string; color: 'green' | 'blue' | 'red'; dot: string } {
  if (status === 'error') return { text: '有失败任务', color: 'red', dot: '#DC2626' }
  if (status === 'syncing') return { text: '后台处理中', color: 'blue', dot: '#2563EB' }
  return { text: '正常', color: 'green', dot: '#059669' }
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
      if (!controller.signal.aborted) setError(errorValue instanceof Error ? errorValue.message : '数据状态读取失败')
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
    showToast('已刷新后台同步状态')
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px 40px' }}>
      <Grid4>
        <MetricCard label="当前来源正常率" value={sources.length ? `${Math.round((healthyCount / sources.length) * 100)}%` : '—'} sub={`${healthyCount}/${sources.length || '—'} 个来源正常`} iconBg="#ECFDF5" iconColor="#059669" iconText="✓" />
        <MetricCard label="有效知识条目" value={loading ? '—' : totalKnowledge.toLocaleString()} sub="FastAPI 主库当前记录" iconBg="#EFF6FF" iconColor="#2563EB" iconText="▤" />
        <MetricCard label="失败或超时任务" value={loading ? '—' : overallTask.failed + overallTask.timed_out} sub="后台维护状态" iconBg={errorCount ? '#FEF2F2' : '#ECFDF5'} iconColor={errorCount ? '#DC2626' : '#059669'} iconText={errorCount ? '✕' : '✓'} />
        <MetricCard label="最近来源变更" value={latest ? formatDateTime(latest) : '—'} sub="按主库更新时间" iconBg="#F5F0FF" iconColor="#7C3AED" iconText="⇄" />
      </Grid4>

      {error && <WarnBox><strong>状态读取失败：</strong>{error}</WarnBox>}
      {loading && <InfoBox>正在读取当前记录和后台同步任务状态…</InfoBox>}

      <Card>
        <CardHead>
          <CardTitle icon="⇄">同步状态</CardTitle>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Badge text="后台自动维护" color="blue" />
            <button onClick={refreshStatus} disabled={loading} style={{ fontSize: 11, padding: '5px 10px', borderRadius: 5, border: '0.5px solid var(--border)', background: '#F8FAFC', color: '#374151', cursor: loading ? 'not-allowed' : 'pointer' }}>↻ 刷新状态</button>
          </div>
        </CardHead>
        <CardBody>
          <div style={{ fontSize: 11, color: '#6B7280', lineHeight: 1.7 }}>
            C、B、KOL 的数据推送和 MaxKB 同步由后端任务处理；前端只读取状态，不直接触发同步或重同步。
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginTop: 10 }}>
            {['三端接收', '版本校验', '主库入账', '后台同步 MaxKB', '索引状态回写'].map((step, index, all) => (
              <span key={step} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ background: '#F8FAFC', border: '0.5px solid var(--border)', borderRadius: 6, padding: '5px 10px', fontSize: 10, color: '#374151' }}>{step}</span>
                {index < all.length - 1 && <span style={{ color: '#94A3B8' }}>→</span>}
              </span>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHead><CardTitle icon="▤">三端数据状态</CardTitle><SectionNote>{loading ? '读取中…' : '数据来自正式 RAG Hub 接口'}</SectionNote></CardHead>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr>
              {['数据来源', '有效记录', '最近变更', '状态', '已完成任务', '失败 / 超时'].map(title => (
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
                    <td style={{ padding: '10px 12px', borderBottom: '0.5px solid #F1F5F9', fontSize: 12 }}>{source.knowledge.toLocaleString()} 条</td>
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
        <CardHead><CardTitle icon="⚠">后台任务摘要</CardTitle><Badge text={overallTask.failed || overallTask.timed_out ? '需后台关注' : '无失败任务'} color={overallTask.failed || overallTask.timed_out ? 'amber' : 'green'} /></CardHead>
        <CardBody>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
            {([
              ['待处理', overallTask.pending],
              ['处理中', overallTask.processing],
              ['已完成', overallTask.completed],
              ['失败', overallTask.failed],
              ['超时', overallTask.timed_out],
            ] as const).map(([label, value]) => (
              <div key={label} style={{ background: '#F8FAFC', borderRadius: 6, padding: '9px 10px' }}>
                <div style={{ fontSize: 9, color: '#6B7280' }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: value && (label === '失败' || label === '超时') ? '#DC2626' : '#111827' }}>{value}</div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      <WarnBox>
        <strong>故障隔离说明：</strong>RAG 页面只读展示状态；C、B、KOL 上游系统不依赖页面操作。正式同步、重试和重建由后台维护接口或上游 Outbox 执行。
      </WarnBox>
    </div>
  )
}
