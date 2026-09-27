```
▀█▓▒░██▀█▓▒░▄▄  ▀█▓▒░██▀█▓▒░▄▄   ▀█▓▒░██▀ ██▓▒░    ▓▒░██ ▀█▓▒░██▀▀▀▀▓▒░█ ▀█▓▒░██▀ ▀█▓▒░██▀       
 ▓▒░███  ▀▓▒░██  ▓▒░███  ▀▓▒░██   ▓▒░███  █▓▒░█    ▓▒░██  ▓▒░███    ▒░░█  ▓▒░███   ▓▒░███        
 ▒░████   ▒░███  ▒░████   ▒░███   ▒░████  ▓▒░██    ▒░███  ▒░████     ▀▀▀  ▒░████   ▒░████        
 ░█████▄▄░███▀   ░█████▄▄░███▀    ░█████  ▒░███    ░████  ░█████▄▄▄█▄     ░█████   ░█████        
 ░█████          ░█████   ░███▄   ░█████  ███░█    ░████  ░█████   ▀      ░█████   ░█████        
 ░█████          ░█████   ░████   ░█████  ▐█░▒█    ▒░██▌  ░█████    ▓▒░█  ░█████   ░█████    ▓▒░█
 ░█████          ░█████   ░████   ░█████   ▀███▄ ▄░███▀   ░█████    ▒░██  ░█████   ░█████    ▒░██
▀▀▀▀▀▀▀▀        ▀▀▀▀▀▀▀▀ ▀▀▀▀▀▀▀ ▀▀▀▀▀▀▀▀    ▀▀▀▀▀▀▀▀    ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ ▀▀▀▀▀▀▀▀ ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
```

A pseudonymisation service for reducing obvious PII exposure in text workflows, with strong support for Australian financial identifiers — **not a substitute for true anonymisation**.

> [!IMPORTANT]
> **Read this before integrating:** Priveil replaces known PII patterns with consistent placeholders. It cannot enumerate all possible identifying information, does not account for auxiliary data an attacker might possess, and makes no mathematical guarantee about re-identification risk. See [**On anonymisation and its limits**](#on-anonymisation-and-its-limits) below.

> [!CAUTION]
> **Service hardening is your responsibility:** this API ships with **no built-in authentication, no rate limiting, and no TLS termination**. Deploy it only behind your own trusted gateway/load balancer (authn/authz, traffic limits, TLS, and network controls).

---

> [!WARNING]
> ## On anonymisation and its limits
>
> The word "anonymise" appears throughout this codebase and documentation because it is the term practitioners use. It is not accurate, and that matters.
>
> What Priveil produces is **pseudonymisation**: detected entity spans are replaced with labelled placeholders (`<PERSON>`, `***-***-***`). The `entity_map` returned by `/pseudonymise` records the original PII spans as keys — it is sensitive data that must be protected with the same controls as the original text.
>
> Beyond that, no tool that works by finding and replacing known patterns can produce truly anonymous data, for three reasons:
>
> 1. **Data is more identifying than it appears.** A name, a postcode, and a date of birth together uniquely identify most people. There is no way to enumerate what an attacker might use.
> 2. **Auxiliary data is an unknown variable.** Information that looks private may be public for specific individuals. Data that is safe today may become identifying after an unrelated breach.
> 3. **Attacks improve over time.** AI-assisted reconstruction attacks, linkage attacks, and re-identification techniques continue to improve.

> [!TIP]
> The only approach with a mathematical guarantee is differential privacy — applied to aggregations, not to text. **What Priveil is useful for:** keeping PII out of logs and analytics pipelines, reducing accidental exposure when data crosses trust boundaries, and making data *less obviously identifying* for operational purposes.

---

## Detection Stack

Two layers, both always active:

- **Regex recognisers** — checksum-validated for AU identifiers, pattern-based for email, phone, and credit card. Zero ML dependencies.
- **Laya span advisor** (`laya` optional extra) — non-autoregressive System 1 verification of uncertain spans in `mode="advisor"`. Runs locally in ~33 ms on GPU, no API key, no egress. Also powers `/assess`.

```bash
# Regex-only (default)
uv sync

# With laya span verification + assessment
uv sync --extra laya
```

When laya is installed, `mode="advisor"` and `/assess` activate automatically with no further configuration.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/detect` | Detect PII entities in text |
| `POST` | `/pseudonymise` | Pseudonymise PII in text |
| `POST` | `/assess` | Assess content risk and sensitivity (requires laya) |

### `POST /detect`

Returns detected entities with type, character offsets, confidence score, PII classification, and sensitivity tier. Every response includes an HMAC-SHA-256 audit hash of the input.

```bash
curl -X POST http://localhost:8000/detect \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Jane Smith TFN 123 456 782, BSB 062-000, jane@bank.com.au",
    "mode": "advisor"
  }'
