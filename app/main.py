"""FastAPI application factory."""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router
from app.api.websocket import ws_router

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    app = FastAPI(
        title="Texas Hold'em Poker",
        description="Web-based Texas Hold'em with AI bots",
        version="1.0.0",
    )

    # Templates
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.state.templates = templates

    # Static files
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    # Routers
    app.include_router(router)
    app.include_router(ws_router)

    return app


app = create_app()
