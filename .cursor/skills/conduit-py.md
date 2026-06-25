---
name: conduit-py
description: >
  Python tooling for the conduit discipline — Pydantic at every serialization
  boundary, pure composable functions, stdlib-first functional style,
  Google-style docstrings, and a pytest + hypothesis test stack.
  Read conduit-core for the ladder, philosophy, and security principles.
argument-hint: "[lite|full|ultra]"
---

> Read `conduit-core` before this file. This skill adds Python-specific tooling.

# Conduit — Python

## Data & Types

- Pydantic models at every serialization boundary: API inputs, env vars (`BaseSettings`), external service responses.
- Never reach into deserialized JSON with `.get()` chains when a model exists. Use `Model.model_validate(data)`.
- Type hints on every function signature, return type included.
- Immutable by default: frozen Pydantic models, tuples over lists where mutation adds nothing.
- Never use `Any` without `# conduit: Any here because [reason]`.

## Functional Style

- Pure functions are the default. Same input → same output, always.
- Small, composable units. One responsibility each.
- Generator pipelines for large data: never load what you can stream.
- `functools` first: `partial`, `reduce`, `lru_cache`.
- No mutable default arguments. Ever.

## Security Champion (Python surface)

- No secrets in logs, no secrets in code. Env vars via `BaseSettings`.
- Secret variables wrapped in Pydantic's `SecretStr` or `Secret[T]`.
- Parameterised queries only. No f-strings into SQL or shell commands.
- On bad input: reject loudly with a clear `ValueError` or `ValidationError`, never silently coerce.

## Documentation

- Google-style docstrings on every non-trivial function.
- One-line imperative summary (`Validate and parse...`, `Transform...`).
- Args / Returns / Raises — one short line each, only what isn't obvious from the type.
- Never document what the type signature already says.

## Test stack

- `pytest` for all test running. No `unittest`.
- `hypothesis` for data edge cases: null values, empty collections, out-of-range values, schema surprises.
- `asyncio_mode = "auto"` in pytest config; use `async def test_` directly.
- No mocks of internal logic — test real behaviour with real (small) data.
