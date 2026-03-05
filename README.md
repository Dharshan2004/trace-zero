# TRACE-ZERO — Optimal Execution Simulator

> A full-stack institutional-grade trading simulator that replays real market microstructure data and compares three liquidation strategies — **Almgren-Chriss optimal execution**, TWAP, and market dump — measuring implementation shortfall, execution variance, and AC utility across a live animated Bloomberg Terminal UI.

---

## What This Is

Most execution algorithm implementations are theoretical scripts that spit out a matplotlib graph. This one isn't.

TRACE-ZERO connects a **market replay engine** (real Binance L1 orderbook data) to a **simulated matching engine** that applies permanent and temporary price impact as orders are filled. Three strategies run simultaneously against independent exchange instances so their market impact trajectories never contaminate each other. The result streams tick-by-tick over WebSocket to a Bloomberg Terminal-aesthetic UI built with TradingView's Lightweight Charts library.

The payoff: a live tear sheet that quantifies, in basis points, exactly how much the AC optimal trajectory saves over naive execution.

---

## The Finance

### Almgren-Chriss Optimal Liquidation (2000)

Given a position of $X$ shares to liquidate over horizon $T$ with $N$ child orders, the model solves for the trajectory $\{x_j\}$ minimising mean-variance execution cost:

$$\min_{\{x_j\}} \quad E[C] + \lambda \cdot \text{Var}[C]$$

Where:
- **Permanent impact** — each trade shifts the midprice permanently: $g(v) = \gamma \cdot v$
- **Temporary impact** — per-trade spread + depth cost: $h(v) = \varepsilon \cdot \text{sgn}(v) + \eta \cdot v/\tau$
- **$\lambda$** — risk aversion (controls the speed/risk tradeoff: $\lambda \to 0$ approaches TWAP, $\lambda \to \infty$ approaches immediate dump)

The closed-form optimal schedule uses a hyperbolic sine trajectory:

$$\tilde{x}_j = X \cdot \frac{2\sinh\!\left(\tfrac{1}{2}\kappa\tau\right)}{\sinh(\kappa T)} \cdot \cosh\!\left(\kappa\!\left(T - \left(j - \tfrac{1}{2}\right)\tau\right)\right)$$

Where $\kappa$ is derived from the model parameters and encodes the "urgency" of execution.

### Calibration from Crypto L1 Data

AC was designed for equities. TRACE-ZERO adapts it to crypto by deriving parameters directly from the replay feed:

| Parameter | How it's derived |
|-----------|-----------------|
| $\sigma^2$ | Variance of log mid-price returns, scaled to interval $\tau = T/N$ |
| $\varepsilon$ | Median half-spread: `median((ask - bid) / 2)` across all replay ticks |
| $\gamma$, $\eta$ | Standard AC scaling from spread and daily volume estimate — exposed as UI sliders |

### Implementation Shortfall

Each strategy's execution quality is measured in basis points:

$$\text{IS (bps)} = \frac{P_{\text{arrival}} - \text{VWAP}_{\text{fills}}}{P_{\text{arrival}}} \times 10{,}000$$

A lower shortfall = more value extracted from the liquidation.

### Why This Matters

- **Dump** has the lowest market risk (done instantly) but highest implementation shortfall — the entire order hammers through available liquidity at once
- **TWAP** spreads impact but ignores the risk of adverse price moves during the liquidation window
- **AC Optimal** finds the mathematically optimal balance for a given risk aversion $\lambda$, and this project makes that tradeoff visible

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Next.js Frontend (port 3000)              │
│                                                              │
│  ┌────────────┐  ┌─────────────────────────┐  ┌──────────┐  │
│  │ Parameters │  │ Price / Trajectory /    │  │   Tear   │  │
│  │   Panel    │  │ Shortfall (LW Charts)   │  │  Sheet   │  │
│  │   <GO>     │  │                         │  │  Grid    │  │
│  └────────────┘  └─────────────────────────┘  └──────────┘  │
│  └──────────────────── Order Blotter ──────────────────────┘  │
│                                                              │
│                 useSimulation() WebSocket hook               │
└─────────────────────────┬────────────────────────────────────┘
                          │  WS: tick-by-tick snapshots
                          │  REST: POST /api/simulation/run
