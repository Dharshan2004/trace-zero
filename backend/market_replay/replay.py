"""
Generator-based market event replay.

No sleep / no rate limiting here — the caller (simulation runner) controls
pacing by consuming events at its own rate.
"""

import json
from typing import Generator


def replay_events(events: list[dict]) -> Generator[dict, None, None]:
    """
    Yield events one by one from an in-memory list.

    No sleep, no timing — purely a generator adapter so the simulation
    runner can iterate over events in a uniform way regardless of source.
    """
    for event in events:
        yield event


def replay_file(filepath: str) -> Generator[dict, None, None]:
    """
    Load a JSONL file and yield each event as a dict.

    Unlike load_file(), this generator streams line-by-line so very large
    files do not need to be fully loaded into memory before replay begins.
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                yield event
            except json.JSONDecodeError:
                # Skip malformed lines silently
                continue
