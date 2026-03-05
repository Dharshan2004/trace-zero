'use client'
import type { CSSProperties } from 'react'
import Panel from '@/components/Panel'
import type { TearSheetResult } from '@/hooks/useSimulation'

interface Props { result: TearSheetResult | null; symbol?: string; style?: CSSProperties }

const STRATS = ['dump', 'twap', 'ac'] as const
type S = typeof STRATS[number]
const LABELS: Record<S, string> = { dump: 'DUMP', twap: 'TWAP', ac: 'AC OPT' }

const fmt = (v: number|undefined, d=2) => v == null || isNaN(v) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })
const fmtBps = (v: number|undefined) => v == null || isNaN(v) ? '—' : `${v.toFixed(1)} bp`
const fmtSav = (v: number|undefined) => v == null || isNaN(v) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)} bp`

const cell: CSSProperties = { padding: '5px 6px', borderBottom: '1px solid #1a1a1a', borderRight: '1px solid #1a1a1a', fontVariantNumeric: 'tabular-nums', fontSize: '11px', textAlign: 'right', whiteSpace: 'nowrap' }
const hcell: CSSProperties = { ...cell, color: '#FF8C00', fontWeight: 700, fontSize: '10px', textAlign: 'center', background: '#0f0f0f', letterSpacing: '0.08em' }
const lcell: CSSProperties = { ...cell, color: '#888', fontSize: '10px', textAlign: 'left', whiteSpace: 'pre', letterSpacing: '0.06em' }

export default function TearSheet({ result, symbol = 'BTCUSDT', style }: Props) {
  type Row = { label: string; vals: string[]; best: number|null; worst: number|null; savings?: boolean }

  function rows(): Row[] {
    if (!result) return [
      { label: 'VWAP',      vals: ['—','—','—'], best: null, worst: null },
      { label: 'SHORTFALL', vals: ['—','—','—'], best: null, worst: null },
      { label: 'VARIANCE',  vals: ['—','—','—'], best: null, worst: null },
      { label: 'UTILITY',   vals: ['—','—','—'], best: null, worst: null },
      { label: 'SAVINGS\nVS DUMP', vals: ['—','—','—'], best: null, worst: null, savings: true },
    ]
    const { dump, twap, ac } = result
    const idxMin = (a: number[]) => a.indexOf(Math.min(...a))
    const idxMax = (a: number[]) => a.indexOf(Math.max(...a))
    const vwaps = [dump.vwap, twap.vwap, ac.vwap]
    const sfs   = [dump.shortfall_bps, twap.shortfall_bps, ac.shortfall_bps]
    const vars  = [dump.variance, twap.variance, ac.variance]
    const utils = [dump.utility, twap.utility, ac.utility]
    return [
      { label: 'VWAP',      vals: [fmt(dump.vwap), fmt(twap.vwap), fmt(ac.vwap)],         best: idxMax(vwaps), worst: idxMin(vwaps) },
      { label: 'SHORTFALL', vals: [fmtBps(dump.shortfall_bps), fmtBps(twap.shortfall_bps), fmtBps(ac.shortfall_bps)], best: idxMin(sfs), worst: idxMax(sfs) },
      { label: 'VARIANCE',  vals: [fmt(dump.variance), fmt(twap.variance), fmt(ac.variance)], best: idxMin(vars), worst: idxMax(vars) },
      { label: 'UTILITY',   vals: [fmt(dump.utility), fmt(twap.utility), fmt(ac.utility)],   best: idxMin(utils), worst: idxMax(utils) },
      { label: 'SAVINGS\nVS DUMP', vals: ['—', fmtSav((twap.shortfall_bps - dump.shortfall_bps) * -1), fmtSav(result.ac_savings_vs_dump_bps)], best: null, worst: null, savings: true },
    ]
  }

  return (
    <Panel title="EXECUTION TEAR SHEET" style={style} rightHeader={<span style={{ color: '#888', fontSize: '10px' }}>{symbol}</span>}>
      <div style={{ overflow: 'auto', height: '100%' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          <colgroup><col style={{ width: '34%' }} />{STRATS.map(s => <col key={s} style={{ width: '22%' }} />)}</colgroup>
          <thead>
            <tr>
              <th style={{ ...hcell, textAlign: 'left' }}>METRIC</th>
              {STRATS.map(s => <th key={s} style={hcell}>{LABELS[s]}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows().map((row, ri) => (
              <tr key={ri} style={{ background: ri % 2 === 0 ? '#000' : '#050505' }}>
                <td style={lcell}>{row.label}</td>
                {row.vals.map((v, ci) => {
                  let color = '#fff'
                  if (result) {
                    if (row.savings) { if (v !== '—' && v.startsWith('+')) color = '#00C853' }
                    else { if (row.best === ci) color = '#00C853'; if (row.worst === ci) color = '#FF1744' }
                  }
                  return <td key={ci} style={{ ...cell, color }}>{v}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {result && (
          <div style={{ margin: '8px 6px', padding: '6px 8px', border: '1px solid #1a4a1a', background: '#001800' }}>
            <div style={{ color: '#555', fontSize: '9px', letterSpacing: '0.08em', marginBottom: '4px' }}>AC OPTIMAL SAVINGS SUMMARY</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '3px' }}>
              <span style={{ color: '#888', fontSize: '10px' }}>VS DUMP</span>
              <span style={{ color: '#00C853', fontSize: '11px' }}>{fmtSav(result.ac_savings_vs_dump_bps)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#888', fontSize: '10px' }}>VS TWAP</span>
              <span style={{ color: '#00C853', fontSize: '11px' }}>{fmtSav(result.ac_savings_vs_twap_bps)}</span>
            </div>
          </div>
        )}
        {!result && (
          <div style={{ margin: '12px 8px', padding: '8px', border: '1px solid #1a1a1a', textAlign: 'center' }}>
            <span style={{ color: '#333', fontSize: '10px', letterSpacing: '0.1em' }}>SET PARAMETERS AND PRESS GO</span>
          </div>
        )}
      </div>
    </Panel>
  )
}
