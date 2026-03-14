"""
Binance WebSocket L2 data capture.

Connects to the Binance combined stream for bookTicker (L1) and depth20
(L2 depth snapshot) simultaneously, merges them into unified normalized
events, and writes to a Parquet or JSONL file.

Stream selection
----------------
- bookTicker  : fires on every best-bid/ask change — very high frequency
- depth20@100ms : full 20-level snapshot every 100ms — manageable rate

We subscribe to both via the combined stream endpoint and merge on symbol.
When a depth update arrives, it is emitted as a normalized L2 event.
When only a bookTicker arrives (between depth snapshots), it is emitted as
an L1 event (bid_levels has just the best level from bookTicker qty fields).
"""

import asyncio
import json
import os
import time
from typing import Optional

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore

from backend.market_replay.normalizer import normalize_event, normalize_l2_event
from backend.market_replay.logger import MarketLogger

_BINANCE_WS_BASE = "wss://stream.binance.com:9443"


async def capture_binance_l2(
    symbol: str,
    duration_seconds: int,
    output_path: str,
    depth_levels: int = 20,
) -> int:
    """
    Connect to Binance combined stream (bookTicker + depth), capture L2 data
    for `duration_seconds`, and write to `output_path` (.parquet or .jsonl).

    The combined stream delivers both streams multiplexed. We emit one event
    per depth snapshot (100ms cadence) enriched with best bid/ask from the
    most recent bookTicker update.

    Parameters
    ----------
    symbol : str
        Binance symbol, e.g. 'BTCUSDT'.
    duration_seconds : int
        How long to capture in seconds.
    output_path : str
        Destination file path (.parquet preferred, .jsonl for legacy).
    depth_levels : int
        Number of orderbook levels to capture per side (5, 10, or 20).

    Returns
    -------
    int
        Number of events written.
    """
    if websockets is None:
        raise ImportError(
            "The 'websockets' package is required for capture. "
            "Install it with: pip install websockets"
        )

    sym_lower = symbol.lower()
    valid_levels = {5, 10, 20}
    if depth_levels not in valid_levels:
        depth_levels = 20

    # Combined stream: both feeds on one connection
    book_stream = f"{sym_lower}@bookTicker"
    depth_stream = f"{sym_lower}@depth{depth_levels}@100ms"
    urls_to_try = [
        f"{_BINANCE_WS_BASE}/stream?streams={book_stream}/{depth_stream}",
        f"wss://stream.binance.com:443/stream?streams={book_stream}/{depth_stream}",
    ]

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    count = 0
    deadline = time.monotonic() + duration_seconds

    # State: latest L1 quote (updated on every bookTicker event)
    _latest_l1: dict = {}

    connected_ws = None
    for url in urls_to_try:
        try:
            connected_ws = await websockets.connect(url, ping_interval=20, ping_timeout=10)
            break
        except Exception:
            continue

    with MarketLogger(output_path) as logger:
        if connected_ws is None:
            # All URLs failed (geo-block, rate-limit, network) — fall back to L1
            return await capture_binance_l1(symbol, duration_seconds, output_path)

        async with connected_ws as ws:
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    break

                try:
                    envelope = json.loads(raw_msg)
                except json.JSONDecodeError:
                    continue

                # Combined stream wraps each message: {"stream": "...", "data": {...}}
                stream_name: str = envelope.get("stream", "")
                data: dict = envelope.get("data", envelope)
                event_time_ms = int(data.get("E", time.time() * 1000))

                if "@bookTicker" in stream_name:
                    # Update cached L1 quote
                    try:
                        _latest_l1 = normalize_event(data)
                    except ValueError:
                        pass

                elif f"@depth" in stream_name:
                    # Emit an L2 event
                    try:
                        event = normalize_l2_event(data, symbol, event_time_ms)
                    except ValueError:
                        continue

                    # Overlay the latest L1 best bid/ask if available and fresher
                    if _latest_l1:
                        event["bid"] = _latest_l1["bid"]
                        event["ask"] = _latest_l1["ask"]
                        event["mid"] = (_latest_l1["bid"] + _latest_l1["ask"]) / 2.0
                        event["spread"] = _latest_l1["ask"] - _latest_l1["bid"]
                        # Overwrite top-of-book level with L1 quantities
                        if _latest_l1.get("bid_levels"):
                            event["bid_levels"][0] = _latest_l1["bid_levels"][0]
                        if _latest_l1.get("ask_levels"):
                            event["ask_levels"][0] = _latest_l1["ask_levels"][0]

                    logger.write(event)
                    count += 1

    return count


async def capture_binance_l1(
    symbol: str,
    duration_seconds: int,
    output_path: str,
) -> int:
    """
    Legacy L1-only capture via bookTicker stream.

    Kept for backward compatibility. Prefer capture_binance_l2() for new
    captures — it enriches the feed with full depth information.
    """
    if websockets is None:
        raise ImportError("The 'websockets' package is required for capture.")

    stream_name = f"{symbol.lower()}@bookTicker"
    url = f"{_BINANCE_WS_BASE}/ws/{stream_name}"

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    count = 0
    deadline = time.monotonic() + duration_seconds

    with MarketLogger(output_path) as logger:
        async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    break

                try:
                    raw = json.loads(raw_msg)
                except json.JSONDecodeError:
                    continue

                try:
                    normalized = normalize_event(raw)
                except ValueError:
                    continue

                logger.write(normalized)
                count += 1

    return count
