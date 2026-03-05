"""
JSONL loading utilities for market replay data.

Provides helpers to load event files, list available datasets, and
inspect file metadata without loading the full payload.
"""

import json
import os
from typing import Optional


def load_file(filepath: str) -> list[dict]:
    """
    Load all events from a JSONL file into memory.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to a .jsonl file.

    Returns
    -------
    list[dict]
        Ordered list of event dicts. Malformed lines are skipped.
    """
    events: list[dict] = []
    with open(filepath, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def list_data_files(data_dir: str = "data") -> list[str]:
    """
    List available .jsonl files in the data directory.

    Returns absolute paths sorted by filename.
    """
    if not os.path.isdir(data_dir):
        return []
    files = [
        os.path.join(data_dir, f)
        for f in sorted(os.listdir(data_dir))
        if f.endswith(".jsonl")
    ]
    return files


def get_file_info(filepath: str) -> dict:
    """
    Return summary metadata for a JSONL event file without loading it fully.

    Returns
    -------
    dict with keys:
        event_count  : int
        time_range_ms: int  (last_ts - first_ts)
        price_range  : dict {min_mid, max_mid, first_mid, last_mid}
        symbol       : str
    """
    event_count = 0
    first_ts: Optional[int] = None
    last_ts: Optional[int] = None
    first_mid: Optional[float] = None
    last_mid: Optional[float] = None
    min_mid: Optional[float] = None
    max_mid: Optional[float] = None
    symbol: str = "UNKNOWN"

    with open(filepath, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_count += 1

            ts = event.get("timestamp_ms")
            if ts is not None:
                ts = int(ts)
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            bid = event.get("bid")
            ask = event.get("ask")
            mid_val = event.get("mid")
            if mid_val is None and bid is not None and ask is not None:
                mid_val = (float(bid) + float(ask)) / 2.0

            if mid_val is not None:
                mid_val = float(mid_val)
                if first_mid is None:
                    first_mid = mid_val
                last_mid = mid_val
                min_mid = mid_val if min_mid is None else min(min_mid, mid_val)
                max_mid = mid_val if max_mid is None else max(max_mid, mid_val)

            sym = event.get("symbol")
            if sym and symbol == "UNKNOWN":
                symbol = str(sym)

    time_range_ms = (last_ts - first_ts) if (first_ts is not None and last_ts is not None) else 0

    return {
        "event_count": event_count,
        "time_range_ms": time_range_ms,
        "price_range": {
            "min_mid": min_mid,
            "max_mid": max_mid,
            "first_mid": first_mid,
            "last_mid": last_mid,
        },
        "symbol": symbol,
    }
