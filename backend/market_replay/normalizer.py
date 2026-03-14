"""
Normalizes raw Binance WebSocket events into a consistent internal format.

Supports two stream types:
  - bookTicker  : L1 best bid/ask (no depth)
  - depth20     : L2 full depth snapshot (up to 20 price levels each side)

The normalized format is a superset — L1 events have empty bid_levels/ask_levels,
L2 events populate them so the engine can walk the book for exact slippage.
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
        T  - transaction time (ms)
        E  - event time (ms)

    Returns
    -------
    dict with keys: symbol, bid, ask, mid, spread, timestamp_ms,
                    bid_levels (list of [price, qty]), ask_levels
    """
    try:
        bid = float(raw["b"])
        ask = float(raw["a"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(f"Cannot parse bid/ask from event: {raw!r}") from exc

    mid = (bid + ask) / 2.0
    spread = ask - bid

    timestamp_ms: int
    if "T" in raw:
        timestamp_ms = int(raw["T"])
    elif "E" in raw:
        timestamp_ms = int(raw["E"])
    else:
        timestamp_ms = int(time.time() * 1000)

    symbol = str(raw.get("s", "UNKNOWN"))

    # L1 events include best qty at top of book
    bid_qty = float(raw.get("B", 0.0))
    ask_qty = float(raw.get("A", 0.0))

    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "timestamp_ms": timestamp_ms,
        "bid_levels": [[bid, bid_qty]] if bid_qty > 0 else [],
        "ask_levels": [[ask, ask_qty]] if ask_qty > 0 else [],
    }


def normalize_l2_event(raw: dict, symbol: str, timestamp_ms: int) -> dict:
    """
    Convert a raw Binance depth snapshot event into a normalized L2 dict.

    Binance depth20 payload keys:
        lastUpdateId : int
        bids         : list of [price_str, qty_str]  — best first
        asks         : list of [price_str, qty_str]  — best first

    Parameters
    ----------
    raw : dict
        The 'data' sub-dict from a combined stream depth event, or the
        raw depth message itself.
    symbol : str
        Symbol extracted from the stream name.
    timestamp_ms : int
        Timestamp from the outer envelope (E field).

    Returns
    -------
    dict
        Normalized event with bid_levels and ask_levels populated.
    """
    try:
        raw_bids: list = raw.get("bids", [])
        raw_asks: list = raw.get("asks", [])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Cannot parse depth event: {raw!r}") from exc

    bid_levels = [[float(p), float(q)] for p, q in raw_bids if float(q) > 0]
    ask_levels = [[float(p), float(q)] for p, q in raw_asks if float(q) > 0]

    if not bid_levels or not ask_levels:
        raise ValueError(f"Empty depth event for {symbol}")

    bid = bid_levels[0][0]
    ask = ask_levels[0][0]
    mid = (bid + ask) / 2.0
    spread = ask - bid

    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "timestamp_ms": timestamp_ms,
        "bid_levels": bid_levels,
        "ask_levels": ask_levels,
    }
