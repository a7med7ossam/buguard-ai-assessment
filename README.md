# Buguard Asset Management — AI Applications Track

A self-contained slice of the **DarkAtlas** Attack Surface Management platform: a
minimal FastAPI service that ingests discovered assets into PostgreSQL, plus a
**LangChain-powered analysis layer** providing enrichment, risk scoring,
natural-language querying, and report generation over that data.

> **Track:** AI Applications (Section 5). The API surface is intentionally
> small — bulk import, a relationships view, and one endpoint per analysis
> capability — with the LangChain layer doing the heavy lifting.

---

## 1. Setup and run

### Prerequisites
- Docker + Docker Compose
- An LLM API key (Gemini, via its OpenAI-compatible endpoint — see *Design decisions*)

### Run everything with one command

```bash
# 1. Create your env file from the template and fill in values
cp .env.example .env
#    -> set POSTGRES_* and GEMINI_API_KEY

# 2. Build and start the app + PostgreSQL
docker compose up --build
```

The API is then available at **http://localhost:8000**. The app waits for
PostgreSQL to pass its healthcheck before starting, and creates its tables
automatically on boot.

Seed the database with the provided sample dataset:

```bash
curl -X POST http://localhost:8000/api/import \
  -H "Content-Type: application/json" \
  --data @data/sample_assets.json
```

### Running locally without Docker (optional)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Start only PostgreSQL via compose, or point DATABASE_URL at your own instance:
docker compose up -d db
uvicorn app.main:app --reload
```

When running on the host, `DATABASE_URL` should use `localhost` (as in
`.env.example`). Under Docker, the app service overrides it to use the `db`
host automatically.

---

## 2. Environment variables

| Variable | Purpose | Example |
|---|---|---|
| `POSTGRES_USER` | Database user (used by both the `db` container and the connection string) | `buguard` |
| `POSTGRES_PASSWORD` | Database password | `change_me` |
| `POSTGRES_DB` | Database name | `darkatlas_assets` |
| `DATABASE_URL` | SQLAlchemy connection string. Host = `localhost` on the host machine; the compose app service overrides it to host `db`. | `postgresql://buguard:change_me@localhost:5432/darkatlas_assets` |
| `GEMINI_API_KEY` | LLM provider key, read from the environment and never committed | `your_api_key_here` |

Secrets stay out of the repo: `.env` is git-ignored and docker-ignored, and only
`.env.example` (with placeholders) is committed.

---

## 3. API documentation

FastAPI generates interactive docs automatically once the app is running:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI JSON:** http://localhost:8000/openapi.json

### Endpoint summary

| Method | Path | Description |
|---|---|---|
| `GET`  | `/health` | Liveness probe used by the compose healthcheck |
| `POST` | `/api/import` | Bulk import assets (idempotent; dedup + tag/metadata merge + relationship building) |
| `GET`  | `/api/assets/{asset_id}/relationships` | An asset together with its incoming and outgoing relationship edges |
| `POST` | `/api/analyze/enrich` | **AI** — classify environment / category / criticality and write enrichment back to the asset's metadata |
| `POST` | `/api/analyze/risk` | **AI** — risk score (1–10), risk level, and a concise summary |
| `GET`  | `/api/analyze/report` | **AI** — Markdown inventory/risk report over the whole dataset |
| `POST` | `/api/analyze/query` | **AI** — natural-language → SQL query over the assets |

---

## 4. Design decisions

**Layered structure.** HTTP concerns (`app/routers`), business logic
(`app/services`), and the AI layer (`app/ai`) are separated. Routers stay thin;
deduplication, merging, and relationship building live in services; each
LangChain capability is its own module. The LLM client and pure helpers are
isolated so the analysis modules are easy to reason about and test.

**Deduplication keyed on `(type, value)`.** An asset's identity is its kind and
canonical value, not its source-assigned `id`. Re-importing the same
`(type, value)` updates `last_seen`, flips `status` back to `active` (a stale
asset that re-appears returns to active), and **merges** tags and metadata
rather than overwriting. A unique constraint on `(type, value)` backs this at
the database level.

