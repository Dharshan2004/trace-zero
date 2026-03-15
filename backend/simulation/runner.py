"""
Core simulation orchestrator.

Coordinates:
  1. Loading / generating replay data
  2. Static calibration of the AC model from the full event stream
  3. Creating strategy + exchange instances (Dump, TWAP, VWAP, AC Optimal)
  4. Replaying market events and firing orders at the right time steps
  5. Dynamic rolling calibration: updates kappa every N ticks as vol changes
  6. Network latency simulation: fills evaluated at T + latency_ms
  7. WebSocket throttling: UI snapshots batched at ui_throttle_ms cadence
  8. Assembling and returning the final SimulationResult

Rolling Calibration
-------------------
Every `calibration_window` ticks the runner recomputes sigma (rolling
log-return variance) and epsilon (rolling median half-spread) from the last W
ticks, then calls ac_model.recalibrate() to update kappa. The AC optimal
strategy's *previously scheduled* trade sizes are fixed (pre-computed from the
initial kappa), but the impact and utility calculations update dynamically.

WebSocket Throttling
--------------------
The internal simulation runs at full tick resolution. The on_snapshot callback
(which writes to the WebSocket queue) is rate-limited to ui_throttle_ms. This
decouples the simulation clock from the frontend render rate, preventing the
Next.js rendering thread from being flooded by thousands of events per second.

Latency Simulation
------------------
If config.latency_ms > 0, orders are not filled at the decision tick. The
exchange enqueues them as pending and executes the fill against the book state
latency_ms later — modelling the execution risk of a network round-trip.
"""

from __future__ import annotations

import asyncio
import os
import time as _time
from collections import deque
from typing import Awaitable, Callable

import numpy as np

from backend.engine.exchange import SimulatedExchange
from backend.engine.order import Order
from backend.market_replay.loader import list_data_files, load_file
from backend.models.almgren_chriss import AlmgrenChriss, calibrate_from_replay
from backend.simulation.config import SimulationConfig
from backend.simulation.results import SimulationResult, StrategyResult
from backend.strategies.ac_optimal import ACOptimalStrategy
from backend.strategies.base import Strategy, TradeSlice
from backend.strategies.dump import DumpStrategy
from backend.strategies.twap import TWAPStrategy
from backend.strategies.vwap import VWAPStrategy


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------

def _generate_synthetic_events(
    n_ticks: int = 500,
    mid_start: float = 97_000.0,
    spread: float = 1.0,
    sigma_per_tick: float = 0.0,
    symbol: str = "BTCUSDT",
    total_shares: float = 1.0,
) -> list[dict]:
    """
    Generate a synthetic BTC-like L1 orderbook event stream.

    sigma_per_tick is intentionally 0.0 so the price path is flat.
    This isolates pure market-impact effects: DUMP (sells all at t=0,
    walks deepest into the book) will always show the highest IS, and
    AC Optimal will always show the lowest IS, with no price-drift noise
    masking the signal.  A non-zero sigma would introduce a random walk
    whose direction (up or down) dominates over the sub-bps impact
    differences and makes the IS ordering unpredictable.

    tick_size is set to 10 USD so each depth level is $10 apart,
    producing IS differences of ~1–5 bps that are clearly readable on
    the tear sheet without needing unrealistically large position sizes.
    """
    rng = np.random.default_rng(seed=42)
    if sigma_per_tick > 0:
        log_returns = rng.normal(0.0, sigma_per_tick, n_ticks)
        mids = mid_start * np.exp(np.cumsum(log_returns))
        mids = np.insert(mids, 0, mid_start)[:n_ticks]
    else:
        mids = np.full(n_ticks, mid_start)

    half_spread = spread / 2.0
    base_ts = 1_700_000_000_000
    tick_size = 10.0  # $10 between levels → IS differences of ~1–5 bps, clearly visible

    events: list[dict] = []
    for i, mid in enumerate(mids):
        bid = mid - half_spread
        ask = mid + half_spread
        # Synthetic 10-level book: exponentially growing qty at deeper levels
        bid_levels = []
        ask_levels = []
        for level in range(10):
            tick_offset = level * tick_size
            # Scale depth with total_shares so the order always walks several
            # levels regardless of position size (prevents all strategies from
            # exhausting the book and showing identical worst-case IS).
            qty = total_shares * 0.02 * (2 ** level)
            bid_levels.append([bid - tick_offset, qty])
            ask_levels.append([ask + tick_offset, qty])
        events.append(
            {
                "symbol": symbol,
                "bid": float(bid),
                "ask": float(ask),
                "mid": float(mid),
                "spread": spread,
                "timestamp_ms": base_ts + i * 100,
                "bid_levels": bid_levels,
                "ask_levels": ask_levels,
            }
        )
    return events


