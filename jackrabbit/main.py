"""Main FastAPI application for Jackrabbit."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from jackrabbit.api import router as api_router
from jackrabbit.database import init_db
from jackrabbit.web import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    init_db()
    yield
    # Shutdown (if needed)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Jackrabbit",
        description="Ticket tracking and sprint management system",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include routers
    app.include_router(api_router)
    app.include_router(web_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    from jackrabbit.config import get_settings

    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower())
