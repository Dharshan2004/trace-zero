'use client'
import type { CSSProperties } from 'react'
import Panel from '@/components/Panel'
import type { TearSheetResult } from '@/hooks/useSimulation'

interface Props { result: TearSheetResult | null; symbol?: string; style?: CSSProperties }

type S = 'dump' | 'twap' | 'vwap' | 'ac'
const STRATS: S[] = ['dump', 'twap', 'vwap', 'ac']
const LABELS: Record<S, string> = { dump: 'DUMP', twap: 'TWAP', vwap: 'VWAP', ac: 'AC OPT' }
const COLORS: Record<S, string> = { dump: '#FF1744', twap: '#FFD600', vwap: '#C77DFF', ac: '#00C853' }

const fmt = (v: number | undefined, d = 2) =>
  v == null || isNaN(v) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })
const fmtBps = (v: number | undefined) => (v == null || isNaN(v) ? '—' : `${v.toFixed(1)} bp`)
const fmtSav = (v: number | undefined) => (v == null || isNaN(v) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)} bp`)

export default function TearSheet({ result, symbol = 'BTCUSDT', style }: Props) {
  const bestIS: S | null = result
    ? STRATS.reduce((best, s) => result[s].shortfall_bps < result[best].shortfall_bps ? s : best, 'dump' as S)
    : null

  const row = (label: string, val: string, highlight?: boolean) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '3px 0', borderBottom: '1px solid #111' }}>
      <span style={{ color: '#666', fontSize: '9px', letterSpacing: '0.08em' }}>{label}</span>
      <span style={{ color: highlight ? '#00C853' : '#e0e0e0', fontSize: '11px', fontVariantNumeric: 'tabular-nums' }}>{val}</span>
    </div>
  )

  return (
    <Panel title="EXECUTION TEAR SHEET" style={style} rightHeader={<span style={{ color: '#888', fontSize: '10px' }}>{symbol}</span>}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto' }}>
        {/* 2×2 card grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1px', background: '#1a1a1a', flex: '1 1 auto' }}>
          {STRATS.map(s => {
            const data = result?.[s]
            const isBest = s === bestIS
            return (
              <div key={s} style={{
                background: isBest ? '#001800' : '#050505',
                borderLeft: `3px solid ${COLORS[s]}`,
                padding: '8px 8px 8px 10px',
              }}>
                <div style={{ color: COLORS[s], fontSize: '10px', fontWeight: 700, letterSpacing: '0.1em', marginBottom: '6px' }}>
                  {LABELS[s]}
                  {isBest && <span style={{ color: '#00C853', fontSize: '8px', marginLeft: '6px' }}>BEST IS</span>}
                </div>
                {row('VWAP', fmt(data?.vwap))}
                {row('IS', fmtBps(data?.shortfall_bps), isBest)}
                {row('VAR', fmt(data?.variance, 0))}
                {row('UTIL', fmt(data?.utility, 2))}
              </div>
            )
          })}
        </div>

        {/* AC savings summary */}
        {result ? (
          <div style={{ margin: '6px 4px', padding: '6px 8px', border: '1px solid #1a4a1a', background: '#001800', flexShrink: 0 }}>
            <div style={{ color: '#555', fontSize: '9px', letterSpacing: '0.08em', marginBottom: '4px' }}>AC OPTIMAL SAVINGS</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
              <span style={{ color: '#888', fontSize: '10px' }}>VS DUMP</span>
              <span style={{ color: '#00C853', fontSize: '11px' }}>{fmtSav(result.ac_savings_vs_dump_bps)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#888', fontSize: '10px' }}>VS TWAP</span>
              <span style={{ color: '#00C853', fontSize: '11px' }}>{fmtSav(result.ac_savings_vs_twap_bps)}</span>
            </div>
          </div>
        ) : (
          <div style={{ margin: '12px 8px', padding: '8px', border: '1px solid #1a1a1a', textAlign: 'center', flexShrink: 0 }}>
            <span style={{ color: '#333', fontSize: '10px', letterSpacing: '0.1em' }}>SET PARAMETERS AND PRESS GO</span>
          </div>
        )}
      </div>
    </Panel>
  )
}
