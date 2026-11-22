"""AI Material Inspector — CV/OCR quality inspection for utility store receipts."""

from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.schemas import HealthOut
from app.services.bootstrap import init_database

settings = get_settings()
setup_logging(debug=settings.app_debug)
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    import threading

    init_database()

    def _warm() -> None:
        try:
            from app.services.ocr import warm_ocr

            warm_ocr()
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_warm, name="ocr-warm", daemon=True).start()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Computer vision + OCR material quality inspection against sample SAP purchase orders.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(api_router)


@app.middleware("http")
async def security_and_request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-ms"] = str(round((time.perf_counter() - started) * 1000, 1))
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/api/health", response_model=HealthOut, tags=["ops"])
def health():
    db_ok = "ok"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:  # noqa: BLE001
        db_ok = "error"
    return HealthOut(status="ok", version=settings.app_version, env=settings.app_env, database=db_ok)


@app.get("/api/ready", tags=["ops"])
def ready():
    return {"ready": True}


@app.get("/")
def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"app": settings.app_name, "docs": "/api/docs"})


@app.get("/login")
def login_page():
    page = STATIC_DIR / "login.html"
    if page.exists():
        return FileResponse(page)
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
