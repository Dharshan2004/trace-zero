#!/usr/bin/env python3
"""
Quick script to capture live Binance L1 orderbook data.

Usage
-----
    python scripts/capture_data.py [SYMBOL] [DURATION_SECONDS]

Examples
--------
    python scripts/capture_data.py BTCUSDT 60
    python scripts/capture_data.py ETHUSDT 120

Output is written to data/{SYMBOL}_{DURATION}s.jsonl relative to the
project root.
"""

import asyncio
import os
import sys

# Allow running from project root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.market_replay.collector import capture_binance_l1


async def main() -> None:
    symbol: str = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    duration: int = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    # Resolve data directory relative to project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)

    output = os.path.join(data_dir, f"{symbol}_{duration}s.jsonl")

    print(f"Capturing {symbol} for {duration}s -> {output}")
    count = await capture_binance_l1(symbol, duration, output)
    print(f"Done. Captured {count} events.")


if __name__ == "__main__":
    asyncio.run(main())
