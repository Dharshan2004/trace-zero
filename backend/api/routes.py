"""
REST API routes for Trace-Zero.

Endpoints
---------
GET  /api/symbols                       List available JSONL data files
GET  /api/symbols/{symbol}/info         File metadata for a given symbol
POST /api/simulation/run                Launch a simulation (async, returns sim_id)
POST /api/capture                       Start a live Binance L1 capture
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.market_replay.loader import get_file_info, list_data_files
from backend.simulation.config import SimulationConfig

# Import the shared sim-store so WS can attach to running simulations
from backend.api.ws import _sim_store

router = APIRouter()

# ---------------------------------------------------------------------------
# Data directory (relative to project root)
# ---------------------------------------------------------------------------
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")


# ---------------------------------------------------------------------------
# Request / Response models (Pydantic)
# ---------------------------------------------------------------------------

class SimulationRunRequest(BaseModel):
    symbol: str = "BTCUSDT"
    total_shares: float = 1.0
    liquidation_time: float = 60.0
    num_trades: int = 20
    risk_aversion: float = 1e-6
    gamma_override: Optional[float] = None
    eta_override: Optional[float] = None
    data_file: Optional[str] = None


class CaptureRequest(BaseModel):
    symbol: str
    duration_seconds: int = 60


# ---------------------------------------------------------------------------
# Background simulation task
# ---------------------------------------------------------------------------

async def _run_sim_background(sim_id: str, config: SimulationConfig) -> None:
    """
    Background coroutine that runs the simulation and pushes results into
    the sim_id queue so the WebSocket handler can stream them.
    """
    # Import here to avoid circular imports at module load time
    from backend.simulation.runner import run_simulation

    queue: asyncio.Queue = _sim_store[sim_id]

    async def on_snapshot(snapshot: dict) -> None:
        await queue.put(snapshot)

    try:
        result = await run_simulation(config, on_snapshot)
        complete_msg = {
            "type": "complete",
            "result": result.to_dict(),
        }
        await queue.put(complete_msg)
    except Exception as exc:
        error_msg = {"type": "error", "message": str(exc)}
        await queue.put(error_msg)
    finally:
        # Signal that the producer is done (None sentinel)
        await queue.put(None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/symbols")
async def list_symbols() -> dict:
    """
    Return a list of available JSONL data files in the data/ directory.

    Each entry contains the filename and the symbol derived from the name.
    """
    files = list_data_files(_DATA_DIR)
    result = []
    for fpath in files:
        fname = os.path.basename(fpath)
        # Derive symbol from filename: BTCUSDT_60s.jsonl -> BTCUSDT
        symbol = fname.split("_")[0] if "_" in fname else fname.replace(".jsonl", "")
        result.append({"filename": fname, "symbol": symbol, "path": fpath})
    return {"symbols": result}


@router.get("/symbols/{symbol}/info")
async def get_symbol_info(symbol: str) -> dict:
    """
    Return metadata for the first JSONL file matching the given symbol.

    Raises 404 if no matching file is found.
    """
    files = list_data_files(_DATA_DIR)
    matched: Optional[str] = None
    for fpath in files:
        fname = os.path.basename(fpath)
        if fname.upper().startswith(symbol.upper()):
            matched = fpath
            break

    if matched is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data file found for symbol '{symbol}'. "
                   f"Use POST /api/capture or drop a JSONL file into data/.",
        )

    try:
        info = get_file_info(matched)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {exc}")

    return {"symbol": symbol, "file": os.path.basename(matched), **info}


@router.post("/simulation/run")
async def start_simulation(
    body: SimulationRunRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Launch an async simulation run.

    Returns a sim_id that the client can use to open a WebSocket at
    /api/simulation/{sim_id}/stream to receive incremental updates.
    """
    sim_id = str(uuid.uuid4())

    config = SimulationConfig(
        symbol=body.symbol,
        total_shares=body.total_shares,
        liquidation_time=body.liquidation_time,
        num_trades=body.num_trades,
        risk_aversion=body.risk_aversion,
        gamma_override=body.gamma_override,
        eta_override=body.eta_override,
        data_file=body.data_file,
    )

    # Create the queue before starting the background task so the WS
    # handler can find it even if it connects very quickly.
    _sim_store[sim_id] = asyncio.Queue()

    background_tasks.add_task(_run_sim_background, sim_id, config)

    return {"sim_id": sim_id}


@router.post("/capture")
async def capture_data(body: CaptureRequest, background_tasks: BackgroundTasks) -> dict:
    """
    Start a live Binance L1 capture in the background.

    The data is written to data/{symbol}_{duration}s.jsonl.
    """
    from backend.market_replay.collector import capture_binance_l1

    output_path = os.path.join(_DATA_DIR, f"{body.symbol}_{body.duration_seconds}s.jsonl")

    async def _capture() -> None:
        await capture_binance_l1(body.symbol, body.duration_seconds, output_path)

    background_tasks.add_task(_capture)

    return {
        "status": "capturing",
        "symbol": body.symbol,
        "duration_seconds": body.duration_seconds,
        "output_file": output_path,
    }
