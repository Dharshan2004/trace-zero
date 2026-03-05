'use client'
import { useEffect, useRef } from 'react'
import { createChart, ColorType, LineSeries } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, LineData } from 'lightweight-charts'
import Panel from '@/components/Panel'
import type { PricePoint, FillEvent } from '@/hooks/useSimulation'
import type { CSSProperties } from 'react'

function dedupeByTime<T extends { time: number }>(arr: T[]): T[] {
  const sorted = [...arr].sort((a, b) => a.time - b.time)
  return sorted.filter((d, i) => i === 0 || d.time !== sorted[i-1].time)
}

export default function PriceChart({ data, fills, style }: { data: PricePoint[]; fills: FillEvent[]; style?: CSSProperties }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
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
    seriesRef.current = chart.addSeries(LineSeries, { color: '#FF8C00', lineWidth: 1, priceLineVisible: false })
    chartRef.current = chart
    prevLenRef.current = 0
    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.resize(containerRef.current.clientWidth, containerRef.current.clientHeight)
    })
    ro.observe(containerRef.current)
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; seriesRef.current = null }
  }, [])

  useEffect(() => {
    if (!seriesRef.current) return
    if (!data.length) { seriesRef.current.setData([]); prevLenRef.current = 0; return }
    const deduped = dedupeByTime(data)
    if (deduped.length < prevLenRef.current || prevLenRef.current === 0) {
      seriesRef.current.setData(deduped.map(d => ({ time: d.time as LineData['time'], value: d.mid })))
    } else {
      const last = deduped[deduped.length - 1]
      seriesRef.current.update({ time: last.time as LineData['time'], value: last.mid })
    }
    prevLenRef.current = deduped.length
  }, [data])

  const price = data.length ? data[data.length-1].mid : null
  return (
    <Panel title="PRICE" style={style} rightHeader={
      <span style={{ color: '#FF8C00', fontSize: '11px' }}>
        {price != null ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
      </span>
    }>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
    </Panel>
  )
}
