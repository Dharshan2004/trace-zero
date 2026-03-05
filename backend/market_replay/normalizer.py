"""
Normalizes raw Binance bookTicker WebSocket events into a consistent
internal format consumed by the rest of the market_replay pipeline.
"""

import time


def normalize_event(raw: dict) -> dict:
    """
    Convert a raw Binance bookTicker event to a normalized dict.

    Binance bookTicker payload keys:
        u  - order book update id
        s  - symbol  (e.g. 'BTCUSDT')
        b  - best bid price (string)
        B  - best bid qty  (string)
        a  - best ask price (string)
        A  - best ask qty  (string)
        T  - transaction time (ms)  -- present in combined stream events
        E  - event time (ms)        -- present in combined stream events

    Returns
    -------
    dict with keys: symbol, bid, ask, mid, spread, timestamp_ms
    """
    try:
        bid = float(raw["b"])
        ask = float(raw["a"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(f"Cannot parse bid/ask from event: {raw!r}") from exc

    mid = (bid + ask) / 2.0
    spread = ask - bid

    # Prefer transaction time, then event time, then wall clock
    timestamp_ms: int
    if "T" in raw:
        timestamp_ms = int(raw["T"])
    elif "E" in raw:
        timestamp_ms = int(raw["E"])
    else:
        timestamp_ms = int(time.time() * 1000)

    symbol = str(raw.get("s", "UNKNOWN"))

    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "timestamp_ms": timestamp_ms,
    }
