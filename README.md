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
> **Service hardening is your responsibility:** this API ships with **no built-in authentication, no rate limiting, and no TLS termination**. Deploy it only behind your own trusted gateway/load balancer.

---

## How it works

Priveil is a three-layer pipeline. Each layer is independently optional.

```
Incoming text
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 1 — Regex recognisers (always active)             │
│  AU_TFN · AU_MEDICARE · AU_ABN · AU_ACN · AU_BSB        │
│  AU_PHONE · EMAIL_ADDRESS · PHONE_NUMBER · CREDIT_CARD  │
│  Checksum-validated where possible. Zero ML.            │
└─────────────────────────────────────────────────────────┘
      │
      ▼ (--extra gliner)
┌─────────────────────────────────────────────────────────┐
│ Layer 2 — GLiNER2 NER (optional)                        │
│  PERSON · LOCATION · DATE_TIME                          │
│  Encoder-based NER; finds name/place/date spans that    │
│  regex cannot. ~400 M params, runs on CPU.              │
└─────────────────────────────────────────────────────────┘
      │
      ▼ (--extra laya, mode="advisor")
┌─────────────────────────────────────────────────────────┐
│ Layer 3 — Laya span advisor (optional)                  │
│  Non-autoregressive System 1 model (~33 ms on GPU).     │
│  Verifies each uncertain span: "is this genuinely PII   │
│  in context?" Removes false positives before returning. │
│  No API key. No egress. Runs entirely locally.          │
└─────────────────────────────────────────────────────────┘
      │
      ▼
Detected entities  ──►  /pseudonymise  ──►  Redacted text
                   ──►  /assess        ──►  Risk profile
```

**Why two ML models?** GLiNER2 and laya do completely different jobs:

| | GLiNER2 | Laya |
|---|---|---|
| **Task** | Find entity spans in text (NER) | Verify whether a found span is genuine PII |
| **Input** | Raw text | `{entity_type, span, context}` |
| **Output** | Character offsets + label | Probability 0–1 |
| **Speed** | ~50–200 ms (CPU) | ~33 ms on GPU, ~100 ms on CPU |
| **Install** | `--extra gliner` | `--extra laya` |
| **API key** | No | No |

Neither replaces the other. GLiNER2 finds candidates; laya filters false positives.

---

## Quickstart

```bash
# Regex-only: AU financial identifiers + email/phone/card
uv sync
uv run python -m priveil

# Full stack: add person/place/date detection + false-positive filtering
uv sync --extra gliner --extra laya
uv run python -m priveil
```

API at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/detect` | Detect PII entities in text |
| `POST` | `/pseudonymise` | Replace PII with placeholders |
| `POST` | `/assess` | Risk profile (requires `--extra laya`) |

### `POST /detect`

```bash
curl -X POST http://localhost:8000/detect \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Contact Jane Smith at jane@example.com and call 0412 345 678.",
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
      { "text": "Jane Smith",       "entity_type": "PERSON",        "is_pii": true,  "sensitivity": "high",   "score": 0.85 },
      { "text": "jane@example.com", "entity_type": "EMAIL_ADDRESS", "is_pii": true,  "sensitivity": "medium", "score": 1.0  },
      { "text": "0412 345 678",     "entity_type": "AU_PHONE",      "is_pii": true,  "sensitivity": "medium", "score": 0.95 }
    ],
    "advisor_applied": true
  }
}
```

> **Note:** `PERSON` only appears when `--extra gliner` is installed. Without it, only regex-detected types (email, phone, AU identifiers) are returned.

**`mode` field:**

| Value | Behaviour |
|-------|-----------|
| `"advisor"` (default) | Laya verifies each uncertain span to remove false positives. Falls back to `"fast"` if laya is not installed. |
| `"fast"` | Raw detector output — no ML verification pass. |

### `POST /pseudonymise`

```bash
curl -X POST http://localhost:8000/pseudonymise \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Jane Smith TFN 123 456 782, BSB 062-000, jane@bank.com.au",
    "mode": "advisor"
  }'
