"""
FastAPI application entry point.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers.certificates import router as certificates_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create DB tables and output directory."""
    await init_db()
    os.makedirs("certificates", exist_ok=True)
    yield


app = FastAPI(
    title="Bulk Certificate Generator",
    description=(
        "A backend API that accepts certificate generation requests for a "
        "list of recipients and generates PDF certificates using a predefined "
        "template. Supports bulk processing, status tracking, and individual "
        "certificate download."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(certificates_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "healthy"}
