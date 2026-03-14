'use client'
import { useState, useRef, useCallback } from 'react'

export type SimStatus = 'idle' | 'running' | 'complete' | 'error'

export interface SimConfig {
  symbol: string
  total_shares: number
  liquidation_time: number
  num_trades: number
  risk_aversion: number
  gamma_override?: number
  eta_override?: number
  latency_ms?: number
  calibration_window?: number
  ui_throttle_ms?: number
}

export interface PricePoint {
  time: number
  mid: number
  bid: number
  ask: number
}

export interface TrajectoryPoint {
  time: number
  dump: number
  twap: number
  vwap: number
  ac: number
}

export interface CostPoint {
  time: number
  dump: number
  twap: number
  vwap: number
  ac: number
}

export interface FillEvent {
  timestamp_ms: number
  strategy: string
  qty: number
  price: number
  slippage_bps: number
  temp_impact: number
}

export interface TearSheetResult {
  dump: { vwap: number; shortfall_bps: number; variance: number; utility: number }
  twap: { vwap: number; shortfall_bps: number; variance: number; utility: number }
  vwap: { vwap: number; shortfall_bps: number; variance: number; utility: number }
  ac:   { vwap: number; shortfall_bps: number; variance: number; utility: number }
  ac_savings_vs_dump_bps: number
  ac_savings_vs_twap_bps: number
}

function normalizeResult(api: {
  strategies?: {
    dump?: Record<string, unknown>
    twap?: Record<string, unknown>
    vwap?: Record<string, unknown>
    ac?: Record<string, unknown>
  }
  ac_savings_vs_dump_bps?: number
  ac_savings_vs_twap_bps?: number
}): TearSheetResult {
  const map = (s: Record<string, unknown> | undefined) => ({
    vwap: Number(s?.vwap ?? 0),
    shortfall_bps: Number(s?.implementation_shortfall_bps ?? s?.shortfall_bps ?? 0),
    variance: Number(s?.trajectory_variance ?? s?.variance ?? 0),
    utility: Number(s?.utility ?? 0),
  })
  return {
    dump: map(api.strategies?.dump),
    twap: map(api.strategies?.twap),
    vwap: map(api.strategies?.vwap),
    ac:   map(api.strategies?.ac),
    ac_savings_vs_dump_bps: Number(api.ac_savings_vs_dump_bps ?? 0),
    ac_savings_vs_twap_bps: Number(api.ac_savings_vs_twap_bps ?? 0),
  }
}

export function useSimulation() {
  const [status, setStatus] = useState<SimStatus>('idle')
  const [config, setConfig] = useState<SimConfig>({
    symbol: 'BTCUSDT',
    total_shares: 1.0,
    liquidation_time: 60,
    num_trades: 20,
    risk_aversion: 1e-6,
    latency_ms: 0,
    calibration_window: 100,
    ui_throttle_ms: 50,
  })
  const [priceData, setPriceData] = useState<PricePoint[]>([])
  const [trajectoryData, setTrajectoryData] = useState<TrajectoryPoint[]>([])
  const [costData, setCostData] = useState<CostPoint[]>([])
  const [allFills, setAllFills] = useState<FillEvent[]>([])
  const [result, setResult] = useState<TearSheetResult | null>(null)
  const [dataMode, setDataMode] = useState<'l2_real' | 'l2_synthetic' | 'l1' | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const statusRef = useRef<SimStatus>('idle')

  const start = useCallback(async (cfg: SimConfig) => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }

    setConfig(cfg)
    setStatus('running')
    statusRef.current = 'running'
    setPriceData([])
    setTrajectoryData([])
    setCostData([])
    setAllFills([])
    setResult(null)
    setDataMode(null)

    try {
      const res = await fetch('/api/simulation/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      if (!res.ok) { setStatus('error'); statusRef.current = 'error'; return }

      const { sim_id } = await res.json()

      const ws = new WebSocket(`ws://localhost:8000/api/simulation/${sim_id}/stream`)
      wsRef.current = ws

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)

          if (msg.type === 'snapshot') {
            if (msg.mid_price != null && msg.timestamp_ms != null) {
              setPriceData(prev => [...prev, {
                time: Math.floor(msg.timestamp_ms / 1000),
                mid: msg.mid_price,
                bid: msg.bid ?? msg.mid_price,
                ask: msg.ask ?? msg.mid_price,
              }])
            }
            if (msg.data_mode) setDataMode(msg.data_mode)
            if (msg.strategies) {
              const t = Math.floor(msg.timestamp_ms / 1000)
              setTrajectoryData(prev => [...prev, {
                time: t,
                dump: msg.strategies.dump?.qty_traded ?? 0,
                twap: msg.strategies.twap?.qty_traded ?? 0,
                vwap: msg.strategies.vwap?.qty_traded ?? 0,
                ac:   msg.strategies.ac?.qty_traded ?? 0,
              }])
              setCostData(prev => [...prev, {
                time: t,
                dump: msg.strategies.dump?.cumulative_cost_bps ?? 0,
                twap: msg.strategies.twap?.cumulative_cost_bps ?? 0,
                vwap: msg.strategies.vwap?.cumulative_cost_bps ?? 0,
                ac:   msg.strategies.ac?.cumulative_cost_bps ?? 0,
              }])
            }
            if (msg.new_fills && Array.isArray(msg.new_fills)) {
              setAllFills(prev => [...prev, ...msg.new_fills])
            }
          } else if (msg.type === 'complete') {
            // Hydrate the price chart from the full price_series in the result
            // (the WebSocket throttle may have only delivered a few live snapshots)
            const series = msg.result?.price_series
            if (Array.isArray(series) && series.length > 0) {
              setPriceData(series.map((p: { timestamp_ms: number; mid: number; bid: number; ask: number }) => ({
                time: Math.floor(p.timestamp_ms / 1000),
                mid: p.mid,
                bid: p.bid,
                ask: p.ask,
              })))
            }
            setResult(normalizeResult(msg.result ?? {}))
            setStatus('complete')
            statusRef.current = 'complete'
            ws.close()
          }
        } catch { /* ignore malformed messages */ }
      }

      ws.onerror = () => { setStatus('error'); statusRef.current = 'error' }
      ws.onclose = () => {
        if (statusRef.current === 'running') { setStatus('idle'); statusRef.current = 'idle' }
      }
    } catch {
      setStatus('error')
      statusRef.current = 'error'
    }
  }, [])

  return { status, config, priceData, trajectoryData, costData, fills: allFills, allFills, result, dataMode, start }
}