```

```json
{
  "data": {
    "anonymised_text": "<PERSON> TFN ***-***-***, BSB XXX-XXX, <EMAIL>",
    "entity_map": {
      "Jane Smith":       "<PERSON>",
      "123 456 782":      "***-***-***",
      "062-000":          "XXX-XXX",
      "jane@bank.com.au": "<EMAIL>"
    },
    "advisor_applied": true
  }
}
```

**Default operators:**

| Entity type | Output example |
|-------------|---------------|
| `PERSON` | `<PERSON>` |
| `EMAIL_ADDRESS` | `<EMAIL>` |
| `AU_PHONE` / `PHONE_NUMBER` | `<PHONE>` |
| `AU_TFN` | `***-***-***` |
| `AU_BSB` | `XXX-XXX` |
| `AU_ABN` | `*** *** ***` |
| `CREDIT_CARD` | `**** **** **** 1234` (last 4 kept) |
| `LOCATION` | `<LOCATION>` |
| `DATE_TIME` | `<DATE>` |

Override per request:

```json
{
  "text": "Call Jane on 0412 345 678",
  "operator_overrides": { "PERSON": "redact", "AU_PHONE": "hash" }
}
```

Available operators: `replace`, `mask`, `redact`, `hash`.

### `POST /assess`

Laya-powered sensitivity assessment. Requires `uv sync --extra laya`.

```bash
curl -X POST http://localhost:8000/assess \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Applicant Jane Smith TFN 123 456 782. BSB 062-000.",
    "context": "Australian home loan application"
  }'
