from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from alias.api.routes import health
from alias.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hook — engines are wired here as slices land."""
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return the configured FastAPI application.

    Args:
        settings: Optional override; defaults to env-driven Settings().

    Returns:
        A fully configured FastAPI app.
    """
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="Alias",
        description="Pseudonymisation service for Australian financial context",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(health.router)

    return app


app = create_app()
