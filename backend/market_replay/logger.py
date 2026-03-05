"""
NDJSON (newline-delimited JSON) file writer for market events.

Each call to write() appends a single JSON object followed by a newline,
forming a valid JSONL file that can be streamed line-by-line.
"""

import json
import os
from typing import Optional


class MarketLogger:
    """
    Writes normalized market events to a JSONL file.

    Usage
    -----
        logger = MarketLogger("data/BTCUSDT_60s.jsonl")
        logger.write(event_dict)
        logger.close()

    The file is opened in append mode so that multiple capture sessions
    can be concatenated into the same file if desired.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        # Ensure the parent directory exists
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._file = open(filepath, "a", encoding="utf-8", buffering=1)
        self._closed = False
        self._count = 0

    def write(self, event: dict) -> None:
        """Serialize event to JSON and append a newline."""
        if self._closed:
            raise IOError(f"MarketLogger for {self.filepath!r} is already closed.")
        line = json.dumps(event, separators=(",", ":"))
        self._file.write(line + "\n")
        self._count += 1

    def flush(self) -> None:
        """Flush internal buffer to disk."""
        if not self._closed:
            self._file.flush()

    def close(self) -> None:
        """Flush and close the underlying file handle."""
        if not self._closed:
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