```

Returns: `overall_sensitivity` (low/medium/high/critical), `categories`, `regulatory_flags`, `recommended_handling`, `entity_breakdown`, `risk_summary`, `reasoning`.

---

## GLiNER2 — person, location and date detection

[GLiNER2](https://github.com/fastino/gliner2) is a compact encoder-based NER model that finds `PERSON`, `LOCATION`, and `DATE_TIME` spans in text. It uses a sliding-window approach over raw text and returns character offsets.

**Install:**

```bash
uv sync --extra gliner
```

Without this extra, the service runs in **regex-only mode** — AU financial identifiers, email, phone, and credit card are still detected; person names, locations, and dates are not.

**Configuration:**

| Variable | Default | Description |
|----------|---------|-------------|
| `PRIVEIL_GLINER2_MODEL` | `fastino/gliner2-base-v1` | HuggingFace model ID. Downloaded on first run and cached. |

The model loads at startup from the HuggingFace hub (or local cache). If the load fails, the service continues in regex-only mode rather than refusing to start.

---

## Laya — span verification and assessment

[Laya](https://pypi.org/project/laya/) is a non-autoregressive System 1 decision engine. Rather than generating text, it answers typed questions (`noul` = yes/no probability, `choice`, `score`) in a single encoder forward pass.

Priveil uses laya for two things:

**1. Span verification (`mode="advisor"`)**: after detection, each uncertain span is sent to laya with a `noul` question:

```
entity_type: PERSON
span: "Jane Smith"
context: "Contact Jane Smith at the branch office."
→ is_genuine_pii probability: 0.87  ✓ keep
```

```
entity_type: AU_BSB
span: "062-000"
context: "Routing codes 062-000 and 013-005 direct traffic between nodes."
→ is_genuine_pii probability: 0.21  ✗ drop (false positive)
```

High-confidence spans (score ≥ `PRIVEIL_ADVISOR_SCORE_THRESHOLD`) and trust-tier recognisers (AU_TFN, AU_MEDICARE, etc.) bypass laya entirely.

**2. Risk assessment (`POST /assess`)**: laya answers typed questions about the full document:
- `choice`: overall sensitivity tier (low / medium / high / critical)
- `noul`: is this financial PII? identity PII? medical? employment?

Rule tables derive the advisory fields (`regulatory_flags`, `recommended_handling`) from laya's typed answers plus the detected entity types.

**Why laya instead of an LLM?**

| | LLM (removed) | Laya |
|---|---|---|
| Latency | 150–500 ms (network) | ~33 ms on GPU, ~100 ms on CPU |
| API key | Required | Not required |
| Data egress | Cloud provider | None — runs locally |
| Cost | Per-token | Zero |
| Determinism | Low (sampling) | High (calibrated) |

**Install:**

```bash
uv sync --extra laya
```

**Configuration:**

| Variable | Default | Description |
|----------|---------|-------------|
| `PRIVEIL_ADVISOR_BACKEND` | `auto` | `auto` = use laya if installed; `laya` = require laya |
| `PRIVEIL_ASSESS_BACKEND` | `auto` | `auto` = use laya if installed, else 503 |
| `PRIVEIL_LAYA_PII_THRESHOLD` | `0.5` | Probability threshold for keeping a span |
| `PRIVEIL_LAYA_PRELOAD` | `false` | Load all laya checkpoints at startup (recommended in production) |
| `PRIVEIL_ADVISOR_SCORE_THRESHOLD` | `0.9` | Spans scoring ≥ this bypass laya verification |
| `PRIVEIL_ADVISOR_CONTEXT_CHARS` | `60` | Characters of context window sent to laya per span |

**Performance (concurrent spans):**

| Spans | laya (GPU) | laya (CPU) |
|-------|-----------|-----------|
| 1 | ~33 ms | ~100 ms |
| 3 | ~33 ms | ~100 ms (concurrent) |
| 5 | ~66 ms | ~200 ms |

Multiple spans verify concurrently in the thread pool. All-trust inputs (AU_TFN, AU_MEDICARE etc.) bypass laya entirely — zero overhead.

**Production setup:**

```bash
PRIVEIL_LAYA_PRELOAD=true  # warm checkpoints at startup, not on first request
```

---

## Australian entity types

Purpose-built recognisers with checksum validation where the issuing authority publishes an algorithm.

| Entity type | Description | PII | Sensitivity | Validation |
|-------------|-------------|-----|-------------|-----------|
| `AU_TFN` | Tax File Number | ✅ | critical | ATO mod-11 checksum |
| `AU_MEDICARE` | Medicare card number | ✅ | critical | Services Australia checksum |
| `AU_ABN` | Australian Business Number | ❌ | low | ATO mod-89 checksum |
| `AU_ACN` | Australian Company Number | ❌ | low | ASIC complement-of-10 checksum |
| `AU_BSB` | Bank State Branch code | ✅ | high | Format `XXX-XXX` |
| `AU_PHONE` | Australian mobile/landline | ✅ | medium | `04XX`, `+61 4XX`, `(0X) XXXX XXXX` |

Generic types (always active): `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`.

NER types (requires `--extra gliner`): `PERSON`, `LOCATION`, `DATE_TIME`.

> **TFN scope:** 9-digit TFNs only. Legacy 8-digit TFNs are excluded by design.

---

## Configuration reference

All variables prefixed `PRIVEIL_`. Copy `.env.example` to `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `PRIVEIL_GLINER2_MODEL` | `fastino/gliner2-base-v1` | GLiNER2 NER model. Requires `--extra gliner`. |
| `PRIVEIL_ADVISOR_BACKEND` | `auto` | Span advisor backend: `auto` (laya if installed) or `laya` |
| `PRIVEIL_ASSESS_BACKEND` | `auto` | Assess backend: `auto` (laya if installed, else 503) or `laya` |
| `PRIVEIL_ADVISOR_SCORE_THRESHOLD` | `0.9` | Spans at or above this score bypass laya verification |
| `PRIVEIL_ADVISOR_CONTEXT_CHARS` | `60` | Context window (chars) around each span sent to laya |
| `PRIVEIL_LAYA_PII_THRESHOLD` | `0.5` | Laya `noul` probability to keep a span as genuine PII |
| `PRIVEIL_LAYA_PRELOAD` | `false` | Preload laya checkpoints at startup |
| `PRIVEIL_AUDIT_HASH_KEY` | _(unset)_ | HMAC key for `input_hash`. Set for stable hashes across restarts. |
| `PRIVEIL_EXECUTOR_MAX_WORKERS` | `4` | Thread-pool workers for CPU-bound recogniser + laya work |
| `PRIVEIL_DEBUG` | `false` | FastAPI debug mode |

---

## MCP server

