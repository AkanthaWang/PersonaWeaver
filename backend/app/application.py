"""FastAPI application assembly.

This module only wires infrastructure, routers and the SPA fallback. Business
logic lives in ``backend.app.domains``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.health import router as health_router
from .api.router import router as api_router
from .core.config import ROOT, Config
from .db.database import Database


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.from_env()
    db = Database(config.database_path)
    uploads = config.data_dir / "uploads"
    avatars = config.data_dir / "avatars"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        uploads.mkdir(parents=True, exist_ok=True)
        avatars.mkdir(parents=True, exist_ok=True)
        db.initialize()
        from .domains.conversation.mirror import recover_mirrors
        recover_mirrors(db)
        from .domains.conversation.generation import GenerationEngine
        app.state.conversation_engine = GenerationEngine(db)
        app.state.conversation_engine.recover()
        try:
            yield
        finally:
            await app.state.conversation_engine.shutdown()

    app = FastAPI(title="PersonaWeaver Local API", version="3.0.0", lifespan=lifespan)
    app.state.db = db
    app.state.config = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(health_router)
    app.include_router(api_router)
    dist = ROOT.parent / "frontend" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404)
            return FileResponse(dist / "index.html")

    return app