```

```json
{
  "meta": {
    "request": { "mode": "advisor" },
    "response": { "mode": "advisor", "input_hash": "hmac-sha256:..." }
  },
  "data": {
    "entities": [
      { "text": "123 456 782",      "entity_type": "AU_TFN",        "is_pii": true, "sensitivity": "critical", "score": 1.0  },
      { "text": "062-000",           "entity_type": "AU_BSB",        "is_pii": true, "sensitivity": "high",     "score": 0.85 },
      { "text": "jane@bank.com.au",  "entity_type": "EMAIL_ADDRESS", "is_pii": true, "sensitivity": "medium",   "score": 1.0  }
    ],
    "advisor_applied": true
  }
}
```

**`mode` field** (default `"advisor"`):

| Value | Behaviour |
|-------|-----------|
| `"advisor"` | Laya verifies uncertain spans to remove false positives (~33 ms on GPU). Falls back to `"fast"` if laya is not installed. |
| `"fast"` | Raw detector output. No ML verification. |

### `POST /pseudonymise`

Replaces detected entities with configurable operator strategies.

```bash
curl -X POST http://localhost:8000/pseudonymise \
  -H "Content-Type: application/json" \
  -d '{"text": "Jane Smith TFN 123 456 782", "mode": "advisor"}'
```

```json
{
  "meta": { "request": { "mode": "advisor" }, "response": { "mode": "advisor", "input_hash": "hmac-sha256:..." } },
  "data": {
    "anonymised_text": "<PERSON> TFN ***-***-***",
    "entity_map": { "Jane Smith": "<PERSON>", "123 456 782": "***-***-***" },
    "advisor_applied": true
  }
}
```

**Default operators by entity type:**

| Entity type | Default operator | Output example |
|-------------|-----------------|----------------|
| `PERSON` | replace | `<PERSON>` |
| `EMAIL_ADDRESS` | replace | `<EMAIL>` |
| `PHONE_NUMBER` / `AU_PHONE` | replace | `<PHONE>` |
| `AU_TFN` | replace | `***-***-***` |
| `AU_BSB` | replace | `XXX-XXX` |
| `AU_ABN` | replace | `*** *** ***` |
| `CREDIT_CARD` | mask (last 4 digits) | `**** **** **** 1234` |

Override per request with `operator_overrides`:

```json
{ "text": "Contact Jane Smith on 0412 345 678", "operator_overrides": { "PERSON": "redact", "AU_PHONE": "mask" } }
```

Available operators: `replace`, `mask`, `redact`, `hash`.

### `POST /assess`

Laya-powered sensitivity assessment. Requires `uv sync --extra laya`.

```bash
curl -X POST http://localhost:8000/assess \
  -H "Content-Type: application/json" \
  -d '{"text": "Applicant Jane Smith TFN 123 456 782. BSB 062-000.", "context": "Australian home loan application"}'
