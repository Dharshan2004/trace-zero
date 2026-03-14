"""
Market replay data loading utilities — supports Parquet (via Polars) and JSONL.

Parquet files are loaded nearly instantaneously compared to JSONL line-parsing
(~10–50x faster for large captures). Both formats are auto-detected by extension.

list_data_files() returns .parquet files first (preferred), then .jsonl legacy
files. If both a .parquet and .jsonl exist for the same symbol, the .parquet
takes precedence.
"""

import json
import os
from typing import Optional

try:
    import polars as pl
    _POLARS_AVAILABLE = True
except ImportError:
    _POLARS_AVAILABLE = False


def load_file(filepath: str) -> list[dict]:
    """
    Load all events from a Parquet or JSONL file into memory.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to a .parquet or .jsonl file.

    Returns
    -------
    list[dict]
        Ordered list of event dicts. Malformed lines (JSONL) are skipped.
    """
    if filepath.endswith(".parquet"):
        return _load_parquet(filepath)
    return _load_jsonl(filepath)


def _load_parquet(filepath: str) -> list[dict]:
    if not _POLARS_AVAILABLE:
        raise ImportError(
            "polars is required to read .parquet files. "
            "Install it with: pip install polars pyarrow"
        )
    df = pl.read_parquet(filepath)
    # Polars returns nested lists for bid_levels/ask_levels correctly
    return df.to_dicts()


def _load_jsonl(filepath: str) -> list[dict]:
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
    List available data files in the data directory.

    Returns .parquet files first (preferred), then .jsonl files — both
    sorted by filename. Files are deduplicated so a .parquet file shadows
    its .jsonl counterpart (same stem).

    Returns absolute paths.
    """
    if not os.path.isdir(data_dir):
        return []

    all_files = sorted(os.listdir(data_dir))
    parquet_stems: set[str] = set()
    result: list[str] = []

    # Pass 1: collect parquet files
    for f in all_files:
        if f.endswith(".parquet"):
            result.append(os.path.join(data_dir, f))
            parquet_stems.add(f[: -len(".parquet")])

    # Pass 2: add jsonl files only if no parquet equivalent exists
    for f in all_files:
        if f.endswith(".jsonl"):
            stem = f[: -len(".jsonl")]
            if stem not in parquet_stems:
                result.append(os.path.join(data_dir, f))

    return result


def get_file_info(filepath: str) -> dict:
    """
    Return summary metadata without loading the full file into memory.

    Returns
    -------
    dict with keys:
        event_count   : int
        time_range_ms : int   (last_ts - first_ts)
        price_range   : dict  {min_mid, max_mid, first_mid, last_mid}
        symbol        : str
        format        : str   ('parquet' or 'jsonl')
    """
    if filepath.endswith(".parquet"):
        return _get_parquet_info(filepath)
    return _get_jsonl_info(filepath)


def _get_parquet_info(filepath: str) -> dict:
    if not _POLARS_AVAILABLE:
        raise ImportError("polars is required to read .parquet files.")

    df = pl.read_parquet(filepath)
    event_count = len(df)

    symbol = "UNKNOWN"
    if "symbol" in df.columns and event_count > 0:
        symbol = str(df["symbol"][0])

    first_ts = last_ts = None
    if "timestamp_ms" in df.columns and event_count > 0:
        ts_col = df["timestamp_ms"].cast(pl.Int64)
        first_ts = int(ts_col[0])
        last_ts = int(ts_col[-1])

    first_mid = last_mid = min_mid = max_mid = None
    if "mid" in df.columns and event_count > 0:
        mid_col = df["mid"].cast(pl.Float64)
        first_mid = float(mid_col[0])
        last_mid = float(mid_col[-1])
        min_mid = float(mid_col.min())  # type: ignore[arg-type]
        max_mid = float(mid_col.max())  # type: ignore[arg-type]
    elif "bid" in df.columns and "ask" in df.columns and event_count > 0:
        mid_col = (df["bid"].cast(pl.Float64) + df["ask"].cast(pl.Float64)) / 2.0
        first_mid = float(mid_col[0])
        last_mid = float(mid_col[-1])
        min_mid = float(mid_col.min())  # type: ignore[arg-type]
        max_mid = float(mid_col.max())  # type: ignore[arg-type]

    return {
        "event_count": event_count,
        "time_range_ms": (last_ts - first_ts) if (first_ts is not None and last_ts is not None) else 0,
        "price_range": {
            "min_mid": min_mid,
            "max_mid": max_mid,
            "first_mid": first_mid,
            "last_mid": last_mid,
        },
        "symbol": symbol,
        "format": "parquet",
    }


def _get_jsonl_info(filepath: str) -> dict:
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

            mid_val = event.get("mid")
            if mid_val is None:
                bid = event.get("bid")
                ask = event.get("ask")
                if bid is not None and ask is not None:
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
        "format": "jsonl",
    }
