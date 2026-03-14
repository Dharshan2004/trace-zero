"""
REST API routes for Trace-Zero.

Endpoints
---------
GET  /api/symbols                       List available data files (Parquet + JSONL)
GET  /api/symbols/{symbol}/info         File metadata for a given symbol
POST /api/simulation/run                Launch a simulation (async, returns sim_id)
POST /api/capture                       Start a live Binance L2 capture
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.market_replay.loader import get_file_info, list_data_files
from backend.simulation.config import SimulationConfig
from backend.api.ws import _sim_store

router = APIRouter()

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
    latency_ms: float = Field(default=0.0, ge=0.0, description="Network round-trip latency in ms")
    calibration_window: int = Field(default=100, ge=0, description="Rolling vol window size (0=static)")
    ui_throttle_ms: int = Field(default=50, ge=10, description="Min ms between WebSocket snapshots")


class CaptureRequest(BaseModel):
    symbol: str
    duration_seconds: int = 60
    use_l2: bool = True
    depth_levels: int = 20


# ---------------------------------------------------------------------------
# Background simulation task
# ---------------------------------------------------------------------------

async def _run_sim_background(sim_id: str, config: SimulationConfig) -> None:
    from backend.simulation.runner import run_simulation

    queue: asyncio.Queue = _sim_store[sim_id]

    async def on_snapshot(snapshot: dict) -> None:
        await queue.put(snapshot)

    try:
        result = await run_simulation(config, on_snapshot)
        await queue.put({"type": "complete", "result": result.to_dict()})
    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})
    finally:
        await queue.put(None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/symbols")
async def list_symbols() -> dict:
    """
    Return a list of available data files (Parquet preferred over JSONL).

    Each entry contains the filename, symbol, and format.
    """
    files = list_data_files(_DATA_DIR)
    result = []
    for fpath in files:
        fname = os.path.basename(fpath)
        ext = ".parquet" if fname.endswith(".parquet") else ".jsonl"
        stem = fname[: -len(ext)]
        symbol = stem.split("_")[0] if "_" in stem else stem
        result.append({
            "filename": fname,
            "symbol": symbol,
            "path": fpath,
            "format": ext.lstrip("."),
        })
    return {"symbols": result}


@router.get("/symbols/{symbol}/info")
async def get_symbol_info(symbol: str) -> dict:
    """
    Return metadata for the first file matching the given symbol.
    Parquet files take priority over JSONL files with the same stem.
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
                   f"Use POST /api/capture or drop a .parquet/.jsonl file into data/.",
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
        latency_ms=body.latency_ms,
        calibration_window=body.calibration_window,
        ui_throttle_ms=body.ui_throttle_ms,
    )

    _sim_store[sim_id] = asyncio.Queue()
    background_tasks.add_task(_run_sim_background, sim_id, config)

    return {"sim_id": sim_id}


@router.post("/capture")
async def capture_data(body: CaptureRequest, background_tasks: BackgroundTasks) -> dict:
    """
    Start a live Binance capture in the background.

    With use_l2=True (default) captures L2 depth20 + bookTicker combined stream
    and writes to data/{symbol}_{duration}s.parquet.
    With use_l2=False falls back to L1-only bookTicker stream.
    """
    from backend.market_replay.collector import capture_binance_l1, capture_binance_l2

    ext = ".parquet"
    output_path = os.path.join(_DATA_DIR, f"{body.symbol}_{body.duration_seconds}s{ext}")

    async def _capture() -> None:
        if body.use_l2:
            await capture_binance_l2(
                body.symbol, body.duration_seconds, output_path,
                depth_levels=body.depth_levels,
            )
        else:
            await capture_binance_l1(body.symbol, body.duration_seconds, output_path)

    background_tasks.add_task(_capture)

    return {
        "status": "capturing",
        "symbol": body.symbol,
        "duration_seconds": body.duration_seconds,
        "mode": "L2" if body.use_l2 else "L1",
        "output_file": output_path,
    }
