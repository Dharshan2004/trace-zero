"""
Binance WebSocket L1 data capture.

Connects to the Binance bookTicker stream for a given symbol, captures
events for a fixed duration, normalizes them, and writes to a JSONL file.
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

from backend.market_replay.normalizer import normalize_event
from backend.market_replay.logger import MarketLogger


# Binance Spot WebSocket base URL
_BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"


async def capture_binance_l1(
    symbol: str,
    duration_seconds: int,
    output_path: str,
) -> int:
    """
    Connect to Binance bookTicker WebSocket, capture L1 data for
    `duration_seconds`, normalize each event, and write to `output_path`.

    Parameters
    ----------
    symbol : str
        Binance symbol, e.g. 'BTCUSDT'. Will be lowercased for the stream URL.
    duration_seconds : int
        How long to capture in seconds.
    output_path : str
        Destination JSONL file path.

    Returns
    -------
    int
        Number of events captured.
    """
    if websockets is None:
        raise ImportError(
            "The 'websockets' package is required for capture. "
            "Install it with: pip install websockets"
        )

    stream_name = f"{symbol.lower()}@bookTicker"
    url = f"{_BINANCE_WS_BASE}/{stream_name}"

    # Ensure output directory exists
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
