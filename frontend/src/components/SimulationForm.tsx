'use client'
import { useState } from 'react'
import type { CSSProperties } from 'react'
import Panel from '@/components/Panel'
import type { SimConfig, SimStatus } from '@/hooks/useSimulation'

interface Props {
  onSubmit: (cfg: SimConfig) => void
  config: SimConfig
  status: SimStatus
  style?: CSSProperties
}

interface FormState {
  symbol: string
  total_shares: string
  liquidation_time: string
  num_trades: string
  risk_aversion: string
  gamma_override: string
  eta_override: string
  latency_ms: string
  calibration_window: string
}

function Field({ label, value, onChange, type = 'text', placeholder = '', disabled = false }: {
  label: string; value: string; onChange: (v: string) => void;
  type?: string; placeholder?: string; disabled?: boolean
}) {
  return (
    <div style={{ marginBottom: '10px' }}>
      <label>{label}</label>
      <input type={type} value={value} placeholder={placeholder} disabled={disabled}
        onChange={e => onChange(e.target.value)} autoComplete="off" spellCheck={false} />
    </div>
  )
}

export default function SimulationForm({ onSubmit, config, status, style }: Props) {
  const [form, setForm] = useState<FormState>({
    symbol: config.symbol,
    total_shares: String(config.total_shares),
    liquidation_time: String(config.liquidation_time),
    num_trades: String(config.num_trades),
    risk_aversion: String(config.risk_aversion),
    gamma_override: '',
    eta_override: '',
    latency_ms: String(config.latency_ms ?? 0),
    calibration_window: String(config.calibration_window ?? 100),
  })

  const isRunning = status === 'running'
  const set = (k: keyof FormState) => (v: string) => setForm(p => ({ ...p, [k]: v }))

  function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault()
    if (isRunning) return
    const cfg: SimConfig = {
      symbol: form.symbol.trim().toUpperCase() || 'BTCUSDT',
      total_shares: parseFloat(form.total_shares) || 1.0,
      liquidation_time: parseInt(form.liquidation_time) || 60,
      num_trades: parseInt(form.num_trades) || 20,
      risk_aversion: parseFloat(form.risk_aversion) || 1e-6,
      latency_ms: parseFloat(form.latency_ms) || 0,
      calibration_window: parseInt(form.calibration_window) || 100,
      ui_throttle_ms: 50,
    }
    if (form.gamma_override.trim()) { const g = parseFloat(form.gamma_override); if (!isNaN(g)) cfg.gamma_override = g }
    if (form.eta_override.trim()) { const e = parseFloat(form.eta_override); if (!isNaN(e)) cfg.eta_override = e }
    onSubmit(cfg)
  }

  return (
    <Panel title="PARAMETERS" style={style}>
      <form onSubmit={handleSubmit} style={{ padding: '10px 8px', display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <Field label="SYMBOL" value={form.symbol} onChange={set('symbol')} placeholder="BTCUSDT" disabled={isRunning} />
          <Field label="TOTAL SHARES" value={form.total_shares} onChange={set('total_shares')} type="number" placeholder="1.000" disabled={isRunning} />
          <Field label="LIQ TIME (MIN)" value={form.liquidation_time} onChange={set('liquidation_time')} type="number" placeholder="60" disabled={isRunning} />
          <Field label="NUM TRADES" value={form.num_trades} onChange={set('num_trades')} type="number" placeholder="20" disabled={isRunning} />
          <Field label="RISK AVERSION" value={form.risk_aversion} onChange={set('risk_aversion')} placeholder="0.000001" disabled={isRunning} />
          <div style={{ borderTop: '1px solid #222', margin: '8px 0' }} />
          <div style={{ color: '#555', fontSize: '10px', marginBottom: '6px' }}>MARKET MICROSTRUCTURE</div>
          <Field label="LATENCY (MS)" value={form.latency_ms} onChange={set('latency_ms')} type="number" placeholder="0" disabled={isRunning} />
          <Field label="CAL WINDOW" value={form.calibration_window} onChange={set('calibration_window')} type="number" placeholder="100" disabled={isRunning} />
          <div style={{ borderTop: '1px solid #222', margin: '8px 0' }} />
          <div style={{ color: '#555', fontSize: '10px', marginBottom: '6px' }}>OPTIONAL OVERRIDES</div>
          <Field label="GAMMA OVERRIDE" value={form.gamma_override} onChange={set('gamma_override')} placeholder="—" disabled={isRunning} />
          <Field label="ETA OVERRIDE" value={form.eta_override} onChange={set('eta_override')} placeholder="—" disabled={isRunning} />
        </div>
        <div style={{ marginTop: '12px', flexShrink: 0 }}>
          <button type="submit" className="btn-go" disabled={isRunning}>
            {isRunning ? 'RUNNING...' : 'GO'}
          </button>
        </div>
      </form>
    </Panel>
  )
}