# ---------------------------------------------------------------------------
# Rolling calibration helper
# ---------------------------------------------------------------------------

def _rolling_recalibrate(
    ac_model: AlmgrenChriss,
    mid_window: deque,
    spread_window: deque,
    tau: float,
    ticks_per_minute: float,
) -> None:
    """
    Recompute sigma2 and epsilon from the current rolling windows and
    call ac_model.recalibrate() to update kappa.
    """
    if len(mid_window) < 2:
        return

    mids = np.array(mid_window, dtype=float)
    log_returns = np.diff(np.log(mids))
    tick_variance = float(np.var(log_returns))

    ticks_per_tau = ticks_per_minute * tau
    sigma2_per_tau = tick_variance * ticks_per_tau
    mid_price = float(mids[-1])
    sigma2 = sigma2_per_tau * (mid_price ** 2)
    sigma2 = max(sigma2, 1e-10)

    half_spreads = np.array(spread_window, dtype=float) / 2.0
    epsilon = max(float(np.median(half_spreads)), 1e-8)

    ac_model.recalibrate(sigma2, epsilon, sigma2_for_kappa=max(sigma2_per_tau, 1e-20))


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_simulation(
    config: SimulationConfig,
    on_snapshot: Callable[[dict], Awaitable[None]],
) -> SimulationResult:
    """
    Run the complete four-strategy simulation (Dump, TWAP, VWAP, AC Optimal).

    Parameters
    ----------
    config : SimulationConfig
    on_snapshot : async callable
        Called with a snapshot dict to stream incremental UI updates.

    Returns
    -------
    SimulationResult
    """
    # ------------------------------------------------------------------
    # 1. Load or generate replay events
    # ------------------------------------------------------------------
    events: list[dict]

    # Resolve data file: explicit path → auto-discover by symbol → synthetic fallback
    _data_file = config.data_file
    if not (_data_file and os.path.isfile(_data_file)):
        # Auto-discover: look for any file in data/ whose name starts with the symbol
        _data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
        _candidates = list_data_files(_data_dir)
        for _candidate in _candidates:
            _fname = os.path.basename(_candidate).upper()
            if _fname.startswith(config.symbol.upper()):
                _data_file = _candidate
                break

    using_real_data = bool(_data_file and os.path.isfile(_data_file))
    if using_real_data:
        events = load_file(_data_file)
    else:
        events = _generate_synthetic_events(symbol=config.symbol, total_shares=config.total_shares)

    if not events:
        events = _generate_synthetic_events(symbol=config.symbol, total_shares=config.total_shares)
        using_real_data = False

    # ------------------------------------------------------------------
    # 2. Calibrate AC model (static, from full event stream)
    # ------------------------------------------------------------------
    ac_config = calibrate_from_replay(
        events=events,
        T=config.liquidation_time,
        N=config.num_trades,
        shares=config.total_shares,
        llambda=config.risk_aversion,
        daily_volume_estimate=config.daily_volume_estimate,
    )

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
        VWAPStrategy(),
        ACOptimalStrategy(ac_model),
    ]

    exchanges: dict[str, SimulatedExchange] = {
        s.name: SimulatedExchange(ac_model, latency_ms=config.latency_ms)
        for s in strategies
    }

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
    # ------------------------------------------------------------------
    if total_events < N:
        padding = [events[-1]] * (N - total_events)
        events = events + padding
        total_events = len(events)

    bucket_size = total_events / N
    raw_step_indices: list[int] = [int(i * bucket_size) for i in range(N)]

    seen: set[int] = set()
    step_trigger_indices: list[int] = []
    for idx in raw_step_indices:
        while idx in seen:
            idx += 1
        idx = min(idx, total_events - 1)
        seen.add(idx)
        step_trigger_indices.append(idx)

    step_trigger_set = set(step_trigger_indices)
    event_to_step: dict[int, int] = {
        ev_idx: step_idx
        for step_idx, ev_idx in enumerate(step_trigger_indices)
    }

    # ------------------------------------------------------------------
    # 5. Rolling calibration setup
    # ------------------------------------------------------------------
    use_rolling = config.calibration_window > 0
    cal_window = config.calibration_window if use_rolling else 0

    mid_window: deque = deque(maxlen=cal_window) if use_rolling else deque()
    spread_window: deque = deque(maxlen=cal_window) if use_rolling else deque()

    # Estimate ticks-per-minute for sigma scaling
    timestamps = [e.get("timestamp_ms", 0) for e in events]
    elapsed_ms = max(timestamps[-1] - timestamps[0], 1)
    ticks_per_minute = (total_events - 1) / (elapsed_ms / 60_000.0)

    ticks_since_cal = 0

    # ------------------------------------------------------------------
    # 6. Per-strategy tracking
    # ------------------------------------------------------------------
    shares_remaining_track: dict[str, list[float]] = {s.name: [] for s in strategies}
    cost_curve_track: dict[str, list[float]] = {s.name: [] for s in strategies}

    price_series: list[dict] = []
    _price_subsample = max(1, total_events // 1000)

    # Pre-warm all books with the first event
    first_event = events[0]
    for ex in exchanges.values():
        ex.update_book(first_event)

    # ------------------------------------------------------------------
    # 7. WebSocket throttle state
    # ------------------------------------------------------------------
    _throttle_interval = config.ui_throttle_ms / 1000.0  # seconds
    _last_broadcast_mono = _time.monotonic()

    # ------------------------------------------------------------------
    # 8. Replay loop
    # ------------------------------------------------------------------
    step_count = 0

    for ev_idx, event in enumerate(events):
        # Update all books
        for ex in exchanges.values():
            ex.update_book(event)

        # Apply any latency-pending fills that are now due
        if config.latency_ms > 0:
            for ex in exchanges.values():
                ex.apply_pending_fills(event)

        # Rolling calibration window update
        if use_rolling:
            mid_val = event.get("mid", (event["bid"] + event["ask"]) / 2.0)
            mid_window.append(mid_val)
            spread_window.append(event["ask"] - event["bid"])
            ticks_since_cal += 1

            if ticks_since_cal >= cal_window and len(mid_window) >= 2:
                _rolling_recalibrate(
                    ac_model, mid_window, spread_window,
                    ac_model.tau, ticks_per_minute,
                )
                ticks_since_cal = 0

        # Price series for chart (subsampled)
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
            sim_ts_ms = event.get("timestamp_ms", ev_idx * 100)

            strategy_snapshot: dict[str, dict] = {}
            step_fills: list[dict] = []

            for s in strategies:
                trade_slice = schedules[s.name][step_idx]
                qty = trade_slice.qty

                if qty > 1e-12:
                    order = Order(
                        strategy_name=s.name,
                        qty=qty,
                        timestamp_ms=sim_ts_ms,
                    )
                    fill = exchanges[s.name].execute(order)
                    if fill is not None:
                        step_fills.append({
                            "timestamp_ms": fill.timestamp_ms,
                            "strategy": s.name,
                            "qty": fill.qty_filled,
                            "price": fill.fill_price,
                            "slippage_bps": fill.slippage_bps,
                            "temp_impact": float(fill.temp_impact),
                        })

                ex = exchanges[s.name]
                shares_rem = ex.shares_remaining
                shares_remaining_track[s.name].append(shares_rem)

                cum_is_bps = ex.implementation_shortfall_bps
                cost_curve_track[s.name].append(cum_is_bps)

                strategy_snapshot[s.name] = {
                    "shares_remaining": shares_rem,
                    "avg_price": ex.avg_fill_price,
                    "cumulative_cost_bps": cum_is_bps,
                    "qty_traded": qty,
                }

            mid_price = event.get("mid", (event["bid"] + event["ask"]) / 2.0)

            snapshot = {
                "type": "snapshot",
                "step": step_count,
                "total_steps": N,
                "mid_price": mid_price,
                "timestamp_ms": sim_ts_ms,
                "strategies": strategy_snapshot,
                "new_fills": step_fills,
                "data_mode": "l2_real" if using_real_data else "l2_synthetic",
            }

            # ----------------------------------------------------------
            # WebSocket throttle: only broadcast every ui_throttle_ms ms
            # ----------------------------------------------------------
            now_mono = _time.monotonic()
            if now_mono - _last_broadcast_mono >= _throttle_interval:
                await on_snapshot(snapshot)
                _last_broadcast_mono = now_mono

            # Yield control to event loop occasionally
            if step_count % 5 == 0:
                await asyncio.sleep(0)

    # Ensure the final snapshot is always sent regardless of throttle.
    # Replace new_fills with ALL accumulated fills so the blotter is complete.
    if step_count > 0:
        all_accumulated_fills: list[dict] = []
        for s in strategies:
            for f in exchanges[s.name].fills:
                all_accumulated_fills.append({
                    "timestamp_ms": f.timestamp_ms,
                    "strategy": s.name,
                    "qty": f.qty_filled,
                    "price": f.fill_price,
                    "slippage_bps": f.slippage_bps,
                    "temp_impact": float(f.temp_impact),
                })
        snapshot["new_fills"] = all_accumulated_fills  # type: ignore[possibly-undefined]
        await on_snapshot(snapshot)  # type: ignore[possibly-undefined]

    # ------------------------------------------------------------------
    # 9. Assemble StrategyResults
    # ------------------------------------------------------------------
    arrival_price = exchanges["dump"].arrival_price

    def _build_result(strategy_name: str) -> StrategyResult:
        ex = exchanges[strategy_name]
        fills = ex.fills
        vwap_price = ex.avg_fill_price
        is_bps = ex.implementation_shortfall_bps

        trade_qtys = np.array([f.qty_filled for f in fills])
        traj_var = ac_model.trajectory_variance(trade_qtys) if len(trade_qtys) > 0 else 0.0

        if strategy_name == "ac":
            utility = float(ac_model.compute_AC_utility(config.total_shares))
        else:
            utility = is_bps + config.risk_aversion * traj_var

        return StrategyResult(
            name=strategy_name,
            fills=fills,
            vwap=vwap_price,
            implementation_shortfall_bps=is_bps,
            trajectory_variance=traj_var,
            utility=utility,
            trajectory=shares_remaining_track.get(strategy_name, []),
            cost_curve=cost_curve_track.get(strategy_name, []),
        )

    dump_result = _build_result("dump")
    twap_result = _build_result("twap")
    vwap_result = _build_result("vwap")
    ac_result = _build_result("ac")

    ac_savings_vs_dump = dump_result.implementation_shortfall_bps - ac_result.implementation_shortfall_bps
    ac_savings_vs_twap = twap_result.implementation_shortfall_bps - ac_result.implementation_shortfall_bps

    step_timestamps = [
        events[idx].get("timestamp_ms", idx * 100)
        for idx in step_trigger_indices
    ]

    return SimulationResult(
        config=config,
        dump=dump_result,
        twap=twap_result,
        vwap=vwap_result,
        ac=ac_result,
        price_series=price_series,
        ac_savings_vs_dump_bps=ac_savings_vs_dump,
        ac_savings_vs_twap_bps=ac_savings_vs_twap,
        step_timestamps=step_timestamps,
    )
