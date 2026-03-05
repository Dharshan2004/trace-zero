'use client'
import { useEffect, useRef } from 'react'
import { createChart, ColorType, LineSeries } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, LineData } from 'lightweight-charts'
import Panel from '@/components/Panel'
import type { CostPoint } from '@/hooks/useSimulation'
import type { CSSProperties } from 'react'

const COLORS = { dump: '#FF1744', twap: '#FFD600', ac: '#00C853' }

function dedupeByTime<T extends { time: number }>(arr: T[]): T[] {
  const sorted = [...arr].sort((a, b) => a.time - b.time)
  return sorted.filter((d, i) => i === 0 || d.time !== sorted[i-1].time)
}

export default function CostChart({ data, style }: { data: CostPoint[]; style?: CSSProperties }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const refs = useRef<{ dump: ISeriesApi<'Line'>|null; twap: ISeriesApi<'Line'>|null; ac: ISeriesApi<'Line'>|null }>({ dump: null, twap: null, ac: null })
  const prevLenRef = useRef(0)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#000' }, textColor: '#888', fontFamily: 'JetBrains Mono, monospace', fontSize: 10 },
      grid: { vertLines: { color: '#1a1a1a' }, horzLines: { color: '#1a1a1a' } },
      crosshair: { vertLine: { color: '#FF8C00', labelBackgroundColor: '#FF8C00' }, horzLine: { color: '#FF8C00', labelBackgroundColor: '#FF8C00' } },
      rightPriceScale: { borderColor: '#333' },
      timeScale: { borderColor: '#333', timeVisible: true, secondsVisible: true },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    })
    refs.current.dump = chart.addSeries(LineSeries, { color: COLORS.dump, lineWidth: 1, priceLineVisible: false, title: 'DUMP' })
    refs.current.twap = chart.addSeries(LineSeries, { color: COLORS.twap, lineWidth: 1, priceLineVisible: false, title: 'TWAP' })
    refs.current.ac   = chart.addSeries(LineSeries, { color: COLORS.ac,   lineWidth: 1, priceLineVisible: false, title: 'AC' })
    chartRef.current = chart
    prevLenRef.current = 0
    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.resize(containerRef.current.clientWidth, containerRef.current.clientHeight)
    })
    ro.observe(containerRef.current)
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; refs.current = { dump: null, twap: null, ac: null } }
  }, [])

  useEffect(() => {
    const { dump, twap, ac } = refs.current
    if (!dump || !twap || !ac) return
    if (!data.length) { dump.setData([]); twap.setData([]); ac.setData([]); prevLenRef.current = 0; return }
    const dd = dedupeByTime(data)
    if (dd.length < prevLenRef.current || prevLenRef.current === 0) {
      dump.setData(dd.map(d => ({ time: d.time as LineData['time'], value: d.dump })))
      twap.setData(dd.map(d => ({ time: d.time as LineData['time'], value: d.twap })))
      ac.setData(dd.map(d => ({ time: d.time as LineData['time'], value: d.ac })))
    } else {
      const last = dd[dd.length-1]
      dump.update({ time: last.time as LineData['time'], value: last.dump })
      twap.update({ time: last.time as LineData['time'], value: last.twap })
      ac.update({ time: last.time as LineData['time'], value: last.ac })
    }
    prevLenRef.current = dd.length
  }, [data])

  const latest = data.length ? data[data.length-1] : null
  const legend = (
    <div style={{ display: 'flex', gap: '10px' }}>
      {(['dump','twap','ac'] as const).map(k => (
        <span key={k} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ display: 'inline-block', width: 12, height: 2, background: COLORS[k] }} />
          <span style={{ color: COLORS[k], fontSize: '10px' }}>{k.toUpperCase()}</span>
          <span style={{ color: '#888', fontSize: '10px' }}>{latest ? latest[k].toFixed(2) : '—'}</span>
        </span>
      ))}
    </div>
  )
  return (
    <Panel title="IMPLEMENTATION SHORTFALL (BPS)" style={style} rightHeader={legend}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
    </Panel>
  )
}
