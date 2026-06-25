ARG PYTHON_VERSION=3.12
ARG SPACY_MODEL=en_core_web_sm

# ── base: shared production dependency install ────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv

ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

# Deps before source for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

COPY src/ ./src/
RUN uv pip install --no-deps . --no-cache-dir

# ── runtime ───────────────────────────────────────────────────────────────────
FROM base AS runtime

# spaCy model downloaded last — after all uv sync calls so it isn't pruned
ARG SPACY_MODEL
RUN uv run python -m spacy download ${SPACY_MODEL}

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "alias.app:app", "--host", "0.0.0.0", "--port", "8000"]

# ── test ──────────────────────────────────────────────────────────────────────
FROM base AS test

# Dev deps (pytest, httpx, etc.) — must come before model download
RUN uv sync --frozen --no-cache

COPY tests/ ./tests/

# spaCy model downloaded last — after uv sync so it isn't pruned from the venv
ARG SPACY_MODEL
RUN uv run python -m spacy download ${SPACY_MODEL}

CMD ["uv", "run", "pytest", "tests/", "-v"]
