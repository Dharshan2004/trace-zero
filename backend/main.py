"""
Trace-Zero API — FastAPI application entry point.

Start with:
    uvicorn backend.main:app --reload --port 8000

Or via the project script:
    python -m uvicorn backend.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.api.ws import ws_router

app = FastAPI(
    title="Trace-Zero API",
    description=(
        "Optimal Execution Simulator — compare Dump, TWAP, and "
        "Almgren-Chriss optimal strategies with live or replayed L1 data."
    ),
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — allow the Vite dev server (5173) and any localhost origin
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
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
