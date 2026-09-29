import {
  formatDateTime,
  recordDomain,
  recordSummary,
  recordTime,
  recordTitle,
  semanticFieldInfo,
  semanticStatusLabel,
} from './api'
import type { QueryResponse, RagRecord, SemanticFieldKey } from './api'

export interface BriefEvidenceItem {
  record: RagRecord
  score: number | null
}

const SEMANTIC_FIELDS: Array<{
  key: SemanticFieldKey
  title: string
  number: string
  domainClass?: string
  value: (response: QueryResponse) => string | null
}> = [
  { key: 'summary', title: 'Summary', number: '01', value: response => response.output.summary },
  { key: 'consumer_signal', title: 'Consumer Signals', number: '02', domainClass: 'domain-c', value: response => response.output.consumer_signal },
  { key: 'business_impact', title: 'Business Impact', number: '03', domainClass: 'domain-b', value: response => response.output.business_impact },
  { key: 'kol_impact', title: 'Creator Impact', number: '04', domainClass: 'domain-k', value: response => response.output.kol_impact },
]

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderText(value: unknown, fallback = '—'): string {
  const text = String(value ?? '').trim()
  return escapeHtml(text || fallback).replace(/\r?\n/g, '<br>')
}

function renderAttribute(value: unknown): string {
  return escapeHtml(value)
}

function safeExternalUrl(value: string | null | undefined): string {
  if (!value) return ''
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : ''
  } catch {
    return ''
  }
}

function sourceLabel(source: string): string {
  if (source === 'maxkb') return 'LLM summary'
  if (source === 'deterministic') return 'Evidence-based fallback'
  if (source === 'none') return 'No domain-specific evidence'
  return 'Result returned'
}

function sourceClass(source: string): string {
  if (source === 'maxkb') return 'badge-green'
  if (source === 'deterministic') return 'badge-amber'
  if (source === 'none') return 'badge-gray'
  return 'badge-blue'
}

function semanticDisplayValue(response: QueryResponse, field: SemanticFieldKey, value: string | null): string {
  const info = semanticFieldInfo(response, field)
  if (info.source === 'none') {
    return info.notice || (field === 'actions' ? 'No action recommendations are available.' : 'No valid evidence is available for the selected scope.')
  }
  return value?.trim() || 'No summary returned.'
}

function splitActions(value: string | null | undefined): string[] {
  if (!value) return []
  return value.split(/[;\n]/).map(item => item.trim()).filter(Boolean)
}

function formatSourceSystem(domain: string): string {
  return domain === 'C' ? 'Consumer' : domain === 'B' ? 'Business' : 'Creator'
}

function formatTimestamp(value: Date): string {
  return value.toLocaleString('en-US', { hour12: true })
}

