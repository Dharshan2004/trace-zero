'use client'
import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import Panel from '@/components/Panel'
import type { FillEvent } from '@/hooks/useSimulation'

const STRAT_COLORS: Record<string, string> = { dump: '#FF1744', twap: '#FFD600', ac: '#00C853' }

function fmtTime(ms: number) {
  const d = new Date(ms)
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map(n => String(n).padStart(2,'0')).join(':') +
    '.' + String(d.getMilliseconds()).padStart(3,'0')
}

const th: CSSProperties = { padding: '3px 8px', color: '#FF8C00', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', borderBottom: '1px solid #333', borderRight: '1px solid #1a1a1a', textAlign: 'left', whiteSpace: 'nowrap', background: '#0f0f0f', position: 'sticky', top: 0, zIndex: 1 }
const td: CSSProperties = { padding: '2px 8px', fontSize: '11px', borderBottom: '1px solid #0f0f0f', borderRight: '1px solid #0f0f0f', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }

export default function OrderBlotter({ fills, style }: { fills: FillEvent[]; style?: CSSProperties }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight }, [fills])

  return (
    <Panel title="ORDER BLOTTER" style={style} rightHeader={<span style={{ color: '#555', fontSize: '10px' }}>{fills.length} FILLS</span>}>
      <div ref={scrollRef} style={{ height: '100%', overflowY: 'auto', overflowX: 'auto' }}>
        {fills.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#333', fontSize: '11px', letterSpacing: '0.1em' }}>
            NO FILLS YET
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '120px' }} /><col style={{ width: '80px' }} /><col style={{ width: '100px' }} />
              <col style={{ width: '120px' }} /><col style={{ width: '100px' }} /><col style={{ width: '120px' }} />
            </colgroup>
            <thead>
              <tr>
                <th style={th}>TIME</th><th style={th}>STRATEGY</th>
                <th style={{ ...th, textAlign: 'right' }}>QTY</th>
                <th style={{ ...th, textAlign: 'right' }}>PRICE</th>
                <th style={{ ...th, textAlign: 'right' }}>SLIPPAGE</th>
                <th style={{ ...th, textAlign: 'right', borderRight: 'none' }}>IMPACT</th>
              </tr>
            </thead>
            <tbody>
              {fills.map((fill, i) => {
                const color = STRAT_COLORS[fill.strategy.toLowerCase()] ?? '#fff'
                return (
                  <tr key={i} style={{ background: i % 2 === 0 ? '#000' : '#050505' }}>
                    <td style={{ ...td, color: '#888' }}>{fmtTime(fill.timestamp_ms)}</td>
                    <td style={{ ...td, color, fontWeight: 700 }}>{fill.strategy.toUpperCase()}</td>
                    <td style={{ ...td, color: '#fff', textAlign: 'right' }}>{fill.qty.toFixed(6)}</td>
                    <td style={{ ...td, color: '#fff', textAlign: 'right' }}>{fill.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td style={{ ...td, textAlign: 'right', color: fill.slippage_bps > 0 ? '#FF1744' : fill.slippage_bps < 0 ? '#00C853' : '#888' }}>
                      {fill.slippage_bps >= 0 ? '+' : ''}{fill.slippage_bps.toFixed(2)} bp
                    </td>
                    <td style={{ ...td, textAlign: 'right', borderRight: 'none', color: fill.temp_impact > 0 ? '#FF8C00' : '#888' }}>
                      {fill.temp_impact.toFixed(4)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </Panel>
  )
}
