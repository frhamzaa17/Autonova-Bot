# Phase 2 Cost And Production Stack Recommendation

Last updated: June 2, 2026.

This document describes the recommended Phase 2 stack for taking the current AutoNova Bot prototype live. It is written for the current project shape: Python dashboard, Telegram bot, Docling/Markdown ingestion, Chroma vector search, structured JSON extraction, local Ollama LLMs, optional Tavily web search, voice transcription, image generation, and per-company workspaces under `workspace/`.

AutoNova is currently a local-first prototype. Phase 2 should not be treated as "just host the current folder on a VPS." The current system works well for controlled local use, but production needs stronger authentication, persistent storage, backups, monitoring, worker queues, deployment automation, and clear cost controls.

## Current Project Baseline

| Area | Current Implementation | Production Concern |
| --- | --- | --- |
| Dashboard backend | Python stdlib `http.server` in `dashboard/server.py` | Fine for local use, not ideal for concurrent public traffic, middleware, sessions, rate limiting, or observability. |
| Dashboard frontend | Plain HTML/CSS/JavaScript in `dashboard/static/index.html` | Good for MVP. Needs stronger UI state handling, error handling, and auth integration for SaaS. |
| Telegram bot | `python-telegram-bot`, currently suited to local polling | Production should use webhook behind HTTPS or a managed worker process. |
| Tenant model | Company/workspace IDs mapped to local folders | Needs database-backed tenants, roles, limits, audit logs, and quota rules. |
| User/session data | Local JSON under `data/` | Move to PostgreSQL. Local JSON is not safe for multi-user production writes. |
| Uploads/generated files | Local folders under `workspace/uploads` and `workspace/generated` | Move originals and generated files to object storage; keep local temp only. |
| Structured knowledge | `workspace/structured/<tenant>/documents.json` | Move structured records to PostgreSQL tables with indexes. |
| Vector search | Local ChromaDB under `workspace/chroma` | Use managed Postgres + pgvector for simpler ops, or managed/self-hosted Qdrant for larger vector workloads. |
| Document conversion | `rag/markdown_converter.py`: Docling, optional MarkItDown path, local fallback readers/OCR | Run conversion in background workers with timeouts, file size limits, and per-file status. |
| LLM | Ollama local chat + embeddings | Choose between private GPU/Ollama, managed LLM API, or hybrid. Add spending limits and request logging. |
| Voice | Whisper package + FFmpeg | Run as background job. For production, prefer `faster-whisper` or API speech-to-text depending privacy/cost. |
| Web search | Optional Tavily | Keep disabled by default per tenant; log every external search because document context can leak through prompts. |

## Recommended Phase 2 Architecture

```text
Users / Admins
  |
  | HTTPS
  v
Cloudflare DNS + WAF
  |
  v
Nginx / Caddy reverse proxy
  |
  +--> FastAPI API service
  |      - auth, tenants, dashboard API
  |      - Telegram webhook endpoint
  |      - document/task APIs
  |
  +--> Static dashboard frontend
         - current HTML can remain initially
         - later migrate to React/Next.js if needed

Background workers
  - document conversion
  - Markdown parsing
  - structured extraction
  - vector indexing
  - PDF/DOCX generation
  - voice transcription
  - image generation

Data layer
  - PostgreSQL for users, tenants, sessions, structured records, audit logs
  - pgvector or Qdrant for embeddings
  - Cloudflare R2 / S3-compatible storage for uploaded and generated files
  - Redis for queues, locks, rate limits, and ephemeral state

AI layer
  - Option A: Ollama on private GPU server
  - Option B: managed LLM API with strict data policy
  - Option C: hybrid: local embeddings + API chat model
```

## Recommended Stack By Layer

