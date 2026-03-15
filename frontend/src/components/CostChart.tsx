'use client'
import { useEffect, useRef } from 'react'
import { createChart, ColorType, AreaSeries } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, LineData, AutoscaleInfo } from 'lightweight-charts'
import Panel from '@/components/Panel'
import type { CostPoint } from '@/hooks/useSimulation'
import type { CSSProperties } from 'react'

const COLORS = { dump: '#FF1744', twap: '#FFD600', vwap: '#C77DFF', ac: '#00C853' }

function toRgba(hex: string, alpha: number) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

function dedupeByTime<T extends { time: number }>(arr: T[]): T[] {
  const sorted = [...arr].sort((a, b) => a.time - b.time)
  return sorted.filter((d, i) => i === 0 || d.time !== sorted[i - 1].time)
}

type SeriesRefs = { dump: ISeriesApi<'Area'> | null; twap: ISeriesApi<'Area'> | null; vwap: ISeriesApi<'Area'> | null; ac: ISeriesApi<'Area'> | null }

export default function CostChart({ data, style }: { data: CostPoint[]; style?: CSSProperties }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const refs = useRef<SeriesRefs>({ dump: null, twap: null, vwap: null, ac: null })
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

    const autoscaleInfoProvider = (original: () => AutoscaleInfo | null) => {
      const res = original()
      if (res === null) return null
      return {
        priceRange: { minValue: Math.min(res.priceRange.minValue, 0), maxValue: res.priceRange.maxValue },
        margins: res.margins,
      }
    }

    const mkArea = (key: keyof typeof COLORS, title: string) => chart.addSeries(AreaSeries, {
      lineColor: COLORS[key],
      topColor: toRgba(COLORS[key], 0.15),
      bottomColor: toRgba(COLORS[key], 0),
      lineWidth: 1,
      priceLineVisible: false,
      title,
      autoscaleInfoProvider,
    })

    refs.current.dump = mkArea('dump', 'DUMP')
    refs.current.twap = mkArea('twap', 'TWAP')
    refs.current.vwap = mkArea('vwap', 'VWAP')
    refs.current.ac   = mkArea('ac',   'AC')
    chartRef.current = chart
    prevLenRef.current = 0
    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.resize(containerRef.current.clientWidth, containerRef.current.clientHeight)
    })
    ro.observe(containerRef.current)
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; refs.current = { dump: null, twap: null, vwap: null, ac: null } }
  }, [])

  useEffect(() => {
    const { dump, twap, vwap, ac } = refs.current
    if (!dump || !twap || !vwap || !ac) return
    if (!data.length) { dump.setData([]); twap.setData([]); vwap.setData([]); ac.setData([]); prevLenRef.current = 0; return }
    const dd = dedupeByTime(data)
    if (dd.length < prevLenRef.current || prevLenRef.current === 0 || dd.length > prevLenRef.current + 1) {
      dump.setData(dd.map(d => ({ time: d.time as LineData['time'], value: d.dump })))
      twap.setData(dd.map(d => ({ time: d.time as LineData['time'], value: d.twap })))
      vwap.setData(dd.map(d => ({ time: d.time as LineData['time'], value: d.vwap })))
      ac.setData(dd.map(d => ({ time: d.time as LineData['time'], value: d.ac })))
    } else {
      const last = dd[dd.length - 1]
      dump.update({ time: last.time as LineData['time'], value: last.dump })
      twap.update({ time: last.time as LineData['time'], value: last.twap })
      vwap.update({ time: last.time as LineData['time'], value: last.vwap })
      ac.update({ time: last.time as LineData['time'], value: last.ac })
    }
    prevLenRef.current = dd.length
  }, [data])

  const latest = data.length ? data[data.length - 1] : null
  const legend = (
    <div style={{ display: 'flex', gap: '10px' }}>
      {(['dump', 'twap', 'vwap', 'ac'] as const).map(k => (
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