Priveil exposes `detect`, `anonymise`, and `assess` over the [Model Context Protocol](https://modelcontextprotocol.io).

```bash
pip install "priveil[mcp]"
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "priveil": {
      "command": "priveil-mcp",
      "env": {
        "PRIVEIL_LAYA_PRELOAD": "true"
      }
    }
  }
}
```

The MCP server loads the same detection stack as the HTTP API — GLiNER2 if installed, laya if installed. No API key needed when using laya.

---

## Development

```bash
uv sync --extra gliner --extra laya   # full stack
uv run pytest tests/ -v
uv run ruff check src/ tests/
uv run mypy src/
```

**Docker:**

```bash
# Full-stack local image (gliner + laya + mcp)
docker build --target local -t priveil-local .
docker run --rm -p 8000:8000 priveil-local

# CI test matrix
docker build --target test -t priveil-test .
docker run --rm priveil-test
```

CI runs across Python 3.11, 3.12, and 3.13.

---

## Project structure

```
src/priveil/
├── advisor/
│   ├── laya_advisor.py    # LayaSpanAdvisor — noul questions per span
│   │                      # Also exports: AdvisorResult, AdvisorProtocol
│   └── laya_assessor.py   # LayaAssessor — choice/noul for /assess
│                          # Also exports: entity_breakdown()
├── api/
│   ├── deps.py            # FastAPI dependency injection
│   └── routes/            # detect, pseudonymise, assess, health
├── domain/                # Pydantic models (entities, detection, assessment, …)
├── engine/                # AsyncAnalyser, AsyncPseudonymiser
├── mcp/                   # MCP server (pip install "priveil[mcp]")
│   ├── server.py          # _State dataclass, lifespan, FastMCP instance
│   └── tools.py           # detect / anonymise / assess tools
├── recognisers/
│   ├── au_tfn.py          # AU_TFN — mod-11 checksum
│   ├── au_medicare.py     # AU_MEDICARE — Services Australia checksum
│   ├── au_abn.py          # AU_ABN — mod-89 checksum
│   ├── au_acn.py          # AU_ACN — complement-of-10 checksum
│   ├── au_bsb.py          # AU_BSB — format validation
│   ├── au_phone.py        # AU_PHONE — pattern matching
│   ├── email.py           # EMAIL_ADDRESS
│   ├── phone.py           # PHONE_NUMBER
│   ├── credit_card.py     # CREDIT_CARD — Luhn checksum
│   ├── person.py          # PERSON — GLiNER2 (optional)
│   ├── location.py        # LOCATION — GLiNER2 (optional)
│   ├── date_time.py       # DATE_TIME — GLiNER2 (optional)
│   ├── base.py            # Span, BaseRecogniser, RegexRecogniser, GLiNERRecogniser
│   └── registry.py        # build_recognisers(gliner_model=None)
├── settings.py            # All config vars, prefixed PRIVEIL_
├── app.py                 # FastAPI factory + lifespan
└── __main__.py            # python -m priveil → HTTP API

tests/
├── unit/                  # Pure function tests — no network
├── integration/           # Full request→response via httpx AsyncClient
└── mcp/                   # MCP tool tests (skipped when mcp extra not installed)
```

---

## On anonymisation and its limits

> [!WARNING]
> The word "anonymise" appears throughout this codebase because it is the term practitioners use. It is not accurate.
>
> What Priveil produces is **pseudonymisation**: detected entity spans are replaced with labelled placeholders. The `entity_map` returned by `/pseudonymise` is sensitive data — protect it with the same controls as the original text.
>
> No pattern-matching tool can produce truly anonymous data:
>
> 1. **Data is more identifying than it appears.** A name, postcode, and date of birth together uniquely identify most people. There is no way to enumerate what an attacker might use.
> 2. **Auxiliary data is an unknown variable.** Information that looks private today may be public for specific individuals, or become identifying after an unrelated breach.
> 3. **Attacks improve.** Re-identification techniques continue to advance.

> [!TIP]
> **What Priveil is useful for:** keeping PII out of logs and analytics pipelines, reducing accidental exposure when data crosses trust boundaries, improving compliance posture. These are real and valuable goals — just not anonymisation.
>
> For further reading: Damien Desfontaines' [*What anonymization techniques can you trust?*](https://desfontain.es/blog/trustworthy-anonymization.html) and Katharine Jarmul's [*Probably Private*](https://probablyprivate.com/).

---

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Docker (optional, for CI matrix builds)