| Layer | Recommended Tool | How To Use It | Why |
| --- | --- | --- | --- |
| Backend API | FastAPI + Uvicorn/Gunicorn | Port `dashboard/server.py` routes into typed FastAPI endpoints. Keep current business modules in `rag/`, `docs/`, `llm/`, `voice/`, `images/`. | Gives production middleware, OpenAPI docs, validation, async support, auth integration, and cleaner testing. |
| Reverse proxy | Nginx or Caddy | Terminate HTTPS, route `/api`, `/telegram/webhook`, and static dashboard files. | Required for TLS, compression, upload limits, and stable public URLs. |
| Frontend | Keep current HTML first; later React/Next.js | Phase 2A: serve current dashboard. Phase 2B: migrate to React only after API stabilizes. | Avoids rewriting UI before the backend is production-safe. |
| Database | PostgreSQL | Store users, tenants, roles, documents, parsed records, messages, tasks, usage, audit events. | Replaces fragile local JSON and supports backups, constraints, transactions. |
| Vector DB | Start with pgvector; move to Qdrant if needed | Store chunk embeddings by tenant, document, chunk ID, metadata. | pgvector keeps MVP ops simple. Qdrant is better once vector scale grows. |
| Object storage | Cloudflare R2 or S3-compatible storage | Store uploads, generated files, Markdown sidecars, exports, and backups. Keep database rows as metadata only. | Durable, cheap, easier backups, avoids filling VPS disk. |
| Queue | Redis + RQ/Celery/Dramatiq | Submit ingestion/conversion jobs from dashboard/Telegram and show status. | Prevents HTTP requests from hanging during Docling/OCR/LLM work. |
| Document conversion | Docling primary + local fallbacks | Run in worker with max file size, timeout, and retry policy. Store converted Markdown in object storage. | Current pipeline already works; production needs isolation and status tracking. |
| OCR | Tesseract locally; optional cloud OCR later | Use for image scans and image-heavy PDFs after Docling fallback. | Keeps privacy local and avoids per-page OCR API costs initially. |
| LLM chat | Ollama private GPU or managed API | Use tenant-level setting: `local_private`, `managed_api`, or `disabled`. Log model, token estimate, latency, and cost. | Lets privacy-sensitive clients stay private while others use cheaper managed models. |
| Embeddings | `mxbai-embed-large` via Ollama or hosted embedding API | Keep embedding model consistent per tenant; version embeddings when changing model. | Stable retrieval depends on a stable embedding model. |
| Telegram | Webhook mode | Set Telegram webhook to `https://domain.com/telegram/webhook/<secret>`. | More reliable than long polling for hosted production. |
| Auth | Password hashing + sessions/JWT; later SSO | Store users in PostgreSQL, hash with Argon2/bcrypt, add role-based access. | Current local bootstrap/admin model is not enough for live multi-company use. |
| Monitoring | Sentry + Prometheus/Grafana or hosted equivalent | Track exceptions, ingestion failures, LLM latency, queue depth, disk, memory, and request rates. | Needed before real users depend on it. |
| Backups | Daily PostgreSQL backup + object storage lifecycle | Encrypt backups, retain 7 daily + 4 weekly + 3 monthly copies. Test restore monthly. | Production data is mostly client documents; backup failure is business failure. |
| CI/CD | GitHub Actions + Docker images | Run lint/compile/tests, build image, deploy to VPS via SSH or registry. | Makes releases repeatable and safer. |

## Production Data Model To Add

Move these local files/folders into database/object storage gradually:

| Current Path | Production Target |
| --- | --- |
| `data/dashboard_users.json` | `users`, `companies`, `memberships`, `roles` tables |
| `data/conversation_state.json` | `conversations`, `messages`, `telegram_links` tables |
| `data/dashboard_admin_bootstrap.txt` | One-time admin setup flow; never store bootstrap password in repo |
| `workspace/uploads/<tenant>/` | Object storage bucket prefix: `uploads/<tenant>/<document_id>/original` |
| `workspace/generated/<tenant>/` | Object storage prefix: `generated/<tenant>/<artifact_id>/...` |
| `workspace/generated/<tenant>/_markdown_ingest/` | Object storage prefix plus `document_markdown` database row |
| `workspace/structured/<tenant>/documents.json` | `document_records`, `record_fields`, `document_tables` tables |
| `workspace/chroma/` | `pgvector` tables or Qdrant collection |

Minimum useful PostgreSQL tables:

- `companies`: tenant/company profile and workspace slug.
- `users`: dashboard users.
- `memberships`: user to company mapping with role.
- `documents`: uploaded/generated document metadata.
- `document_versions`: original, converted, edited, generated file versions.
- `document_chunks`: Markdown chunk text, metadata, embedding reference.
- `document_records`: structured extracted business entities.
- `tasks`: ingestion/conversion/generation jobs and status.
- `conversations`: Telegram/dashboard chat sessions.
- `messages`: user/bot messages with source channel.
- `audit_events`: logins, uploads, deletes, exports, integrations, admin actions.
- `usage_events`: LLM calls, web searches, image generation, voice transcription, token/cost estimates.