function fileTimestamp(value: Date): string {
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${value.getFullYear()}${pad(value.getMonth() + 1)}${pad(value.getDate())}-${pad(value.getHours())}${pad(value.getMinutes())}`
}

function renderSemanticBadge(response: QueryResponse, field: SemanticFieldKey): string {
  const info = semanticFieldInfo(response, field)
  return `<span class="badge ${sourceClass(info.source)}">${sourceLabel(info.source)}</span>`
}

function renderDomainCard(response: QueryResponse, field: SemanticFieldKey, title: string, domain: string, value: string | null): string {
  const info = semanticFieldInfo(response, field)
  return `
    <article class="domain-card ${domain === 'C' ? 'domain-c' : domain === 'B' ? 'domain-b' : 'domain-k'}">
      <div class="domain-card-head">
        <span class="domain-mark">${domain}</span>
        <h3>${escapeHtml(title)}</h3>
        ${renderSemanticBadge(response, field)}
      </div>
      <p>${renderText(semanticDisplayValue(response, field, value))}</p>
      ${info.notice && info.source !== 'none' ? `<div class="field-note">${renderText(info.notice)}</div>` : ''}
    </article>`
}

function evidenceDomain(target: string): string {
  if (target.startsWith('c_')) return 'C'
  if (target.startsWith('b_')) return 'B'
  if (target === 'kol') return 'K'
  return '—'
}

function renderEvidence(response: QueryResponse, evidence: BriefEvidenceItem[]): string {
  const references = response.output.evidence || []
  const detailedIds = new Set(evidence.flatMap(item => [item.record.id, item.record.source_record_id]))
  const referenceOnly = references.filter(reference => !detailedIds.has(reference.record_id))
  const total = Math.max(evidence.length, new Set([
    ...evidence.map(item => item.record.id),
    ...references.map(reference => reference.record_id),
  ]).size)
  if (!evidence.length && !referenceOnly.length) return '<div class="empty">No traceable evidence is available for this query.</div>'

  return `<div class="evidence-summary">${escapeHtml(total)} references; ${escapeHtml(evidence.length)} record details loaded${referenceOnly.length ? `; metadata retained for ${escapeHtml(referenceOnly.length)} additional references` : ''}.</div>
  <div class="evidence-list">
    ${evidence.map((item, index) => {
      const record = item.record
      const sourceUrl = safeExternalUrl(record.source_url)
      const score = typeof item.score === 'number' ? item.score.toFixed(2) : '—'
      const date = formatDateTime(recordTime(record))
      return `<article class="evidence-item">
        <div class="evidence-index">${String(index + 1).padStart(2, '0')}</div>
        <div class="evidence-main">
          <div class="evidence-title-row">
            <span class="domain-mark small">${escapeHtml(recordDomain(record))}</span>
            <h3>${escapeHtml(recordTitle(record))}</h3>
            <span class="score">Relevance ${escapeHtml(score)}</span>
          </div>
          <p>${renderText(recordSummary(record), 'No summary available.')}</p>
          <div class="evidence-meta">
            <span>${escapeHtml(formatSourceSystem(record.source_system))}</span>
            <span>Business date: ${escapeHtml(date)}</span>
            <span>Version: ${escapeHtml(record.source_version)}</span>
            <span>Knowledge base: ${escapeHtml(record.target_knowledge_base)}</span>
            ${sourceUrl ? `<a href="${renderAttribute(sourceUrl)}" target="_blank" rel="noreferrer">Open source</a>` : ''}
          </div>
        </div>
      </article>`
    }).join('')}
    ${referenceOnly.map((reference, index) => {
      const displayIndex = evidence.length + index
      const score = typeof reference.score === 'number' ? reference.score.toFixed(2) : '—'
      const domain = evidenceDomain(reference.target_knowledge_base)
      return `<article class="evidence-item reference-only">
        <div class="evidence-index">${String(displayIndex + 1).padStart(2, '0')}</div>
        <div class="evidence-main">
          <div class="evidence-title-row">
            <span class="domain-mark small">${escapeHtml(domain)}</span>
            <h3>Referenced record ${renderText(reference.record_id)}</h3>
            <span class="score">Relevance ${escapeHtml(score)}</span>
          </div>
          <p>Record details were not loaded on this page. Traceability metadata is retained for this reference.</p>
          <div class="evidence-meta">
            <span>Knowledge base: ${escapeHtml(reference.target_knowledge_base)}</span>
            <span>Version: ${escapeHtml(reference.source_version)}</span>
          </div>
        </div>
      </article>`
    }).join('')}
  </div>`
}

function renderDataTimes(response: QueryResponse): string {
  const values = (response.output.data_time || []).filter(value => value && value.trim())
  if (!values.length) return '<span class="empty-inline">The response does not include a specific data time.</span>'
  return values.map(value => `<span class="time-chip">${renderText(value)}</span>`).join('')
}

function renderActions(response: QueryResponse): string {
  const actions = splitActions(response.output.action_recommendations)
  if (!actions.length) return '<div class="empty">No action recommendations are available.</div>'
  return `<ol class="action-list">${actions.map((action, index) => `<li><span class="action-number">${index + 1}</span><span>${renderText(action)}</span></li>`).join('')}</ol>`
}

function renderMetaValue(value: unknown): string {
  return escapeHtml(value === null || value === undefined || value === '' ? '—' : value)
}

export function buildBriefHtml(response: QueryResponse, evidence: BriefEvidenceItem[], generatedAt = new Date()): string {
  const output = response.output
  const status = semanticStatusLabel(response)
  const generatedTime = formatTimestamp(generatedAt)
  const title = `RAG Query Brief - ${response.query}`
  const fields = SEMANTIC_FIELDS
    .filter(field => field.key !== 'summary')
    .map(field => renderDomainCard(response, field.key, field.title, field.domainClass === 'domain-c' ? 'C' : field.domainClass === 'domain-b' ? 'B' : 'K', field.value(response)))
    .join('')
  const degradedReason = response.query_meta.degraded_reason
    ? `<span>Fallback reason: ${renderText(response.query_meta.degraded_reason)}</span>`
    : ''

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(title)}</title>
  <style>
    :root {
      --background: #eef2f7;
      --card: #ffffff;
      --text: #111827;
      --muted: #6b7280;
      --border: #e2e8f0;
      --blue: #2563eb;
      --blue-soft: #eff6ff;
      --green: #059669;
      --green-soft: #ecfdf5;
      --amber: #b45309;
      --amber-soft: #fffbeb;
      --purple: #7c3aed;
      --purple-soft: #f5f0ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 30px 18px 48px;
      background: var(--background);
      color: var(--text);
      font-family: Inter, "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif;
      font-size: 14px;
      line-height: 1.6;
    }
    .report { max-width: 1080px; margin: 0 auto; }
    .report-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 18px; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-mark { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 9px; background: #1b2b3c; color: #fff; font-size: 18px; font-weight: 700; }
    .eyebrow { color: var(--muted); font-size: 11px; letter-spacing: .04em; }
    h1 { margin: 0; font-size: 24px; line-height: 1.3; }
    .generated { color: var(--muted); font-size: 11px; text-align: right; line-height: 1.7; }
    .generated strong { color: var(--text); font-size: 12px; }
    .card, .section { background: var(--card); border: 1px solid var(--border); border-radius: 10px; box-shadow: 0 2px 8px rgba(15, 23, 42, .03); }
    .card { padding: 18px 20px; margin-bottom: 14px; }
    .section { padding: 20px; margin-bottom: 14px; }
    .hero { border-top: 4px solid var(--blue); }
    .label { color: var(--muted); font-size: 10px; margin-bottom: 5px; }
    .question { margin: 0 0 16px; font-size: 17px; font-weight: 600; line-height: 1.5; }
    .meta-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; }
    .meta-item { min-width: 0; padding: 10px 11px; background: #f8fafc; border-radius: 7px; }
    .meta-value { overflow-wrap: anywhere; font-size: 12px; font-weight: 600; }
    .meta-sub { color: var(--muted); font-size: 10px; margin-top: 2px; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
    .section-title { display: flex; align-items: center; gap: 9px; }
    .section-number { color: var(--blue); font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700; }
    h2 { margin: 0; font-size: 15px; }
    h3 { margin: 0; font-size: 12px; }
    .badge { display: inline-flex; align-items: center; min-height: 21px; padding: 2px 8px; border: 1px solid transparent; border-radius: 999px; font-size: 10px; font-weight: 600; white-space: nowrap; }
    .badge-green { color: #047857; background: var(--green-soft); border-color: rgba(4, 120, 87, .2); }
    .badge-amber { color: var(--amber); background: var(--amber-soft); border-color: rgba(180, 83, 9, .2); }
    .badge-gray { color: #64748b; background: #f1f5f9; border-color: #e2e8f0; }
    .badge-blue { color: #1d4ed8; background: var(--blue-soft); border-color: rgba(37, 99, 235, .2); }
    .conclusion { padding: 16px; border-left: 3px solid var(--blue); border-radius: 6px; background: var(--blue-soft); color: #1e3a8a; font-size: 14px; line-height: 1.85; }
    .domain-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .domain-card { min-width: 0; padding: 14px; border: 1px solid var(--border); border-top: 3px solid var(--blue); border-radius: 8px; }
    .domain-card.domain-c { border-top-color: var(--green); }
    .domain-card.domain-b { border-top-color: var(--blue); }
    .domain-card.domain-k { border-top-color: var(--purple); }
    .domain-card-head, .evidence-title-row { display: flex; align-items: center; gap: 7px; }
    .domain-card-head { flex-wrap: wrap; margin-bottom: 9px; }
    .domain-card p { margin: 0; color: #4b5563; font-size: 11px; line-height: 1.8; overflow-wrap: anywhere; }
    .domain-card .badge { margin-left: auto; }
    .domain-mark { width: 24px; height: 22px; display: inline-grid; place-items: center; flex: 0 0 auto; border-radius: 5px; color: #047857; background: var(--green-soft); font-size: 10px; font-weight: 700; }
    .domain-card.domain-b .domain-mark { color: #1d4ed8; background: var(--blue-soft); }
    .domain-card.domain-k .domain-mark { color: #6d28d9; background: var(--purple-soft); }
    .domain-mark.small { width: 20px; height: 19px; font-size: 9px; }
    .field-note { margin-top: 8px; color: var(--muted); font-size: 10px; }
    .action-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
    .action-list li { display: flex; align-items: flex-start; gap: 10px; padding: 9px 10px; border-bottom: 1px solid #f1f5f9; color: #374151; font-size: 11px; line-height: 1.7; }
    .action-list li:last-child { border-bottom: 0; }
    .action-number { width: 20px; height: 20px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 5px; color: #374151; background: #f1f5f9; font-size: 10px; font-weight: 700; }
    .evidence-list { display: grid; gap: 0; }
    .evidence-item { display: flex; gap: 12px; padding: 13px 0; border-bottom: 1px solid #f1f5f9; }
    .evidence-item:last-child { border-bottom: 0; padding-bottom: 0; }
    .evidence-summary { margin-bottom: 4px; color: var(--muted); font-size: 10px; }
    .reference-only { background: #fafafa; }
    .evidence-index { width: 25px; flex: 0 0 auto; padding-top: 2px; color: #94a3b8; font-family: "JetBrains Mono", monospace; font-size: 11px; }
    .evidence-main { min-width: 0; flex: 1; }
    .evidence-title-row h3 { overflow-wrap: anywhere; }
    .score { margin-left: auto; color: #1d4ed8; background: var(--blue-soft); border-radius: 999px; padding: 2px 7px; font-size: 9px; white-space: nowrap; }
    .evidence-main p { margin: 6px 0; color: #4b5563; font-size: 10px; line-height: 1.65; overflow-wrap: anywhere; }
    .evidence-meta { display: flex; flex-wrap: wrap; gap: 5px 12px; color: #94a3b8; font-size: 9px; }
    .evidence-meta a { color: var(--blue); text-decoration: none; }
    .evidence-meta a:hover { text-decoration: underline; }
    .time-list { display: flex; flex-wrap: wrap; gap: 7px; }
    .time-chip { display: inline-flex; padding: 5px 9px; border: 1px solid var(--border); border-radius: 6px; background: #f8fafc; color: #374151; font-family: "JetBrains Mono", monospace; font-size: 10px; }
    .boundary { color: #92400e; background: var(--amber-soft); border: 1px solid rgba(180, 83, 9, .2); border-radius: 7px; padding: 12px 14px; font-size: 11px; line-height: 1.75; }
    .trace { display: flex; flex-wrap: wrap; gap: 6px 15px; margin-top: 12px; color: var(--muted); font-size: 10px; }
    .empty, .empty-inline { color: var(--muted); font-size: 11px; }
    .footer { padding: 5px 2px; color: #94a3b8; font-size: 10px; line-height: 1.7; }
    @media (max-width: 720px) {
      body { padding: 18px 10px 30px; }
      .report-header { display: block; }
      .generated { margin-top: 10px; text-align: left; }
      .meta-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .domain-grid { grid-template-columns: 1fr; }
      .section, .card { padding: 15px; }
    }
    @media print {
      body { padding: 0; background: #fff; }
      .card, .section { box-shadow: none; break-inside: avoid; }
      .section { break-inside: auto; }
      .evidence-item { break-inside: avoid; }
    }
  </style>
</head>
<body>
  <main class="report">
    <header class="report-header">
      <div class="brand">
        <span class="brand-mark">R</span>
        <div><div class="eyebrow">Global RAG Hub</div><h1>Query Brief</h1></div>
      </div>
      <div class="generated"><strong>Generated</strong><br>${escapeHtml(generatedTime)}<br>Based on valid evidence returned for this query</div>
    </header>

    <section class="card hero">
      <div class="label">Question</div>
      <p class="question">${renderText(response.query)}</p>
      <div class="meta-grid">
        <div class="meta-item"><div class="label">Query Scope</div><div class="meta-value">${renderText(response.selected_targets.join(', '))}</div></div>
        <div class="meta-item"><div class="label">Query Status</div><div class="meta-value">${escapeHtml(status)}</div><div class="meta-sub">${renderText(response.query_meta.generation_source)}</div></div>
        <div class="meta-item"><div class="label">Valid Evidence</div><div class="meta-value">${renderMetaValue(response.evidence_count)} items</div><div class="meta-sub">Evidence</div></div>
        <div class="meta-item"><div class="label">Total Duration</div><div class="meta-value">${renderMetaValue(response.query_meta.total_ms)} ms</div><div class="meta-sub">Retrieval ${renderMetaValue(response.query_meta.retrieval_ms)} ms · Generation ${renderMetaValue(response.query_meta.generation_ms)} ms</div></div>
      </div>
      <div class="trace"><span>Response generation: ${escapeHtml(status)}</span>${degradedReason}</div>
    </section>

    <section class="section">
      <div class="section-head"><div class="section-title"><span class="section-number">01</span><h2>Summary</h2></div>${renderSemanticBadge(response, 'summary')}</div>
      <div class="conclusion">${renderText(semanticDisplayValue(response, 'summary', output.summary))}</div>
    </section>

    <section class="section">
      <div class="section-head"><div class="section-title"><span class="section-number">02—04</span><h2>Domain Analysis</h2></div><span class="label" style="margin:0">Each domain is based only on its supporting evidence.</span></div>
      <div class="domain-grid">${fields}</div>
    </section>

    <section class="section">
      <div class="section-head"><div class="section-title"><span class="section-number">05</span><h2>Action Recommendations</h2></div><span class="label" style="margin:0">Generated from the evidence for this query</span></div>
      ${renderActions(response)}
    </section>

    <section class="section">
      <div class="section-head"><div class="section-title"><span class="section-number">06</span><h2>Evidence</h2></div><span class="label" style="margin:0">${escapeHtml(evidence.length)} details</span></div>
      ${renderEvidence(response, evidence)}
    </section>

    <section class="section">
      <div class="section-head"><div class="section-title"><span class="section-number">07</span><h2>Data Time</h2></div></div>
      <div class="time-list">${renderDataTimes(response)}</div>
    </section>

    <section class="section">
      <div class="section-head"><div class="section-title"><span class="section-number">08</span><h2>Limitations</h2></div></div>
      <div class="boundary">${renderText(output.limitations || 'This response is based only on active knowledge. It does not replace quality assessment, legal judgment, or formal business decisions.')}</div>
    </section>

    <footer class="footer">This brief was generated by the Global RAG Hub. Evidence, data times, and field sources reflect the response at export time. Review the relevant notices when the status is "Evidence-based fallback" or "No domain-specific evidence."</footer>
  </main>
</body>
</html>`
}

export function downloadBriefHtml(response: QueryResponse, evidence: BriefEvidenceItem[]): void {
  const generatedAt = new Date()
  const html = buildBriefHtml(response, evidence, generatedAt)
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `rag-query-brief-${fileTimestamp(generatedAt)}.html`
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  window.setTimeout(() => {
    URL.revokeObjectURL(url)
    anchor.remove()
  }, 0)
}
