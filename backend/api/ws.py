"""
WebSocket endpoint for streaming simulation progress.

Architecture
------------
- POST /api/simulation/run creates a UUID sim_id and an asyncio.Queue,
  stores them in _sim_store, and starts a background simulation task.
- The simulation runner calls on_snapshot() which puts messages into the queue.
- The client opens WS /api/simulation/{sim_id}/stream.
- This handler pulls from the queue and forwards JSON to the client.
- A None sentinel in the queue signals completion.

Message types
-------------
  {type: "snapshot", step, total_steps, mid_price, timestamp_ms, strategies}
  {type: "complete", result}
  {type: "error", message}
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# Module-level store: sim_id -> asyncio.Queue
# Routes module imports this dict to register new simulations.
_sim_store: dict[str, asyncio.Queue] = {}

ws_router = APIRouter()


@ws_router.websocket("/simulation/{sim_id}/stream")
async def simulation_stream(websocket: WebSocket, sim_id: str) -> None:
    """
    Stream simulation snapshots to the connected WebSocket client.

    1. Accept the connection.
    2. Wait (with timeout) for the sim_id queue to appear in _sim_store.
    3. Pull messages from the queue and forward as JSON text frames.
    4. Close cleanly when None sentinel or "complete" message arrives.
    """
    await websocket.accept()

    # Wait up to 10 seconds for the simulation to register its queue
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 10.0
    while sim_id not in _sim_store:
        if loop.time() > deadline:
            await websocket.send_text(
                json.dumps({"type": "error", "message": f"sim_id '{sim_id}' not found."})
            )
            await websocket.close()
            return
        await asyncio.sleep(0.05)

    queue: asyncio.Queue = _sim_store[sim_id]

    try:
        while True:
            try:
                # Poll the queue with a timeout so we can detect client disconnects
                message: Any = await asyncio.wait_for(queue.get(), timeout=60.0)
            except asyncio.TimeoutError:
                # Send a keepalive ping to detect stale connections
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except WebSocketDisconnect:
                    break
                continue

            if message is None:
                # Sentinel: simulation producer is done
                break

            try:
                await websocket.send_text(json.dumps(message, default=_json_default))
            except WebSocketDisconnect:
                break

            # If the simulation is complete, close after sending
            if isinstance(message, dict) and message.get("type") == "complete":
                break

    except WebSocketDisconnect:
        pass
    finally:
        # Clean up the queue from the store to free memory
        _sim_store.pop(sim_id, None)
        try:
            await websocket.close()
        except Exception:
            pass


def _json_default(obj: Any) -> Any:
    """Fallback JSON serializer for non-standard types."""
    if hasattr(obj, "__float__"):
        return float(obj)
    if hasattr(obj, "__int__"):
        return int(obj)
    return str(obj)
