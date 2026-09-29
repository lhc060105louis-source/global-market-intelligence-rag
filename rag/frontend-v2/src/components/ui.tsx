import type { ReactNode, CSSProperties } from 'react'

export function Card({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{
      background: '#fff', border: '0.5px solid var(--border)', borderRadius: 9,
      overflow: 'hidden', marginBottom: 12, ...style,
    }}>{children}</div>
  )
}

export function CardHead({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{
      padding: '10px 14px', borderBottom: '0.5px solid #F1F5F9',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', ...style,
    }}>{children}</div>
  )
}

export function CardBody({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div style={{ padding: 14, ...style }}>{children}</div>
}

export function CardTitle({ icon, children }: { icon?: string; children: ReactNode }) {
  return (
    <span style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'flex', alignItems: 'center', gap: 6 }}>
      {icon && <span style={{ color: '#2563EB', fontStyle: 'normal' }}>{icon}</span>}
      {children}
    </span>
  )
}

export function MetricCard({
  label, value, sub, iconBg, iconColor, iconText, change, changeColor,
}: {
  label: string; value: string | number; sub?: string;
  iconBg?: string; iconColor?: string; iconText?: string;
  change?: string; changeColor?: string;
}) {
  return (
    <div style={{ background: '#fff', border: '0.5px solid var(--border)', borderRadius: 9, padding: 14, position: 'relative' }}>
      {iconText && (
        <div style={{
          width: 32, height: 32, borderRadius: 7, background: iconBg || '#EFF6FF',
          color: iconColor || '#2563EB', display: 'flex', alignItems: 'center',
          justifyContent: 'center', float: 'right', marginTop: -2, fontSize: 14, fontWeight: 700,
        }}>{iconText}</div>
      )}
      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 5 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, lineHeight: 1, marginBottom: 4 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: '#9CA3AF' }}>{sub}</div>}
      {change && <div style={{ fontSize: 10, fontWeight: 500, marginTop: 2, color: changeColor || '#6B7280' }}>{change}</div>}
    </div>
  )
}

export function Badge({ text, color }: { text: string; color: 'green' | 'blue' | 'amber' | 'red' | 'purple' | 'gray' }) {
  const map = {
    green: { bg: '#ECFDF5', c: '#047857', b: 'rgba(4,120,87,0.25)' },
    blue: { bg: '#EFF6FF', c: '#1D4ED8', b: 'rgba(37,99,235,0.25)' },
    amber: { bg: '#FFFBEB', c: '#92400E', b: 'rgba(180,83,9,0.25)' },
    red: { bg: '#FEF2F2', c: '#991B1B', b: 'rgba(185,28,28,0.25)' },
    purple: { bg: '#F5F0FF', c: '#6D28D9', b: 'rgba(109,40,217,0.25)' },
    gray: { bg: '#F8FAFC', c: '#4B5563', b: 'var(--border)' },
  }
  const s = map[color]
  return (
    <span style={{
      fontSize: 10, fontWeight: 500, padding: '2px 7px', borderRadius: 20,
      border: `0.5px solid ${s.b}`, background: s.bg, color: s.c,
      display: 'inline-block', whiteSpace: 'nowrap',
    }}>{text}</span>
  )
}

export function DomainMark({ domain }: { domain: 'C' | 'B' | 'K' }) {
  const map = {
    C: { bg: '#ECFDF5', c: '#047857' },
    B: { bg: '#EFF6FF', c: '#1D4ED8' },
    K: { bg: '#F5F0FF', c: '#6D28D9' },
  }
  const s = map[domain]
  return (
    <span style={{
      width: 24, height: 20, borderRadius: 5, display: 'inline-flex',
      alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 700,
      background: s.bg, color: s.c, flexShrink: 0,
    }}>{domain}</span>
  )
}

export function InfoBox({ children }: { children: ReactNode }) {
  return (
    <div style={{
      background: '#EFF6FF', border: '0.5px solid rgba(37,99,235,0.25)', borderRadius: 6,
      padding: '10px 12px', fontSize: 11, color: '#1E40AF', lineHeight: 1.65, marginBottom: 12,
    }}>{children}</div>
  )
}

export function WarnBox({ children }: { children: ReactNode }) {
  return (
    <div style={{
      background: '#FFFBEB', border: '0.5px solid rgba(180,83,9,0.25)', borderRadius: 6,
      padding: '10px 12px', fontSize: 11, color: '#92400E', lineHeight: 1.65, marginBottom: 12,
    }}>{children}</div>
  )
}

export function BtnPrimary({ children, onClick, disabled, style }: { children: ReactNode; onClick?: () => void; disabled?: boolean; style?: CSSProperties }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        fontSize: 12, padding: '6px 14px', borderRadius: 6,
        background: disabled ? '#93C5FD' : '#2563EB', color: '#fff', border: 'none',
        display: 'inline-flex', alignItems: 'center', gap: 5,
        cursor: disabled ? 'not-allowed' : 'pointer', ...style,
      }}
    >{children}</button>
  )
}

export function BtnOutline({ children, onClick, active, style }: { children: ReactNode; onClick?: () => void; active?: boolean; style?: CSSProperties }) {
  return (
    <button
      onClick={onClick}
      style={{
        fontSize: 11, padding: '5px 10px', borderRadius: 5,
        border: `0.5px solid ${active ? '#93C5FD' : 'var(--border)'}`,
        background: active ? '#EFF6FF' : '#fff',
        color: active ? '#1D4ED8' : '#374151',
        display: 'inline-flex', alignItems: 'center', gap: 5, ...style,
      }}
    >{children}</button>
  )
}

export function SectionNote({ children }: { children: ReactNode }) {
  return <span style={{ fontSize: 10, color: '#94A3B8' }}>{children}</span>
}

export function Grid4({ children }: { children: ReactNode }) {
  return <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 14 }}>{children}</div>
}

export function Grid3({ children }: { children: ReactNode }) {
  return <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, marginBottom: 12 }}>{children}</div>
}

export function Grid2({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12, ...style }}>{children}</div>
}

export function PriorityTag({ level }: { level: 'P0' | 'P1' | 'P2' }) {
  const c = level === 'P0' ? { bg: '#FEF2F2', color: '#991B1B' } : level === 'P1' ? { bg: '#FEF2F2', color: '#B91C1C' } : { bg: '#FFFBEB', color: '#92400E' }
  return (
    <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4, background: c.bg, color: c.color }}>{level}</span>
  )
}
