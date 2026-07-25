---
name: conduit-py
description: >
  Python tooling for the conduit discipline — Pydantic at every serialisation
  boundary, pure composable functions, Google-style docstrings, and a
  pytest + hypothesis test stack. Tailored for priveil: a FastAPI
  pseudonymisation service backed by GLiNER2 (NER detection), pydantic-ai
  (LLM advisor), and presidio-anonymizer (pseudonymisation operators).
  Read conduit-core for the ladder, philosophy, and security principles.
argument-hint: "[lite|full|ultra]"
---

> Read `conduit-core` before this file. This skill adds Python-specific tooling
> and priveil-specific conventions.

# Conduit — Python (priveil)

## Data & Types

- Pydantic models at every serialisation boundary: HTTP request/response,
  env vars (`BaseSettings`), LLM structured output, MCP tool returns.
- Domain models are **frozen** (`BaseModel, frozen=True`). Mutate by
  constructing a new instance, never by patching fields.
- `OperatorType`, `Sensitivity`, `mode` are `Literal` aliases — not enums,
  not plain strings. Use `cast(OperatorType, v)` with an explicit runtime
  guard when accepting from external input.
- Never reach into deserialized JSON with `.get()` chains when a model exists.
  Use `Model.model_validate(data)`.
- Type hints on every function signature, return type included.
- `# type: ignore[code]` requires a trailing comment: `# conduit: [reason]`.
  Never use bare `# type: ignore`.
- Never use `Any` without `# conduit: Any here because [reason]`.

## FastAPI Conventions

- Routes are **thin wrappers** — one `await` call, return the result.
  No business logic in route functions.
- Engine state (analyser, pseudonymiser, advisor, assessor) lives on
  `app.state`, initialised in the lifespan and injected via `deps.py`.
- Lifespan checks `hasattr(app.state, key)` before overwriting — allows test
  fixtures to pre-inject state.
- CPU-bound work (recogniser detection, presidio anonymise) is always offloaded
  to a `ThreadPoolExecutor` via `loop.run_in_executor`. Never block the event loop.
- Lifespan owns resource lifecycle (executors, model loading). Routes never
  construct engines.
- HTTP errors are raised via `HTTPException`; domain errors (bad input) are
  Pydantic `ValidationError` surfaced automatically by FastAPI.
- Every response model is a frozen Pydantic model. No raw dicts on the API surface.

## Entry Points

- `python -m priveil` starts the API server (defined in `src/priveil/__main__.py`).
- `python -m priveil.mcp` starts the MCP server (defined in `src/priveil/mcp/__main__.py`).
- `priveil` and `priveil-mcp` console scripts map to the same `main()` functions.
- Each `__main__.py` owns: settings loading, logging config, process startup.
  No startup logic in `app.py` or `server.py` beyond the lifespan context manager.

## Mode and Degradation

- `mode: Literal["fast", "advisor"]` is the canonical switch for LLM involvement.
  `"advisor"` silently no-ops to `"fast"` when no advisor model is configured —
  **never raise** on an unconfigured advisor in the detection or anonymisation
  path. Only `/assess` raises (503) because it has no fast fallback.
- New LLM-backed features follow the same pattern: degrade gracefully when the
  model is unset, document the no-op in the docstring.

## LLM / pydantic-ai

- **All LLM calls go through pydantic-ai.** Never use a raw `AsyncOpenAI` client
  for generation — use `Agent[None, OutputModel]` with a frozen Pydantic output type.
- The span-verdict advisor (`advisor/span_advisor.py`) uses `Agent[None, KeepDecision]`.
- The document assessor (`advisor/assessor.py`) uses `Agent[None, AssessmentDecision]`.
- Both share the same `build_advisor_model(settings)` factory which returns either
  a provider string (`"openai:gpt-4o"`) or an `OpenAIChatModel` for custom endpoints.
- Structured output is enforced by pydantic-ai — no manual `json.loads()` or JSON
  schema dicts in application code.
