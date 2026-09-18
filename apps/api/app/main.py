"""NEXUS API — application entrypoint."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import agents, analytics, approvals, auth, documents, health, insights, notifications, risk, search
from .core.config import get_settings
from .core.errors import register_error_handlers
from .db.session import create_all
from .tasks.runner import get_runner


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_all()
    runner = get_runner()
    runner.start()
    yield
    runner.stop(timeout=5)


def create_app() -> FastAPI:
    app = FastAPI(
        title="NEXUS API",
        description="Personal Life Intelligence & Action OS",
        version="0.1.0",
        lifespan=lifespan,
    )
    # Dev-friendly CORS. Production deployments should pin the browser origin
    # (documented in docs/security.md).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    api = "/api/v1"
    app.include_router(auth.router, prefix=api)
    app.include_router(documents.router, prefix=api)
    app.include_router(search.router, prefix=api)
    app.include_router(insights.router, prefix=api)
    app.include_router(risk.router, prefix=api)
    app.include_router(agents.router, prefix=api)
    app.include_router(approvals.router, prefix=api)
    app.include_router(analytics.router, prefix=api)
    app.include_router(notifications.router, prefix=api)
    app.include_router(health.router, prefix=api)

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": "nexus-api", "docs": "/docs", "health": "/api/v1/health"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=False)
