"""
Trace-Zero API — FastAPI application entry point.

Start with:
    uvicorn backend.main:app --reload --port 8000

Or via the project script:
    python -m uvicorn backend.main:app --reload
"""

import asyncio
import glob
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.api.ws import ws_router

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ---------------------------------------------------------------------------
# Startup: auto-capture Binance L2 data if data/ is empty
# ---------------------------------------------------------------------------
# Set AUTO_CAPTURE=false to disable (e.g. local dev where you don't want it).
# Set CAPTURE_SYMBOL / CAPTURE_SECONDS to override defaults.
# ---------------------------------------------------------------------------

async def _auto_capture() -> None:
    """Background task: capture real Binance L2 data on cold start."""
    symbol = os.environ.get("CAPTURE_SYMBOL", "BTCUSDT")
    duration = int(os.environ.get("CAPTURE_SECONDS", "60"))
    output_path = os.path.join(_DATA_DIR, f"{symbol}_{duration}s.parquet")

    # Skip if a data file already exists
    existing = glob.glob(os.path.join(_DATA_DIR, "*.parquet")) + \
               glob.glob(os.path.join(_DATA_DIR, "*.jsonl"))
    if existing:
        logger.info("Auto-capture skipped: data files already present (%s)", existing[0])
        return

    logger.info("Auto-capture: starting %ds %s L2 capture → %s", duration, symbol, output_path)
    try:
        from backend.market_replay.collector import capture_binance_l2
        os.makedirs(_DATA_DIR, exist_ok=True)
        await capture_binance_l2(symbol, duration, output_path, depth_levels=20)
        logger.info("Auto-capture complete: %s", output_path)
    except Exception as exc:
        logger.warning("Auto-capture failed (will use synthetic data): %s", exc)


@asynccontextmanager
async def lifespan(application: FastAPI):  # type: ignore[type-arg]
    auto_capture_enabled = os.environ.get("AUTO_CAPTURE", "true").lower() != "false"
    if auto_capture_enabled:
        asyncio.create_task(_auto_capture())
    yield


app = FastAPI(
    title="Trace-Zero API",
    description=(
        "Optimal Execution Simulator — compare Dump, TWAP, and "
        "Almgren-Chriss optimal strategies with live or replayed L1 data."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — localhost for dev, plus the production frontend URL from env
# ---------------------------------------------------------------------------
_cors_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
# Set FRONTEND_URL on Railway/Fly to your Vercel deployment URL
# e.g. https://trace-zero.vercel.app
_frontend_url = os.environ.get("FRONTEND_URL", "")
if _frontend_url:
    _cors_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(router, prefix="/api")
app.include_router(ws_router, prefix="/api")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "trace-zero"}
