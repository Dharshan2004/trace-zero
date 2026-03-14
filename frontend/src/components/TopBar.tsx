'use client'
import { useState, useEffect } from 'react'
import type { SimStatus } from '@/hooks/useSimulation'
import type { CSSProperties } from 'react'

interface TopBarProps {
  symbol: string
  status: SimStatus
  dataMode?: 'l2_real' | 'l2_synthetic' | 'l1' | null
  style?: CSSProperties
}

function formatTime(d: Date) {
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map(n => String(n).padStart(2, '0')).join(':')
}

function formatDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

const STATUS_CONFIG: Record<SimStatus, { label: string; color: string }> = {
  idle:     { label: 'IDLE',     color: '#888888' },
  running:  { label: 'RUNNING',  color: '#FF8C00' },
  complete: { label: 'COMPLETE', color: '#00C853' },
  error:    { label: 'ERROR',    color: '#FF1744' },
}

const DATA_MODE_CONFIG = {
  l2_real:      { label: 'L2 LIVE', color: '#00C853' },
  l2_synthetic: { label: 'L2 SYN',  color: '#FF8C00' },
  l1:           { label: 'L1',      color: '#FF1744' },
}

export default function TopBar({ symbol, status, dataMode, style }: TopBarProps) {
  const [now, setNow] = useState(new Date())
  const [blink, setBlink] = useState(true)

  useEffect(() => {
    const t = setInterval(() => { setNow(new Date()); setBlink(b => !b) }, 1000)
    return () => clearInterval(t)
  }, [])

  const { label, color } = STATUS_CONFIG[status]

  return (
    <div style={{
      background: '#0a0a0a', borderBottom: '1px solid #FF8C00',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 10px', height: '32px', flexShrink: 0, ...style,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <span style={{ color: '#FF8C00', fontWeight: 700, fontSize: '13px', letterSpacing: '0.15em' }}>TRACE-ZERO</span>
        <span style={{ color: '#444' }}>|</span>
        <span style={{ color: '#fff', fontSize: '12px' }}>{symbol}</span>
        <span style={{ color: '#444' }}>|</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ display: 'inline-block', width: 6, height: 6, background: color, opacity: status === 'running' ? (blink ? 1 : 0.2) : 1 }} />
          <span style={{ color, fontSize: '11px', fontWeight: 700, letterSpacing: '0.1em' }}>{label}</span>
        </div>
        {dataMode && (() => {
          const dm = DATA_MODE_CONFIG[dataMode]
          return (
            <>
              <span style={{ color: '#444' }}>|</span>
              <span style={{ color: dm.color, fontSize: '10px', fontWeight: 700, letterSpacing: '0.08em', border: `1px solid ${dm.color}`, padding: '1px 4px' }}>{dm.label}</span>
            </>
          )
        })()}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <span style={{ color: '#555', fontSize: '10px' }}>OPTIMAL EXECUTION SIMULATOR</span>
        <span style={{ color: '#444' }}>|</span>
        <span style={{ color: '#888', fontSize: '11px' }}>{formatDate(now)}</span>
        <span style={{ color: '#FF8C00', fontSize: '11px' }}>{formatTime(now)}</span>
      </div>
    </div>
  )
}