## Phase 2 Implementation Plan

### Phase 2A: Production Hardening Without Full Rewrite

Goal: make the current app safer and deployable with minimal feature changes.

1. Containerize the current app.
   - Add `Dockerfile` and `docker-compose.yml`.
   - Include Python 3.11, FFmpeg, Tesseract, and project requirements.
   - Mount `workspace/` and `data/` as persistent volumes only for staging/local.

2. Add a production settings layer.
   - Keep `.env` for local.
   - Add explicit `APP_ENV=local|staging|production`.
   - Require strong secrets in production.
   - Disable debug endpoints and local bootstrap behavior in production.

3. Add request/file safety limits.
   - Max upload size per file.
   - Allowed extensions.
   - Virus scan hook, even if initially optional.
   - Per-tenant storage limits.
   - Conversion timeout per file.

4. Add a worker queue.
   - Dashboard upload creates a task.
   - Worker processes document conversion and ingestion.
   - UI polls task status.
   - Failed files show reason and retry action.

5. Move only user/session/task data to PostgreSQL first.
   - Leave document files in `workspace/` temporarily.
   - This immediately fixes concurrency risk around local JSON.

6. Deploy behind HTTPS.
   - Use a VPS with Docker Compose.
   - Run app, worker, Redis, PostgreSQL, and reverse proxy.
   - Use Caddy for simple automatic TLS or Nginx with Certbot.

### Phase 2B: Proper SaaS Data Layer

Goal: make tenant data durable and scalable.

1. Move uploads/generated files to Cloudflare R2 or S3.
2. Move structured JSON into PostgreSQL tables.
3. Replace local Chroma with pgvector or Qdrant.
4. Add audit log pages and admin usage reporting.
5. Add scheduled backups and restore tests.
6. Add tenant quotas and billing-ready usage counters.

### Phase 2C: Production AI And Integrations

Goal: make AI reliable, cost-controlled, and integration-ready.

1. Add model routing.
   - Local/private model for confidential tenants.
   - Managed API model for tenants that allow cloud inference.
   - Smaller model for classification/routing.
   - Larger model only for final complex answers.

2. Add cost tracking.
   - Store every LLM/search/image/voice call in `usage_events`.
   - Show monthly estimate per tenant.
   - Add hard monthly limits.

3. Add official portal integrations only where allowed.
   - Start with CSV/export adapters.
   - Add partner APIs only after written access.
   - Never scrape real-estate portals without permission.

## Deployment Options And Costs

All INR figures are planning estimates using roughly USD 1 = INR 85. Recheck exchange rate and provider pricing before quoting a client.

### Option 1: Lean Production MVP

Best for: one client, low to medium traffic, no heavy local LLM on server.

| Component | Suggested Setup | Estimated Monthly Cost |
| --- | --- | ---: |
| VPS | 2-4 vCPU, 4-8 GB RAM, 80-160 GB SSD | USD 12-48 / INR 1,000-4,100 |
| PostgreSQL | Managed Postgres small plan or same VPS for first month | USD 15-60 / INR 1,300-5,100 |
| Redis | Same VPS or managed small Redis | USD 0-15 / INR 0-1,300 |
| Object storage | Cloudflare R2 | Often free for small use; then about USD 0.015/GB-month |
| LLM | Managed API or existing local office Ollama through secure tunnel/VPN | Usage-based |
| Monitoring | Sentry free/pro + uptime monitor | USD 0-30 / INR 0-2,600 |
| Backups | DB snapshots + R2 backup storage | USD 5-25 / INR 425-2,100 |
| Total infra estimate | Without heavy LLM usage | INR 2,500-12,000/month |

Use this if Phase 2 must go live quickly. Keep Ollama on a client-owned machine if document privacy requires local inference.

### Option 2: Balanced SaaS-Ready Stack

Best for: multiple companies, stable production traffic, better reliability.

