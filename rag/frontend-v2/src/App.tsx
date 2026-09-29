import { useState, useEffect, useRef } from 'react'
import PageQA from './pages/PageQA'
import PageAlert from './pages/PageAlert'
import PageSearch from './pages/PageSearch'
import PageDataStatus from './pages/PageDataStatus'
import { DashboardSummary, ragApi } from './lib/api'

type Page = 'qa' | 'alert' | 'search' | 'datastatus'

const NAV_ITEMS: { id: Page; label: string; icon: string; badge?: { text: string; color: string } }[] = [
  { id: 'qa', label: 'Global Q&A', icon: '⌁', badge: { text: 'RAG', color: 'blue' } },
  { id: 'alert', label: 'Alert Coordination', icon: '⚠' },
  { id: 'search', label: 'Knowledge Search', icon: '⊞', badge: { text: 'Cross-domain', color: 'gray' } },
  { id: 'datastatus', label: 'Data Status', icon: '⇄' },
]

const PAGE_TITLES: Record<Page, string> = {
  qa: 'Global Q&A',
  alert: 'Alert Coordination',
  search: 'Knowledge Search',
  datastatus: 'Data Status',
}

export default function App() {
  const [activePage, setActivePage] = useState<Page>('qa')
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [dataTime, setDataTime] = useState(() => {
    const now = new Date()
    return now.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  })
  const [serviceState, setServiceState] = useState<'loading' | 'ok' | 'error'>('loading')
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [refreshToken, setRefreshToken] = useState(0)

  function showToast(msg: string) {
    setToast(msg)
    if (toastTimer.current) clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(null), 2200)
  }

  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current) }, [])

  async function refreshData(showMessage = false) {
    const result = await Promise.allSettled([ragApi.health(), ragApi.dashboardSummary()])
    const health = result[0]
    const dashboard = result[1]
    setServiceState(health.status === 'fulfilled' && health.value.status === 'ok' ? 'ok' : 'error')
    if (dashboard.status === 'fulfilled') setSummary(dashboard.value)
    const now = new Date()
    setDataTime(now.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }))
    if (showMessage) showToast('RAG Hub data status refreshed')
  }

  useEffect(() => { void refreshData() }, [refreshToken])

  const alertBadge = summary
    ? { text: String(summary.risks.active), color: summary.risks.active > 0 ? 'red' : 'gray' }
    : { text: '—', color: 'gray' }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <nav style={{ width: 200, background: 'var(--nav)', flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '16px', borderBottom: '0.5px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 30, height: 30, background: '#2563EB', borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 15, fontWeight: 700, flexShrink: 0 }}>R</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', lineHeight: 1.3 }}>Global RAG Hub</div>
            <div style={{ fontSize: 10, color: '#64748B', marginTop: 1 }}>International Market Intelligence</div>
          </div>
        </div>

        <div style={{ padding: '10px 0', flex: 1 }}>
          <div style={{ padding: '6px 12px 4px', fontSize: 9, fontWeight: 600, color: '#475569', letterSpacing: '0.08em', textTransform: 'uppercase' }}>CORE FEATURES</div>
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              onClick={() => setActivePage(item.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 9, width: '100%',
                padding: '9px 14px', border: 0,
                borderLeft: `2px solid ${activePage === item.id ? '#2563EB' : 'transparent'}`,
                background: activePage === item.id ? 'rgba(37,99,235,0.12)' : 'transparent',
                color: activePage === item.id ? '#93C5FD' : '#94A3B8',
                fontSize: 12, textAlign: 'left', transition: 'all 0.15s',
              }}
            >
              <span style={{ width: 16, textAlign: 'center', fontSize: 14 }}>{item.icon}</span>
              <span style={{ flex: 1 }}>{item.label}</span>
              {(item.badge || item.id === 'alert') && (() => {
                const badge = item.id === 'alert' ? alertBadge : item.badge!
                return (
                <span style={{
                  fontSize: 9, padding: '1px 5px', borderRadius: 10, fontWeight: 600,
                  background: badge.color === 'red' ? '#DC2626' : badge.color === 'blue' ? '#1D4ED8' : 'rgba(255,255,255,0.1)',
                  color: badge.color === 'red' ? '#FEE2E2' : badge.color === 'blue' ? '#BFDBFE' : '#94A3B8',
                }}>{badge.text}</span>
                )
              })()}
            </button>
          ))}
        </div>

        <div style={{ padding: '10px 14px 14px', borderTop: '0.5px solid rgba(255,255,255,0.08)' }}>
          <div style={{ fontSize: 9, color: '#475569', lineHeight: 1.6 }}>
            <div style={{ color: '#64748B', marginBottom: 2 }}>All modules connected</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#059669', display: 'inline-block' }}></span>
              <span style={{ color: serviceState === 'ok' ? '#059669' : '#DC2626' }}>{serviceState === 'ok' ? 'Production API online' : 'Waiting for production API'}</span>
            </div>
            <div style={{ marginTop: 4, color: '#334155' }}>v2.0 · RAG Hub integration</div>
          </div>
        </div>
      </nav>

      {/* Main area */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Topbar */}
        <div style={{
          height: 50, flexShrink: 0, background: '#fff', borderBottom: '0.5px solid var(--border)',
          padding: '0 20px', display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{PAGE_TITLES[activePage]}</span>
          <span style={{ flex: 1 }}></span>

          <span style={{
            fontSize: 10, fontWeight: 600, padding: '3px 8px', borderRadius: 5,
            background: serviceState === 'ok' ? '#ECFDF5' : serviceState === 'loading' ? '#EFF6FF' : '#FEF2F2',
            color: serviceState === 'ok' ? '#047857' : serviceState === 'loading' ? '#1D4ED8' : '#991B1B',
            border: '0.5px solid rgba(37,99,235,0.2)',
            display: 'flex', alignItems: 'center', gap: 4,
          }}>{serviceState === 'ok' ? 'Production API connected' : serviceState === 'loading' ? 'Connecting to RAG Hub' : 'RAG Hub unavailable'}</span>

          <span style={{ fontSize: 10, color: serviceState === 'ok' ? '#059669' : '#DC2626', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: serviceState === 'ok' ? '#059669' : '#DC2626', display: 'inline-block' }}></span>
            {summary ? `${summary.knowledge.upstream_current} active records · ${summary.risks.active} active alerts` : 'Waiting for API status'}
          </span>
          <span style={{ fontSize: 10, color: '#6B7280' }}>Updated {dataTime}</span>
          <button
            style={{ fontSize: 11, padding: '5px 10px', borderRadius: 5, border: '0.5px solid var(--border)', background: '#F8FAFC', color: '#374151', display: 'flex', alignItems: 'center', gap: 4 }}
            onClick={() => setRefreshToken(value => value + 1)}
          >↻ Refresh Data</button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {activePage === 'qa' && <PageQA showToast={showToast} refreshToken={refreshToken} />}
          {activePage === 'alert' && <PageAlert showToast={showToast} refreshToken={refreshToken} />}
          {activePage === 'search' && <PageSearch showToast={showToast} refreshToken={refreshToken} />}
          {activePage === 'datastatus' && <PageDataStatus showToast={showToast} refreshToken={refreshToken} />}
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', left: '50%', bottom: 28, transform: 'translateX(-50%)',
          zIndex: 999, background: '#1F2937', color: '#fff', borderRadius: 7,
          padding: '9px 16px', fontSize: 12, boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
          display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
          animation: 'fadeIn 0.15s ease',
        }}>
          <span style={{ color: '#4ADE80' }}>✓</span> {toast}
        </div>
      )}
    </div>
  )
}
