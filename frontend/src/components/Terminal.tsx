'use client'
import TopBar from '@/components/TopBar'
import SimulationForm from '@/components/SimulationForm'
import PriceChart from '@/components/PriceChart'
import TrajectoryChart from '@/components/TrajectoryChart'
import CostChart from '@/components/CostChart'
import TearSheet from '@/components/TearSheet'
import OrderBlotter from '@/components/OrderBlotter'
import { useSimulation } from '@/hooks/useSimulation'

export default function Terminal() {
  const sim = useSimulation()

  return (
    <div style={{
      display: 'grid',
      gridTemplateRows: '32px 1fr 140px',
      gridTemplateColumns: '220px 1fr 380px',
      height: '100vh',
      width: '100vw',
      gap: '1px',
      background: '#333333',
      overflow: 'hidden',
    }}>
      <TopBar
        symbol={sim.config.symbol}
        status={sim.status}
        dataMode={sim.dataMode}
        style={{ gridColumn: '1 / -1', gridRow: '1' }}
      />
      <SimulationForm
        onSubmit={sim.start}
        config={sim.config}
        status={sim.status}
        style={{ gridColumn: '1', gridRow: '2', overflow: 'hidden' }}
      />
      <div style={{
        gridColumn: '2',
        gridRow: '2',
        display: 'grid',
        gridTemplateRows: '1fr 1fr 1fr',
        gap: '1px',
        background: '#333333',
        overflow: 'hidden',
        minHeight: 0,
      }}>
        <PriceChart data={sim.priceData} fills={sim.fills} />
        <TrajectoryChart data={sim.trajectoryData} />
        <CostChart data={sim.costData} />
      </div>
      <TearSheet
        result={sim.result}
        symbol={sim.config.symbol}
        style={{ gridColumn: '3', gridRow: '2', overflow: 'hidden' }}
      />
      <OrderBlotter
        fills={sim.allFills}
        style={{ gridColumn: '2 / -1', gridRow: '3', overflow: 'hidden' }}
      />
    </div>
  )
}
