"""FastAPI entry point. The web layer only orchestrates — pipeline logic lives elsewhere.

Run locally from the backend/ folder:
    .venv/bin/uvicorn app.main:app --reload
"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings

app = FastAPI(title="AI Meeting Assistant")

# Allow the Vite dev server (the future frontend) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    """Confirm the server is running and show which models are configured (never keys)."""
    return {
        "status": "ok",
        "models": {
            "stt": settings.stt_model,
            "refiner": settings.refiner_model,
            "documenter": settings.documenter_model,
        },
    }
