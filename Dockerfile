ARG PYTHON_VERSION=3.12
ARG SPACY_MODEL=en_core_web_sm

# ── base: shared dependency install ───────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS base
ARG SPACY_MODEL  # re-declared so it is in scope within this stage

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv

# Install directly into the system Python — no venv needed in containers
ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

# Dependencies first for layer caching — source changes don't bust this layer
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

COPY src/ ./src/
RUN uv pip install --no-deps . --no-cache-dir

# Download the spaCy model — separate layer so dep changes don't re-download
RUN uv run python -m spacy download ${SPACY_MODEL}

# ── runtime ───────────────────────────────────────────────────────────────────
FROM base AS runtime

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "alias.app:app", "--host", "0.0.0.0", "--port", "8000"]

# ── test ──────────────────────────────────────────────────────────────────────
FROM base AS test

# Add dev deps (pytest, httpx, etc.)
RUN uv sync --frozen --no-cache

COPY tests/ ./tests/

CMD ["uv", "run", "pytest", "tests/", "-v"]
