---
name: vertical-slices
description: >
  Guidance for breaking features into tracer bullet vertical slices. Use when
  designing new features, epics, or initiative plans for this service. Each
  slice cuts through ALL integration layers end-to-end.
---

# Vertical Slices

A vertical slice is a thin end-to-end cut through every layer of the system —
schema, engine, API, tests. It is NOT a horizontal layer (e.g. "add all domain
models first").

## Rules

- **A completed slice is demo-able or verifiable on its own** — no sibling slice needed.
- **Each slice delivers a narrow but COMPLETE path** — no half-implemented schemas, no skipped tests.
- **Prefactoring ships first** as Slice 0: scaffold, shared models, engine wiring.
- **A new slice NEVER modifies a prior slice's public contract** — extend, don't break.
- **LLM / AI paths are always additive** — core deterministic paths never depend on them.

## Shape of a good slice

| Layer  | Must include                                    |
|--------|-------------------------------------------------|
| Schema | Pydantic request + response models              |
| Engine | Business logic / service layer                  |
| API    | FastAPI route wired end-to-end                  |
| Tests  | ≥1 unit test + ≥1 integration test via ASGI client |

## Anti-patterns

- "Add all the domain models" — horizontal slice, not vertical.
- "Wire up the engine layer" — same problem.
- A slice that cannot be verified without a later slice being complete.
- An API route without a test.

## Process

1. Identify the narrowest path that delivers value.
2. Name it as an imperative user capability: "Detect entities in text".
3. List the layers it touches (schema → engine → API → test).
4. Write the acceptance criteria as observable outputs, not internal state.
5. Implement each layer in order; run the test before calling the slice done.

## Build order for this service

```
Slice 0: Scaffold (prerequisite for everything)
  ↓
Slice 1: Text entity detection  →  POST /detect
  ↓
Slice 2: AU financial recognisers  (extends Slice 1 entities)
  ↓
Slice 3: Anonymisation  →  POST /anonymise
  ↓
Slice 5: LLM judge (non-streaming)  →  POST /judge
  ↓
Slice 6: Streaming judge  →  POST /judge/stream

(Slice 4 — image detection — deferred; see backlog)
```

Each arrow = hard dependency. Slices at the same level run in parallel.