- The recommended local model stack:
  - **Ollama (dev):** `gemma4:e4b` at `PRIVEIL_ADVISOR_BASE_URL=http://localhost:11434/v1`
  - **vLLM (prod):** `google/gemma-4-E4B-it` at `PRIVEIL_ADVISOR_BASE_URL=http://vllm:8000/v1`

## Detection Stack

- **GLiNER2** (`gliner2[local]` optional extra) handles NER: PERSON, LOCATION, DATE_TIME.
  Recognisers extend `GLiNERRecogniser`; they share a single model instance loaded
  at startup.  When `gliner2` is not installed, NER recognisers are skipped (regex-only mode).
- **Regex recognisers** extend `RegexRecogniser`; no ML dependency.  Checksum
  validation is mandatory for AU_TFN, AU_ABN, AU_MEDICARE, AU_ACN.
- Each recogniser is the **single source of truth** for its entity type:
  `entity_type`, `is_pii`, `sensitivity`, `verification`, `default_operator`, and
  `default_operator_params` are all `ClassVar` declarations on the recogniser class.
- `verification: Literal["trust", "advisor"]` on the recogniser drives span routing.
  High-confidence scores (`score >= advisor_score_threshold`) bypass the advisor
  even on advisor-routed types — a conservative score gate, not a replacement.
- `ENTITY_CLASSIFICATION` no longer exists. Classification lives on recognisers.

## Pseudonymisation

- `presidio-anonymizer` handles operators (replace, mask, redact, hash).
- Default operator config is built from recognisers at startup via
  `build_operator_configs(recognisers)` and injected into `AsyncPseudonymiser`.
- `AnonymizerEngine()` constructor is untyped: annotate `# type: ignore[no-untyped-call]  # conduit: presidio untyped`.

## Async & Concurrency

- `async def` everywhere in routes, engine wrappers, and MCP tools.
- CPU-bound calls go through the shared `ThreadPoolExecutor` on `app.state`.
- Session-scoped pytest fixtures for expensive resources (GLiNER2 model load,
  executor). Yield fixtures with explicit `executor.shutdown(wait=True)` teardown.

## Security Champion (Python surface)

- No secrets in logs, no secrets in code. All config via `BaseSettings` with
  `PRIVEIL_` prefix.
- `advisor_api_key` and any bearer token **must** be `SecretStr`, never `str`.
  Access the raw value only at the point of use: `.get_secret_value()`.
- All external input is hostile until Pydantic has validated it. Trust boundary
  = the Pydantic model constructor. After that, trust the type.
- The `entity_map` from pseudonymisation contains original PII. Treat it as
  sensitive in documentation, error messages, and log guidance.
- On bad input: Pydantic raises `ValidationError` automatically. For domain
  errors (invalid operator, unconfigured advisor): raise `ValueError` with a
  clear message that names the env var to set.

## Documentation

- Google-style docstrings on every non-trivial function.
- One-line imperative summary (`Detect PII entities…`, `Build the assessor…`).
- Args / Returns / Raises — one short line each, only what the type doesn't say.
- For mode-dependent behaviour, document the degradation path explicitly.
- Never document what the type signature already says.

## Test Stack

- `pytest` for all test running. No `unittest`.
- `asyncio_mode = "auto"` in pytest config; use `async def test_` directly.
- Three test layers — keep them separate:
  - `tests/unit/` — pure function tests. No engines, no network. Fast.
  - `tests/integration/` — full HTTP request→response via `httpx.AsyncClient`.
    Uses `_PassThroughAdvisor` for LLM-backed paths.
  - `tests/mcp/` — MCP tool tests. Real engines, `SimpleNamespace` context
    stand-in. No MagicMock.
- No mocks of internal logic — test real behaviour with real (small) data.
  `_PassThroughAdvisor` is the one exception: use it for span-advisor paths to
  avoid real LLM calls in CI.
- `hypothesis` for data edge cases on pure functions: recogniser checksums,
  entity map construction, operator override merging. Annotate strategy choices.
- Session-scoped fixtures for GLiNER2 model and engine construction. Function-
  scoped for HTTP clients (each test gets a clean app state).