| Component | Suggested Setup | Estimated Monthly Cost |
| --- | --- | ---: |
| App server | 4-8 vCPU, 8-16 GB RAM VPS | USD 48-96 / INR 4,100-8,200 |
| Worker server | Separate 4-8 vCPU worker for Docling/OCR | USD 24-96 / INR 2,000-8,200 |
| Managed PostgreSQL | 2-4 GB RAM with backups | USD 30-120 / INR 2,600-10,200 |
| Redis | Managed or small VPS service | USD 15-60 / INR 1,300-5,100 |
| Object storage | R2/S3 for uploads/generated files | USD 0-50+ / INR 0-4,300+ depending storage |
| Vector store | pgvector in Postgres initially | Included in DB cost |
| LLM | Managed API for chat, local/Ollama for embeddings | Usage-based, commonly INR 2,000-25,000+ |
| Monitoring/logs | Sentry, Grafana, uptime monitor | USD 20-100 / INR 1,700-8,500 |
| Total infra estimate | Moderate usage | INR 15,000-60,000/month |

Use this when the product has real users and uptime matters.

### Option 3: Private AI / GPU Deployment

Best for: clients that cannot send document context to external LLM APIs.

| Component | Suggested Setup | Estimated Monthly Cost |
| --- | --- | ---: |
| App + DB stack | Same as Balanced SaaS stack | INR 15,000-40,000/month |
| GPU server | RTX 4090/L40S/A100-class rented GPU or client-owned GPU machine | INR 30,000-2,00,000+/month rented, or hardware CAPEX |
| Ollama models | `llama3.2`, Mistral, Qwen/Llama variants, embedding model | No license cost for open models, but compute cost applies |
| Storage/backups | R2/S3 + database snapshots | INR 1,000-10,000+/month |
| Total estimate | Private hosted AI | INR 50,000-2,50,000+/month |

Use this only when privacy requirements justify GPU cost. For most early clients, a hybrid design is more practical.

## Current Official Pricing Anchors

These are the public pricing anchors used for the estimates above:

- DigitalOcean Droplets start at low monthly VPS pricing and bill per second with a monthly cap; their published Droplet page states pricing starts as low as USD 4/month and includes SSD storage and outbound transfer depending on plan. Source: <https://www.digitalocean.com/products/droplets>
- DigitalOcean Managed PostgreSQL currently lists small PostgreSQL plans from about USD 15.15/month for 1 GB RAM/1 vCPU, with higher plans at about USD 30.45, USD 60.90, USD 122.10, and above. Source: <https://www.digitalocean.com/pricing/managed-databases>
- Cloudflare R2 Standard storage lists USD 0.015/GB-month, USD 4.50/million Class A operations, USD 0.36/million Class B operations, and free egress, with a free tier of 10 GB-month storage, 1 million Class A operations, and 10 million Class B operations. Source: <https://developers.cloudflare.com/r2/pricing/>
- Runpod documents GPU Pods as per-second billed compute/storage and says latest GPU prices should be checked in the Runpod console at deployment time; storage examples include container/volume/network disk rates. Source: <https://docs.runpod.io/pods/pricing>
- OpenAI API pricing is usage-based, separate from ChatGPT subscriptions, and supports monthly budgets/spend controls in billing settings. Source: <https://openai.com/api/pricing/>
- Tavily offers free monthly API credits and paid credit-based plans; current docs list 1,000 free credits/month, pay-as-you-go at USD 0.008/credit, and monthly plans such as Project/Bootstrap/Startup/Growth. Source: <https://tavilyai.mintlify.app/documentation/api-credits>

## Recommended Production Configuration

For the next real deployment, use this stack:

```text
Domain/DNS:       Cloudflare
TLS/proxy:        Caddy or Nginx
App runtime:      Docker Compose on Ubuntu 24.04 LTS
Backend:          FastAPI + Uvicorn/Gunicorn
Frontend:         Current static dashboard first; React/Next.js later
Database:         PostgreSQL 16+
Vector search:    pgvector first
Queue/cache:      Redis
Workers:          RQ/Celery/Dramatiq
Object storage:   Cloudflare R2
LLM:              Hybrid: local Ollama embeddings + configurable chat provider
OCR:              Tesseract in worker image
Docs:             Docling in worker image
Monitoring:       Sentry + uptime monitor + structured logs
Backups:          Daily Postgres dumps + R2 lifecycle + monthly restore drill
CI/CD:            GitHub Actions + Docker image build + SSH deploy
```

## How To Use Each Major Service

