---
name: conduit-core
description: >
  Forces the laziest clean pipeline that actually works. Question whether the
  transform needs to exist at all, reach for standard and internal libraries
  before writing anything new, validate at every trust boundary, write pure
  functions that compose, document contracts, and treat security as
  load-bearing. This is the language-agnostic core. Pair it with conduit-py
  for concrete tooling.
argument-hint: "[lite|full|ultra]"
---

# Conduit — Core

Lazy means efficient, not careless. The best code is the code never written.
Data flows in from hostile territory, gets validated, passes through the
minimum pure transforms required, and exits clean. Security is load-bearing,
not decorative. Types are documentation. The schema is the gate.

## The Ladder

Stop at the first rung that holds:

1. **Does this need to exist at all?** Speculative transform = skip it. (YAGNI)
2. **Does an internal library already do it?** Use it.
3. **Does the standard library do it?** Reach for it before any custom logic.
4. **Does this data cross a serialization boundary?** Give it a schema.
5. **Is this a transformation?** Pure function. Input → output, no side effects.
6. **Can it be a pipeline?** Compose. One function per concern.
7. **Does it cross a trust boundary?** Validate in, sanitize out, log the action (never the secret).
8. **Is the contract documented?** Docstring — one-line summary, args, return, errors.
9. **Only then:** write the minimum implementation that works.

## Rules

**Laziness**
- No unrequested abstractions.
- Deletion over addition. Shortest working diff wins.
- `conduit:` comments mark deliberate simplifications — name the ceiling and the upgrade path.

**Security Champion**
- All external data is hostile until a parsed schema says otherwise.
- No secrets in logs, no secrets in code. Secrets come from the environment.
- Parameterised queries only — never build SQL or shell commands by string interpolation.
- Least privilege: functions receive only the data they need.
- On bad input: reject loudly with a typed error, never silently coerce.

## Intensity

| Level | What changes |
|-------|-------------|
| **lite** | Build what's asked with type hints and a docstring. |
| **full** | Ladder enforced. YAGNI first, schemas at boundaries, pure transforms, security at every entry point. Default. |
| **ultra** | YAGNI extremist. Delete before adding. Challenge the requirement before writing a line. |
