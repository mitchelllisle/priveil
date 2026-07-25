ARG PYTHON_VERSION=3.12

# ── setup: uv + manifest only (shared cache layer) ────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS setup

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv

ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY pyproject.toml uv.lock ./

# ── base: production dependency install ───────────────────────────────────────
FROM setup AS base

RUN uv sync --frozen --no-dev --no-cache

COPY src/ ./src/
RUN uv pip install --no-deps . --no-cache-dir

# ── local: gliner + mcp extras for CPU-only local development ─────────────────
# No NVIDIA GPU required. Provides both the API and MCP server in one image.
FROM setup AS local

RUN uv sync --frozen --no-dev --extra gliner --extra mcp --no-cache

COPY src/ ./src/
RUN uv pip install --no-deps . --no-cache-dir

EXPOSE 8000
# Default CMD runs the API; override to "python -m priveil.mcp" for the MCP service.
CMD ["uv", "run", "python", "-m", "priveil"]

# ── runtime ───────────────────────────────────────────────────────────────────
FROM base AS runtime
EXPOSE 8000
CMD ["uv", "run", "python", "-m", "priveil"]

# ── test ──────────────────────────────────────────────────────────────────────
FROM base AS test

# --all-groups includes dev group in one step.
RUN uv sync --frozen --all-groups --no-cache

COPY tests/ ./tests/

CMD ["uv", "run", "pytest", "tests/", "-v"]