### PostgreSQL

Use PostgreSQL as the system of record. Do not keep production users, sessions, or structured records in JSON files.

Implementation steps:

1. Add SQLAlchemy or SQLModel.
2. Add Alembic migrations.
3. Create tables for users, companies, documents, records, tasks, messages, audit logs, and usage events.
4. Replace JSON read/write helpers gradually.
5. Add database transactions around upload/ingestion task creation.

### pgvector

Use pgvector first because it keeps the first production deployment simple.

Implementation steps:

1. Enable the `vector` extension.
2. Store one row per chunk with tenant ID, document ID, chunk text, metadata, and embedding.
3. Add indexes by tenant/document and vector similarity.
4. Keep embedding model version in each row.
5. Re-embed documents when changing embedding models.

Move to Qdrant later if vector data grows large or query latency becomes a problem.

### Cloudflare R2

Use R2 for files, not PostgreSQL.

Recommended prefixes:

```text
uploads/<tenant_id>/<document_id>/original/<filename>
generated/<tenant_id>/<artifact_id>/<filename>
markdown/<tenant_id>/<document_id>/<hash>.md
exports/<tenant_id>/<export_id>/<filename>
backups/<date>/...
```

Store only metadata and object keys in PostgreSQL.

### Redis And Workers

Use Redis for:

- background job queue
- task locks
- rate limits
- temporary progress state
- Telegram webhook deduplication

Use workers for anything slow:

- Docling conversion
- OCR
- Chroma/pgvector indexing
- LLM-heavy summaries
- PDF/DOCX generation
- voice transcription
- image generation

### LLM Provider

Use a tenant-level LLM mode:

```text
local_ollama     highest privacy, needs GPU/CPU capacity
managed_api      easiest scaling, usage-based cost
hybrid           local embeddings + managed chat
disabled         deterministic structured answers only
```

For production, add:

- monthly tenant spend limit
- max tokens per answer
- per-feature model choice
- prompt logging with redaction
- model fallback
- answer source citations from uploaded documents

### Telegram

Use webhook mode:

1. Create `TELEGRAM_WEBHOOK_SECRET`.
2. Expose `POST /telegram/webhook/<secret>`.
3. Set webhook through Telegram Bot API.
4. Store update IDs to prevent duplicate processing.
5. Add tenant/user linking through expiring one-time codes.

### Web Search

Keep Tavily optional and off by default for production tenants.

Use it only when:

- user explicitly asks for current web data
- tenant has enabled web search
- request does not include confidential document text unless client policy allows it

Log every search query and result URL.

## Security Checklist

Before going live:

- Force HTTPS.
- Hash all passwords with Argon2 or bcrypt.
- Add role-based access: owner, admin, member, read-only.
- Add CSRF protection if using cookie sessions.
- Add request rate limits.
- Add max upload size and allowed extensions.
- Scan uploads or at least quarantine unsupported files.
- Store secrets only in environment/secret manager.
- Encrypt database backups.
- Disable directory listing and debug tracebacks.
- Add audit logs for login, upload, delete, export, user invite, integration changes.
- Add tenant isolation tests.
- Add data deletion/export workflow.
- Add privacy policy and terms before external users.

## Minimum Checks Before Every Release

Run locally or in CI:

```powershell
.\.venv\Scripts\python.exe main.py doctor
.\.venv\Scripts\python.exe -m compileall bot dashboard docs images rag utils voice llm main.py
```

Recommended additional Phase 2 checks:

```powershell
pytest
ruff check .
bandit -r .
pip-audit
```

## Final Recommendation

For the first live version, use the Balanced SaaS-Ready Stack but keep the frontend simple:

1. FastAPI backend.
2. Current dashboard served as static UI.
3. PostgreSQL for users, tenants, records, tasks, audit, and usage.
4. Cloudflare R2 for uploaded/generated/Markdown files.
5. Redis worker queue for document processing.
6. pgvector for retrieval.
7. Hybrid AI: local Ollama embeddings plus configurable chat provider.
8. HTTPS reverse proxy, monitoring, backups, and CI/CD from day one.

Expected serious production budget: INR 15,000-60,000/month for normal hosted SaaS usage without private GPU. If the client requires private hosted LLM inference, budget INR 50,000-2,50,000+/month depending on GPU choice and traffic.