**Conflict / merge strategy.** Metadata merges recursively: nested objects are
combined, and on a leaf conflict the newest value wins (last-write-wins). Tags
are unioned. This means a second source enriches a record instead of clobbering
it.

**Per-record fault isolation on import.** Each record is processed inside a
SAVEPOINT (`begin_nested`). A malformed or conflicting record rolls back on its
own and is reported in `failed_records`; the rest of the batch still commits. So
a single bad row never poisons the whole import.

**Grounding the LLM (anti-hallucination).** Several guardrails keep answers tied
to real data:
- Lifecycle facts (expired / expiring-soon / days remaining) are computed in
  Python and handed to the model, which is instructed to trust them rather than
  do its own date math.
- Prompts state *use only the supplied data; never invent assets / metadata /
  vulnerabilities; return "unknown" when information is missing.*
- Structured outputs are enforced with Pydantic output parsers, so responses
  conform to a fixed schema.
- The NL→SQL path is read-only and layered: a pre-flight check rejects write
  verbs and ambiguous adjectives before any LLM call, the generated SQL must
  start with `SELECT`, and the prompt is schema-aware so the model can't
  reference columns that don't exist.

**LLM provider.** Gemini is used through its OpenAI-compatible endpoint, which
lets us keep the well-supported `langchain-openai` wrapper. The provider is a
single edit in `app/ai/llm.py`; the key is read from the environment.

**Schema management.** Tables are created with `create_all` on startup to keep
setup to a single command. For production this would move to Alembic migrations.

---

## 5. Assumptions

- **AI track scope.** Per Section 5, the API is deliberately minimal. Full CRUD,
  the filtered/sorted/paginated list endpoint, and write-operation auth belong
  to Track A and are intentionally out of scope here; they are noted under
  *What I'd do next*.
- **Asset identity** is `(type, value)`; the incoming `id` is a stable handle
  but two different records may not reuse the same `id` for a new asset.
- **Dates** in metadata (`expires`) use `YYYY-MM-DD`. Unparseable dates are
  flagged (`date_parse_error`) rather than crashing.
- **Single tenant.** Multi-tenant isolation is a documented stretch goal, not
  implemented.
- The sample dataset is trusted input representing one DarkAtlas scan export.

---

## 6. Running the tests

The unit tests cover the deterministic core logic and run **without** a database
or an API key.

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Or inside the running container:

```bash
docker compose exec app pytest
```

Covered:
- **Metadata merge** — recursive merge, leaf conflict resolution, no mutation of
  the original (the *conflicting-data* edge case).
- **Lifecycle computation** — expired vs. expiring-soon vs. far-future, and the
  malformed-date path (the *certificate/lifecycle dates* edge case).
- **NL-query guardrails** — forbidden write verbs and ambiguous terms are
  rejected; well-formed read queries pass (the *ambiguous/out-of-scope query*
  edge case).

---

## 7. Example prompts and outputs (AI track)

