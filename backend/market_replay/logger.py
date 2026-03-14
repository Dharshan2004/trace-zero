"""
Dual-format market data logger: Parquet (default) or JSONL (legacy fallback).

Parquet via Polars is ~80% smaller than JSONL and loads nearly instantaneously
from disk — critical when running thousands of backtests. Events are buffered
in memory and flushed to a single columnar Parquet file on close().

If polars is not installed or the path does not end with .parquet, the logger
falls back to streaming NDJSON (line-buffered, compatible with older captures).
"""

import json
import os

try:
    import polars as pl
    _POLARS_AVAILABLE = True
except ImportError:
    _POLARS_AVAILABLE = False


class MarketLogger:
    """
    Writes normalized market events to a Parquet or JSONL file.

    Usage
    -----
        with MarketLogger("data/BTCUSDT_60s.parquet") as logger:
            logger.write(event_dict)

    Parquet mode
    ------------
    Events are buffered in-memory and written as a single .parquet file
    on close() using Snappy compression. This means no partial writes are
    visible on disk until the context manager exits — appropriate for
    capture sessions where atomicity is preferred.

    JSONL mode (fallback)
    ---------------------
    Events are appended line-by-line immediately. Multiple capture sessions
    can be concatenated into the same file.
    """

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._use_parquet = _POLARS_AVAILABLE and filepath.endswith(".parquet")
        self._closed = False
        self._count = 0

        if self._use_parquet:
            self._rows: list[dict] = []
            self._file = None
        else:
            self._rows = []
            self._file = open(filepath, "a", encoding="utf-8", buffering=1)

    def write(self, event: dict) -> None:
        """Serialize event and buffer (Parquet) or append (JSONL)."""
        if self._closed:
            raise IOError(f"MarketLogger for {self.filepath!r} is already closed.")
        if self._use_parquet:
            self._rows.append(event)
        else:
            line = json.dumps(event, separators=(",", ":"))
            self._file.write(line + "\n")  # type: ignore[union-attr]
        self._count += 1

    def flush(self) -> None:
        """Flush JSONL buffer to disk. No-op in Parquet mode."""
        if not self._closed and not self._use_parquet and self._file:
            self._file.flush()

    def close(self) -> None:
        """Flush and finalize. Parquet mode writes the file atomically here."""
        if self._closed:
            return
        if self._use_parquet and self._rows:
            df = pl.DataFrame(self._rows)
            df.write_parquet(self.filepath, compression="snappy")
        elif self._file:
            self._file.flush()
            self._file.close()
        self._closed = True

    @property
    def events_written(self) -> int:
        return self._count

    def __enter__(self) -> "MarketLogger":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
