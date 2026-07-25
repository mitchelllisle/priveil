"""Entry point for the Priveil API server.

Run with::

    python -m priveil                  # uses defaults from environment / .env
    uv run python -m priveil

The server binds to ``0.0.0.0:8000`` by default.  Set ``PRIVEIL_DEBUG=true``
to enable hot-reload (development only).
"""

from __future__ import annotations

import logging


def main() -> None:
    """Start the Priveil FastAPI server.

    Loads settings from the environment (``PRIVEIL_*`` prefix) and delegates
    to uvicorn.  Hot-reload is enabled when ``PRIVEIL_DEBUG=true``.
    """
    import uvicorn

    from priveil.settings import Settings

    settings = Settings()

    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    uvicorn.run(
        "priveil.app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    main()