> Outputs below are representative responses over `data/sample_assets.json`.
> Exact LLM wording varies; the structure and grounding do not. In that
> dataset, `cert-1` (`CN=api.example.com`, issued by Let's Encrypt) expires
> `2025-01-02` — already expired relative to today.

### 7.1 Automated enrichment & categorization

**Request**
```bash
curl -X 'POST' \
  'http://localhost:8000/api/analyze/enrich' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "asset_id": "subdomain-1"
}'
```

**Response**
```json
{
  "asset_id": "subdomain-1",
  "enrichment": {
    "environment": "prod",
    "category": "web_server",
    "criticality": "high"
  }
}
```
The `prod` classification is grounded in the asset's `prod` tag and the `api.`
hostname convention; the enrichment fields are also written back into the
asset's metadata (with a `last_ai_enrichment` timestamp).

### 7.2 Risk scoring & summarization

**Request**
```bash
curl -X 'POST' \
  'http://localhost:8000/api/analyze/risk' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "asset_id": "cert-1"
}'
```

**Response**
```json
{
  "asset_id": "cert-1",
  "risk_assessment": {
    "risk_score": 10,
    "risk_level": "Critical",
    "summary": "The certificate for api.example.com is expired (expired 542 days ago). As a high-criticality production web server asset, this poses a severe risk of service interruption, man-in-the-middle attacks, and loss of trust for users."
  }
}
```
The "expired" judgement comes from the Python-computed `lifecycle` block, not
the model guessing — so it stays correct regardless of the model's own sense of
the date.

### 7.3 Natural-language query

**Request**
```bash
curl -X 'POST' \
  'http://localhost:8000/api/analyze/query' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "Show me all active domains"
}'
```

**Response**
```json
{
  "query": "Show me all active domains",
  "success": true,
  "sql": "SELECT * FROM assets WHERE type = 'DOMAIN' AND status = 'ACTIVE';",
  "result": "[('domain-1', 'DOMAIN', 'example.com', 'ACTIVE', datetime.datetime(2026, 6, 28, 18, 6, 40, 525071), datetime.datetime(2026, 6, 28, 18, 6, 40, 525074), 'scan', ['root'], {})]"
}
```

**Guardrails in action**
```bash
# Ambiguous adjective -> rejected before any LLM call
curl -X POST http://localhost:8000/api/analyze/query \
  -H "Content-Type: application/json" \
  -d '{"query": "show me the risky assets"}'
```
```json
{
  "query": "show me the risky assets",
  "success": false,
  "error": "Query is ambiguous. Please specify measurable criteria."
}
```
```bash
# Write verb -> rejected
curl -X POST http://localhost:8000/api/analyze/query \
  -H "Content-Type: application/json" \
  -d '{"query": "delete all stale assets"}'
```
```json
{
  "query": "delete all stale assets",
  "success": false,
  "error": "Dangerous queries are not allowed."
}
```

### 7.4 Natural-language report generation

**Request**
```bash
curl http://localhost:8000/api/analyze/report
```

**Response** (`text/markdown`, abridged)
```markdown
# Attack Surface Management Report

## Inventory Overview
- 7 assets across 5 types: 1 domain, 1 subdomain, 1 IP address, 2 services,
  1 certificate, 1 technology.

## Exposed Services
- 443/tcp (nginx) and 80/tcp on 203.0.113.10.

## Certificates
- cert-1 (CN=api.example.com) is **expired** (expired 2025-01-02) and covers the
  production subdomain api.example.com.

## Notable Risks
1. Expired certificate on a production-facing subdomain.
2. Plaintext HTTP service (80/tcp) exposed alongside HTTPS.

## Recommendations
1. Renew or rotate cert-1 immediately.
2. Confirm 80/tcp redirects to HTTPS or retire it.
```

---

## 8. Edge cases handled

| Edge case (Section 7) | How it's handled |
|---|---|
| Idempotent imports | Dedup on `(type, value)`; re-import updates `last_seen` + merges, never duplicates |
| Conflicting data | Recursive metadata merge (nested-merge, leaf last-write-wins); tags unioned |
| Re-appearing assets | A re-sighted asset's status is set back to `active` |
| Malformed/partial records | Per-record SAVEPOINT; failures reported in `failed_records`, batch continues |
| Certificate/lifecycle dates | Python-computed `expired` / `expiring_soon` passed to the model |
| Ambiguous / out-of-scope NL queries | Pre-flight guardrails + SELECT-only enforcement + schema-aware prompt |

---

## 9. What I'd do next

- Enhance the response format for the qurey endpoint to be more readable
- Turn the analysis layer into an agent that calls the API as tools, and add an
  output-quality evaluation harness.
- Cache enrichment/risk results to cut LLM calls on unchanged assets.

---

## License

MIT — see [LICENSE](./LICENSE).