┌─────────────────────────▼────────────────────────────────────┐
│                  FastAPI Backend (port 8000)                  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  Simulation Runner                     │  │
│  │                                                        │  │
│  │  Market Replay Events                                  │  │
│  │        │                                               │  │
│  │        │  calibrate_from_replay()                      │  │
│  │        │         │                                     │  │
│  │        │         ▼ ACConfig (σ², ε, γ, η)              │  │
│  │        │                                               │  │
│  │        ├──► SimulatedExchange A ◄── DumpStrategy       │  │
│  │        ├──► SimulatedExchange B ◄── TWAPStrategy       │  │
│  │        └──► SimulatedExchange C ◄── ACOptimalStrategy  │  │
│  │                                                        │  │
│  │  Each exchange owns its own SimulatedBook —            │  │
│  │  permanent impact is isolated per strategy             │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────┐                                       │
│  │  Market Replay    │  Binance L1 JSONL  →  generator       │
│  │  collector.py     │  or synthetic random walk fallback    │
│  └───────────────────┘                                       │
└──────────────────────────────────────────────────────────────┘
```

### Key Design Decision: Isolated Exchange Instances

Each strategy gets its own `SimulatedBook` instance tracking its own cumulative permanent impact. This is the correct way to model it — in a real pre-trade analytics system, you'd run each strategy in a separate simulation lane with the same price feed but diverging impact paths. It's not a subtle detail; without it, the dump strategy's immediate dislocation would corrupt the TWAP and AC price series.

---

## Project Structure

```
trace-zero/
├── backend/
│   ├── main.py                         # FastAPI app, CORS
│   ├── models/
│   │   └── almgren_chriss.py           # ACConfig dataclass + AlmgrenChriss class
│   │                                   # + calibrate_from_replay()
│   ├── engine/
│   │   ├── order.py                    # Order / Fill dataclasses
│   │   ├── book.py                     # SimulatedBook: raw L1 + permanent impact
│   │   └── exchange.py                 # SimulatedExchange: fill execution engine
│   ├── strategies/
│   │   ├── base.py                     # Abstract Strategy + TradeSlice
│   │   ├── dump.py                     # 100% at t=0
│   │   ├── twap.py                     # N equal slices over T
│   │   └── ac_optimal.py               # AC hyperbolic sine schedule
│   ├── simulation/
│   │   ├── config.py                   # SimulationConfig dataclass
│   │   ├── runner.py                   # Async orchestrator + streaming callback
│   │   └── results.py                  # StrategyResult + SimulationResult
│   ├── market_replay/
│   │   ├── collector.py                # Async Binance WS capture
│   │   ├── normalizer.py               # Raw → {bid, ask, mid, spread, ts_ms}
│   │   ├── logger.py                   # NDJSON writer
│   │   ├── replay.py                   # Generator-based replay (no sleep)
│   │   └── loader.py                   # JSONL loading + file metadata
│   └── api/
│       ├── routes.py                   # REST endpoints
│       └── ws.py                       # WebSocket streaming endpoint
├── frontend/
│   └── src/
│       ├── app/                        # Next.js App Router (layout, page)
│       ├── components/
│       │   ├── Terminal.tsx            # Root grid layout
│       │   ├── TopBar.tsx              # Brand bar + live clock + status
│       │   ├── SimulationForm.tsx      # Parameter inputs + GO button
│       │   ├── PriceChart.tsx          # Mid-price (Lightweight Charts)
│       │   ├── TrajectoryChart.tsx     # Shares remaining, 3 strategies
│       │   ├── CostChart.tsx           # Cumulative shortfall (bps)
│       │   ├── TearSheet.tsx           # Bloomberg comparison table
│       │   ├── OrderBlotter.tsx        # Scrolling child order fills
│       │   └── Panel.tsx               # Reusable panel wrapper
│       └── hooks/
│           └── useSimulation.ts        # WS connection + React state
├── data/                               # Captured JSONL files (git-ignored)
├── scripts/
│   └── capture_data.py                 # CLI: python scripts/capture_data.py BTCUSDT 60
├── pyproject.toml
└── OptimalPath(withoutMarketMovements).py   # Original reference (kept for diff)
```

---

## Getting Started

### Prerequisites

- Python ≥ 3.11
- Node.js ≥ 18

### 1. Install backend

```bash
git clone https://github.com/your-username/trace-zero.git
cd trace-zero
pip install -e .
```

### 2. Start the API server

```bash
uvicorn backend.main:app --reload --port 8000
```

No data file required — if `data/` is empty, the runner generates a synthetic BTC price path (geometric random walk, ~$97k mid, realistic spread and volatility) so you can run immediately without a Binance connection.

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open **`http://localhost:3000`**.