```

Returns: `overall_sensitivity`, `risk_summary`, `categories`, `regulatory_flags`, `recommended_handling`, `entity_breakdown`, `reasoning`.

---

## Australian Entity Types

| Entity type | Description | PII | Sensitivity | Validation |
|-------------|-------------|-----|-------------|-----------|
| `AU_TFN` | Tax File Number | ✅ | critical | ATO checksum (mod 11) |
| `AU_MEDICARE` | Medicare card number | ✅ | critical | Services Australia issuing checksum |
| `AU_ABN` | Australian Business Number | ❌ | low | ATO mod-89 checksum |
| `AU_ACN` | Australian Company Number | ❌ | low | ASIC complement-of-10 checksum |
| `AU_BSB` | Bank State Branch code | ✅ | high | Format: `XXX-XXX` |
| `AU_PHONE` | Australian mobile/landline | ✅ | medium | 04XX, +61 4XX, (0X) XXXX XXXX |

Generic types: `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`.

> **TFN scope:** 9-digit TFNs only. Legacy 8-digit TFNs are excluded.

---

## Configuration

Copy `.env.example` to `.env` and set values.

| Variable | Default | Description |
|----------|---------|-------------|
| `PRIVEIL_ADVISOR_BACKEND` | `auto` | Span verification backend: `auto` (laya if installed, else fast), `laya` (requires extra), `pydantic_ai` (removed — use `laya`) |
| `PRIVEIL_ASSESS_BACKEND` | `auto` | Assess backend: `auto` (laya if installed, else 503), `laya` (requires extra) |
| `PRIVEIL_ADVISOR_SCORE_THRESHOLD` | `0.9` | Spans scoring ≥ this bypass laya verification |
| `PRIVEIL_ADVISOR_CONTEXT_CHARS` | `60` | Characters of context window sent to laya per span |
| `PRIVEIL_LAYA_PII_THRESHOLD` | `0.5` | Laya noul probability threshold for keeping a span |
| `PRIVEIL_LAYA_PRELOAD` | `false` | Preload laya checkpoints at startup (recommended in production) |
| `PRIVEIL_AUDIT_HASH_KEY` | _(unset)_ | Secret key for `input_hash` HMAC. Set for stable hashes across restarts. |
| `PRIVEIL_EXECUTOR_MAX_WORKERS` | `4` | Thread-pool size for recogniser, pseudonymiser, and laya work |
| `PRIVEIL_DEBUG` | `false` | Enable FastAPI debug mode |

---

## Laya span advisor

[Laya](https://pypi.org/project/laya/) is a non-autoregressive System 1 encoder. Priveil uses its `noul` question type to verify whether a detected span is genuine PII in context.

**Why:** regex detectors produce false positives (e.g. BSB-formatted routing codes in a non-banking context). Laya filters them in ~33 ms on GPU without API calls, egress, or tokens.

**Perf comparison:**

| Backend | 1 span | 3 spans | 5 spans | API key |
|---------|--------|---------|---------|---------|
| LLM (150 ms/call, removed) | ~150 ms | ~150 ms | ~150 ms | Yes |
| laya (33 ms/span, concurrent) | ~33 ms | ~33 ms | ~66 ms | No |

**Production setup:**

```bash
PRIVEIL_LAYA_PRELOAD=true   # load checkpoints at startup
```

---

## Quickstart

```bash
uv sync --extra laya   # includes span verification + assessment
uv run python -m priveil
```

API at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

---

## MCP Server

Priveil exposes `detect`, `anonymise`, and `assess` over the [Model Context Protocol](https://modelcontextprotocol.io).

```bash
pip install "priveil[mcp]"
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "priveil": {
      "command": "priveil-mcp"
    }
  }
}
```

With laya installed, all three tools work with no API key. Add `PRIVEIL_LAYA_PRELOAD=true` for production.

---

## Development

```bash
uv run pytest tests/ -v
uv run ruff check src/ tests/
uv run mypy src/
```

CI runs the full test matrix across Python 3.11, 3.12, and 3.13.

---

## Project structure

```
src/priveil/
├── advisor/
│   ├── laya_advisor.py   # LayaSpanAdvisor — span verification (AdvisorResult, AdvisorProtocol)
│   └── laya_assessor.py  # LayaAssessor — fast /assess without LLM
├── api/
│   ├── deps.py           # FastAPI dependency injection
│   └── routes/           # detect, pseudonymise, assess, health
├── domain/               # Pydantic models
├── engine/               # AsyncAnalyser, AsyncPseudonymiser
├── mcp/                  # Optional MCP server (pip install "priveil[mcp]")
├── recognisers/          # AU_TFN, AU_MEDICARE, AU_ABN, AU_ACN, AU_BSB, AU_PHONE,
│                         # EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD (all regex + checksum)
├── settings.py
├── __main__.py
└── app.py

tests/
├── unit/
├── integration/
└── mcp/
```

---

## On anonymisation and its limits

For further reading: Damien Desfontaines' [*What anonymization techniques can you trust?*](https://desfontain.es/blog/trustworthy-anonymization.html) and Katharine Jarmul's [*Probably Private*](https://probablyprivate.com/).
