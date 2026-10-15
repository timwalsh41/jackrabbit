"""Main FastAPI application for Jackrabbit."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from jackrabbit.api import router as api_router
from jackrabbit.database import init_db
from jackrabbit.web import router as web_router
from jackrabbit.web import templates


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

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
        """Render the HTML 404 page for browser requests to web routes.

        API routes (and non-HTML clients) keep the JSON error body.
        """
        wants_html = "text/html" in request.headers.get("accept", "")
        if exc.status_code == 404 and wants_html and not request.url.path.startswith("/api/"):
            return templates.TemplateResponse(
                request,
                "404.html",
                {"request": request},
                status_code=404,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    from jackrabbit.config import get_settings

    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower())
