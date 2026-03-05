"""
Core simulation orchestrator.

Coordinates:
  1. Loading / generating replay data
  2. Calibrating the AC model
  3. Creating strategy instances and exchange instances
  4. Replaying market events and firing orders at the right time steps
  5. Streaming per-step snapshots via an async callback
  6. Assembling and returning the final SimulationResult

Time mapping
------------
Replay events span some real-world elapsed time (e.g. 60 seconds of live
data). The simulation maps them uniformly onto the liquidation horizon T
(minutes). Each of the N trade steps occupies tau = T/N minutes and is
triggered when the replay cursor crosses the corresponding fraction of the
total event stream.
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable

import numpy as np

from backend.engine.exchange import SimulatedExchange
from backend.engine.order import Order
from backend.market_replay.loader import load_file
from backend.models.almgren_chriss import AlmgrenChriss, calibrate_from_replay
from backend.simulation.config import SimulationConfig
from backend.simulation.results import SimulationResult, StrategyResult
from backend.strategies.ac_optimal import ACOptimalStrategy
from backend.strategies.base import Strategy, TradeSlice
from backend.strategies.dump import DumpStrategy
from backend.strategies.twap import TWAPStrategy


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------

def _generate_synthetic_events(
    n_ticks: int = 500,
    mid_start: float = 97_000.0,
    spread: float = 1.0,
    sigma_per_tick: float = 0.0002,
    symbol: str = "BTCUSDT",
) -> list[dict]:
    """
    Generate a synthetic BTC-like L1 orderbook event stream using a
    geometric random walk.

    Parameters
    ----------
    n_ticks : int
        Number of events to generate.
    mid_start : float
        Starting mid-price.
    spread : float
        Fixed bid-ask spread (USD).
    sigma_per_tick : float
        Fractional volatility per tick (log-normal step).
    symbol : str
        Symbol label for events.

    Returns
    -------
    list[dict]
        Normalized events compatible with the rest of the pipeline.
    """
    rng = np.random.default_rng(seed=42)
    log_returns = rng.normal(0.0, sigma_per_tick, n_ticks)
    mids = mid_start * np.exp(np.cumsum(log_returns))
    # Prepend the starting mid so first event = mid_start
    mids = np.insert(mids, 0, mid_start)[: n_ticks]

    half_spread = spread / 2.0
    base_ts = 1_700_000_000_000  # arbitrary recent epoch in ms
    events: list[dict] = []
    for i, mid in enumerate(mids):
        events.append(
            {
                "symbol": symbol,
                "bid": float(mid - half_spread),
                "ask": float(mid + half_spread),
                "mid": float(mid),
                "spread": spread,
                "timestamp_ms": base_ts + i * 100,  # 100ms spacing
            }
        )
    return events


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_simulation(
    config: SimulationConfig,
    on_snapshot: Callable[[dict], Awaitable[None]],
) -> SimulationResult:
    """
    Run the complete three-strategy simulation.

    Parameters
    ----------
    config : SimulationConfig
        Simulation parameters.
    on_snapshot : async callable
        Called after each trade step with a snapshot dict so that a
        WebSocket handler can stream incremental updates to the client.

    Returns
    -------
    SimulationResult
        Full simulation result including all fills and metrics.
    """
    # ------------------------------------------------------------------
    # 1. Load or generate replay events
    # ------------------------------------------------------------------
    events: list[dict]
    if config.data_file and os.path.isfile(config.data_file):
        events = load_file(config.data_file)
    else:
        events = _generate_synthetic_events(symbol=config.symbol)

    if not events:
        events = _generate_synthetic_events(symbol=config.symbol)

    # ------------------------------------------------------------------
    # 2. Calibrate AC model from events
    # ------------------------------------------------------------------
    ac_config = calibrate_from_replay(
        events=events,
        T=config.liquidation_time,
        N=config.num_trades,
        shares=config.total_shares,
        llambda=config.risk_aversion,
    )

    # Apply overrides if provided
    if config.gamma_override is not None:
        ac_config.gamma = config.gamma_override
    if config.eta_override is not None:
        ac_config.eta = config.eta_override

    ac_model = AlmgrenChriss(ac_config)

    # ------------------------------------------------------------------
    # 3. Create strategies + exchange instances
    # ------------------------------------------------------------------
    strategies: list[Strategy] = [
        DumpStrategy(),
        TWAPStrategy(),
        ACOptimalStrategy(ac_model),
    ]

    exchanges: dict[str, SimulatedExchange] = {
        s.name: SimulatedExchange(ac_model) for s in strategies
    }

    # Generate trade schedules
    schedules: dict[str, list[TradeSlice]] = {
        s.name: s.generate_schedule(
            config.total_shares,
            config.liquidation_time,
            config.num_trades,
        )
        for s in strategies
    }

    N = config.num_trades
    total_events = len(events)

    # ------------------------------------------------------------------
    # 4. Time mapping
    #
    # We divide the event stream into N equal-sized "buckets". When the
    # replay cursor enters bucket i, strategy step i is executed.
    #
    # If there are fewer events than trade steps, pad the event list with
    # copies of the last event so every step still gets an event.
    # ------------------------------------------------------------------
    if total_events < N:
        # Pad with copies of the last event to ensure every step fires
        padding = [events[-1]] * (N - total_events)
        events = events + padding
        total_events = len(events)

    bucket_size = total_events / N
    raw_step_indices: list[int] = [int(i * bucket_size) for i in range(N)]

    # Deduplicate: if two steps map to the same event index due to
    # rounding, increment subsequent duplicates to the next unused index.
    seen: set[int] = set()
    step_trigger_indices: list[int] = []
    for idx in raw_step_indices:
        while idx in seen:
            idx += 1
        # Clamp to valid range
        idx = min(idx, total_events - 1)
        seen.add(idx)
        step_trigger_indices.append(idx)

    step_trigger_set = set(step_trigger_indices)

    # Reverse map: event_index -> step_index (for O(1) lookup)
    event_to_step: dict[int, int] = {
        ev_idx: step_idx
        for step_idx, ev_idx in enumerate(step_trigger_indices)
    }

    # ------------------------------------------------------------------
    # 5. Per-strategy state tracking
    # ------------------------------------------------------------------
    # shares_remaining[strategy_name][step] = shares after step i
    shares_remaining_track: dict[str, list[float]] = {
        s.name: [] for s in strategies
    }
    cost_curve_track: dict[str, list[float]] = {
        s.name: [] for s in strategies
    }

    price_series: list[dict] = []
    # Subsample price series so the client chart never receives > ~1000 points
    _price_subsample = max(1, total_events // 1000)

    # Pre-warm all books with the first event so arrival_price is set
    first_event = events[0]
    for ex in exchanges.values():
        ex.update_book(first_event)

    # ------------------------------------------------------------------
    # 6. Replay loop
    # ------------------------------------------------------------------
    step_count = 0

    for ev_idx, event in enumerate(events):
        # Update all books with the current market state
        for ex in exchanges.values():
            ex.update_book(event)

        # Track price series (subsampled to at most 1000 points for the client chart)
        if ev_idx % _price_subsample == 0:
            price_series.append(
                {
                    "timestamp_ms": event.get("timestamp_ms", ev_idx * 100),
                    "mid": event.get("mid", (event["bid"] + event["ask"]) / 2.0),
                    "bid": event["bid"],
                    "ask": event["ask"],
                }
            )

        # Check if this event triggers a trade step
        if ev_idx in step_trigger_set:
            step_idx = event_to_step[ev_idx]
            step_count += 1

            # Use the replay event's own timestamp as the simulation clock
            sim_ts_ms = event.get("timestamp_ms", ev_idx * 100)

            # Fire orders for all strategies at this step
            strategy_snapshot: dict[str, dict] = {}

            for s in strategies:
                trade_slice = schedules[s.name][step_idx]
                qty = trade_slice.qty

                if qty > 1e-12:
                    order = Order(
                        strategy_name=s.name,
                        qty=qty,
                        timestamp_ms=sim_ts_ms,
                    )
                    exchanges[s.name].execute(order)

                ex = exchanges[s.name]
                shares_rem = ex.shares_remaining
                shares_remaining_track[s.name].append(shares_rem)

                # Cumulative IS so far
                cum_is_bps = ex.implementation_shortfall_bps
                cost_curve_track[s.name].append(cum_is_bps)

                strategy_snapshot[s.name] = {
                    "shares_remaining": shares_rem,
                    "avg_price": ex.avg_fill_price,
                    "cumulative_cost_bps": cum_is_bps,
                }

            mid_price = event.get("mid", (event["bid"] + event["ask"]) / 2.0)

            snapshot = {
                "type": "snapshot",
                "step": step_count,
                "total_steps": N,
                "mid_price": mid_price,
                "timestamp_ms": sim_ts_ms,
                "strategies": strategy_snapshot,
            }

            await on_snapshot(snapshot)

            # Yield control to the event loop occasionally
            if step_count % 5 == 0:
                await asyncio.sleep(0)

    # ------------------------------------------------------------------
    # 7. Assemble StrategyResults
    # ------------------------------------------------------------------
    arrival_price = exchanges["dump"].arrival_price  # same for all

    def _build_result(strategy_name: str) -> StrategyResult:
        ex = exchanges[strategy_name]
        fills = ex.fills
        vwap = ex.avg_fill_price
        is_bps = ex.implementation_shortfall_bps

        trade_qtys = np.array([f.qty_filled for f in fills])
        traj_var = ac_model.trajectory_variance(trade_qtys) if len(trade_qtys) > 0 else 0.0

        # Utility: E[shortfall_bps] proxy + lambda * variance
        # We use ac_model utility as the reference for the AC strategy.
        # For dump/twap we use the IS-based approximation.
        if strategy_name == "ac":
            utility = float(ac_model.compute_AC_utility(config.total_shares))
        else:
            utility = is_bps + config.risk_aversion * traj_var

        trajectory = shares_remaining_track.get(strategy_name, [])
        cost_curve = cost_curve_track.get(strategy_name, [])

        return StrategyResult(
            name=strategy_name,
            fills=fills,
            vwap=vwap,
            implementation_shortfall_bps=is_bps,
            trajectory_variance=traj_var,
            utility=utility,
            trajectory=trajectory,
            cost_curve=cost_curve,
        )

    dump_result = _build_result("dump")
    twap_result = _build_result("twap")
    ac_result = _build_result("ac")

    ac_savings_vs_dump = dump_result.implementation_shortfall_bps - ac_result.implementation_shortfall_bps
    ac_savings_vs_twap = twap_result.implementation_shortfall_bps - ac_result.implementation_shortfall_bps

    result = SimulationResult(
        config=config,
        dump=dump_result,
        twap=twap_result,
        ac=ac_result,
        price_series=price_series,
        ac_savings_vs_dump_bps=ac_savings_vs_dump,
        ac_savings_vs_twap_bps=ac_savings_vs_twap,
    )

    return result