### 4. Run your first simulation

The form is pre-filled with sensible defaults. Hit **`GO`** and watch:

- **Price chart** — mid-price from the replay feed
- **Trajectory chart** — Dump drops to zero instantly (red), TWAP steps linearly (yellow), AC traces a concave curve (green)
- **Shortfall chart** — cumulative cost in bps diverges over time; AC should finish lowest
- **Tear sheet** — final VWAP, shortfall, variance, and AC utility for all three strategies

---

## Capturing Real Market Data

```bash
# 60 seconds of BTCUSDT orderbook ticks
python scripts/capture_data.py BTCUSDT 60

# Different symbol, longer window
python scripts/capture_data.py ETHUSDT 300
```

Files land in `data/` (git-ignored). The UI lists available symbols automatically via `GET /api/symbols`. You can also drop your own `.jsonl` files in — one JSON object per line with `bid`, `ask`, `timestamp_ms` fields.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/symbols` | List available captured data files |
| `GET` | `/api/symbols/{symbol}/info` | Event count, time range, price range |
| `POST` | `/api/simulation/run` | Start simulation, returns `{"sim_id": "..."}` |
| `WS` | `/api/simulation/{sim_id}/stream` | Stream tick-by-tick snapshots |
| `POST` | `/api/capture` | Trigger live Binance data capture |

### POST /api/simulation/run

```json
{
  "symbol": "BTCUSDT",
  "total_shares": 1.0,
  "liquidation_time": 60,
  "num_trades": 20,
  "risk_aversion": 1e-6,
  "gamma_override": null,
  "eta_override": null
}
```

### WebSocket snapshot message

```json
{
  "type": "snapshot",
  "step": 5,
  "total_steps": 20,
  "mid_price": 97432.10,
  "timestamp_ms": 1709654400000,
  "strategies": {
    "dump": { "shares_remaining": 0.0,  "avg_price": 97380.0, "cumulative_cost_bps": 52.1 },
    "twap": { "shares_remaining": 0.75, "avg_price": 97445.0, "cumulative_cost_bps": 18.3 },
    "ac":   { "shares_remaining": 0.82, "avg_price": 97448.0, "cumulative_cost_bps": 8.7  }
  }
}
```

Final message type is `"complete"` with the full `SimulationResult`.

---

## Verification Checklist

| Scenario | Expected behaviour |
|----------|--------------------|
| λ → 0 | AC schedule converges to TWAP (flat trade list) |
| λ → ∞ | AC schedule converges to Dump (one large first trade) |
| All shares sold | Each strategy should liquidate 100% by final step |
| Trajectory shapes | Dump: vertical drop at t=0. TWAP: linear staircase. AC: smooth concave curve |
| Shortfall ordering | For moderate λ: IS(dump) > IS(twap) > IS(ac) |
| Permanent impact isolation | Re-running with a different λ should not change Dump or TWAP results |

---

## Tech Stack

**Backend**
- **FastAPI** + **uvicorn** — async REST and WebSocket server
- **NumPy** — all AC model mathematics
- **websockets** — Binance live data capture
- Pure Python dataclasses throughout — no database, no ORM, minimal dependencies

**Frontend**
- **Next.js 15** (App Router, SWC compiler)
- **Lightweight Charts** (TradingView) — WebGL-accelerated financial charts
- **Tailwind CSS** — utility styling with custom Bloomberg color theme
- **JetBrains Mono** — monospace terminal font

---

## Reference

- Almgren, R. & Chriss, N. (2000). *Optimal execution of portfolio transactions.* Journal of Risk, 3(2), 5–39.
- Almgren, R. (2003). *Optimal execution with nonlinear impact functions and trading-enhanced risk.* Applied Mathematical Finance, 10(1), 1–18.

---

## License

MIT — see [LICENSE](LICENSE)
