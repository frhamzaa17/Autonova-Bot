# AutoNova Bot

AutoNova Bot is a local-first business operations assistant with a Telegram bot, a secure web dashboard, local document intelligence, document generation/editing, image generation, voice transcription, structured business querying, and optional web search.

The project is designed for company/workspace-based usage. Each company workspace keeps its own uploaded files, generated files, structured document JSON, vector knowledge, chat context, and dashboard view.

Current project status: active local prototype, suitable for demos, internal testing, and controlled business workflows. It is not yet a production multi-tenant SaaS system.

## What It Does

- Runs a Telegram assistant for business questions and file workflows.
- Runs a browser dashboard for admin and company users.
- Registers company accounts with isolated workspaces.
- Links Telegram chats to registered dashboard companies with `/link CODE`.
- Uploads and structures PDFs, DOCX, XLSX, TXT, MD, and OCR-supported images.
- Answers questions from local company documents and structured records.
- Drafts business documents as TXT, DOCX, and PDF bundles.
- Edits uploaded or generated documents where supported.
- Generates images and stores them inside the active company workspace.
- Transcribes Telegram voice notes with Whisper.
- Uses local Ollama models for chat and embeddings.
- Uses ChromaDB for local vector retrieval.
- Optionally uses Tavily for external/current web search.
- Optionally uses Pollinations as an external image fallback.

## Current State

Active entrypoint:

```powershell
python main.py
```

Active runtime modules:

- Telegram bot: `bot/telegram_bot.py`
- Dashboard backend: `dashboard/server.py`
- Dashboard UI: `dashboard/static/index.html`
- Retrieval and structured document logic: `rag/`
- Document generation/editing: `docs/`
- Runtime configuration/storage helpers: `utils/`

Legacy reference implementation:

- `autonova/`

The `autonova/` package is older Phase 1 code kept for reference/compatibility. The current dashboard and bot use the top-level `bot/`, `dashboard/`, `rag/`, `docs/`, `images/`, `voice/`, and `utils/` packages.

## Tech Stack

- Python 3.10+, recommended Python 3.11
- `python-telegram-bot` for Telegram integration
- Ollama for local LLM chat
- Ollama embeddings through `langchain-ollama`
- ChromaDB through `langchain-chroma`
- LangChain document loaders/text splitters
- `python-docx` for DOCX creation/editing
- `openpyxl` for XLSX reading/editing
- `pypdf` for PDF text extraction
- Local PDF writer helpers for generated PDFs
- OpenAI Whisper package for local speech transcription
- FFmpeg for Telegram voice conversion
- Tesseract/Pytesseract and Pillow for OCR image handling
- Built-in Python `http.server` for the dashboard backend
- Plain HTML/CSS/JavaScript dashboard UI with Lucide icons
- JSON files for local runtime state
- Optional Tavily Search/Extract API for web search
- Optional Pollinations fallback for image generation
- Optional local Stable Diffusion model via `diffusers` if configured and installed separately

## Workspace Model

Workspace IDs are safe lowercase identifiers derived from company names, for example:

```text
CodSoft -> codsoft
AFF -> aff
```

Workspace-scoped files are stored under:

```text
workspace/uploads/<workspace>/
workspace/generated/<workspace>/
workspace/structured/<workspace>/documents.json
```

The dashboard no longer shows the internal `default` fallback workspace. Real dashboard workspaces come from registered companies, linked Telegram state, and actual workspace folders.

## Dashboard

Run:

```powershell
.\.venv\Scripts\python.exe main.py dashboard
```

Open:

```text
http://127.0.0.1:8765
```

If port `8765` is busy:

```powershell
.\.venv\Scripts\python.exe main.py dashboard --port 8766
```

### Admin Dashboard

Admin login defaults to the `ALL` overview.

Admin features:

- Cross-workspace stats and activity.
- Company registration list.
- Integration status for Ollama, Telegram, Tavily, ChromaDB, OCR, and voice.
- Workspace dropdown with `ALL` plus real workspaces only.
- Knowledge Base Manager starts with workspace rows.
- Clicking a workspace opens that workspace's files.
- `Workspaces` button returns to the workspace list.
- Inside a workspace, files are grouped as:
  - Uploaded
  - Generated - Docs
  - Generated - Images

Upload is hidden on `ALL` and only appears inside a selected workspace.

### User Dashboard

User dashboard is locked to that user's registered company workspace.

User dashboard features:

- Own company stats.
- Own workspace activity.
- Own knowledge base files.
- Upload/download/remove documents for that workspace.
- Telegram link command for connecting the Telegram bot.

The workspace dropdown is hidden for users because users cannot switch workspaces.

### First Admin Login

Set these before first dashboard run:

```text
DASHBOARD_ADMIN_USERNAME=admin
DASHBOARD_ADMIN_PASSWORD=choose-a-strong-password
```

If `DASHBOARD_ADMIN_PASSWORD` is empty, the dashboard creates a random bootstrap password and saves it here:

```text
data/dashboard_admin_bootstrap.txt
```

## Telegram Bot

Run:

```powershell
.\.venv\Scripts\python.exe main.py bot
```

Telegram commands:

```text
/start
/company Your Company Name
/link DASHBOARD_CODE
```

Use `/link CODE` for dashboard-registered companies. The code appears in the user dashboard. Once linked, Telegram uploads, generated files, image generations, and questions use the same company workspace as the dashboard.

Use `/company Company Name` only for local/non-dashboard workspaces. Dashboard-registered workspaces are protected from being claimed by unrelated Telegram users.

## Main Features

### Knowledge Base

Supported upload/ingestion formats:

- PDF
- DOCX
- XLSX
- TXT
- MD
- JPG/JPEG/PNG/WEBP and other configured OCR image extensions

Uploads are stored in:

```text
workspace/uploads/<workspace>/
```

Vector knowledge is stored in:

```text
workspace/chroma/
```

Structured decoded knowledge is stored in:

```text
workspace/structured/<workspace>/documents.json
```

### Structured Document Understanding

Implemented in:

```text
rag/structured_store.py
```

The structured decoder extracts:

- document profiles
- headings and sections
- paragraphs
- key-value records
- entity lines
- dates and normalized ISO dates
- money/amount values
- IDs, emails, and phone-like values
- bullets and list items
- question/answer records
- DOCX table rows
- XLSX rows
- inferred PDF/text table rows

Specialized record logic currently supports stronger handling for:

- question banks
- rental agreements
- renewal pipelines
- rent trackers
- property listings
- client/contact data
- spreadsheets
- generic business/legal documents

Structured answers are used before LLM fallback for counts, totals, filters, document details, agreement queries, question counts, rent logic, and similar deterministic operations.

### Document Generation

Examples:

```text
draft a rental agreement for 11 months
prepare a sales proposal
create a tenant follow-up letter
make a report from this document
```

Generated bundles can include:

- `.txt`
- `.docx`
- `.pdf`

Generated files are stored in:

```text
workspace/generated/<workspace>/
```

### Document Editing

Implemented mainly in:

```text
docs/document_actions.py
docs/document_ops.py
```

Supported actions include:

- update
- edit
- rewrite
- revise
- modify
- replace
- correct
- fill
- set cell values
- add formulas
- mark spreadsheet rows

Target documents can be resolved from:

- exact filename
- last uploaded file
- last generated file
- last edited file
- phrases such as `last document`, `that PDF`, `same file`
- matching files inside the active workspace

After editing, the bot attempts to re-ingest the edited version so dashboard and knowledge-base views can reflect it.

Important PDF note: PDFs are not edited in place with layout preservation. Readable PDF text is extracted, changed, and regenerated as a new text-based PDF.

### Image Generation

Implemented in:

```text
images/generator.py
```

Images are generated from natural prompts and stored in:

```text
workspace/generated/<workspace>/
```

Local Stable Diffusion can be used if configured. If local generation is unavailable and enabled, Pollinations can be used as an external fallback:

```text
ALLOW_IMAGE_EXTERNAL_FALLBACK=true
```

Keep this disabled for private/confidential prompts.

### Voice Notes

Implemented in:

```text
voice/transcriber.py
```

Flow:

1. Telegram `.ogg` voice file is downloaded.
2. FFmpeg converts audio.
3. Whisper transcribes locally.
4. Transcript is sent through the same question pipeline.

### Web Search

Implemented in:

```text
utils/web_search.py
```

Disabled by default. Enable with:

```text
ALLOW_WEB_SEARCH=true
TAVILY_API_KEY=your_key
```

Use it for:

```text
search web for latest stamp duty rates
look up current home loan rates
scrape https://example.com and summarize it
```

External web search may send query text or URLs to Tavily.

## How The Assistant Answers

Implemented in:

```text
rag/pipeline.py
```

General flow:

1. Load recent chat memory.
2. Rewrite short follow-ups such as `give details` using recent context.
3. Detect document-scoped/local vs external/general intent.
4. Run deterministic business/query handlers where possible.
5. Query structured JSON records.
6. Retrieve file context from ChromaDB and lexical fallback search.
7. Use Tavily when explicitly requested or when the question is clearly current/external and web search is enabled.
8. Ask Ollama to answer using the available context.

## Setup

Create and activate a virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy environment template:

```powershell
Copy-Item .env.example .env
```

Install and start Ollama, then pull recommended models:

```powershell
ollama pull llama3.2
ollama pull mistral
ollama pull mxbai-embed-large
ollama serve
```

Install FFmpeg for voice notes and Tesseract for OCR if those features are needed.

## Environment Variables

Core:

```text
TELEGRAM_BOT_TOKEN=
ALLOWED_TELEGRAM_USER_IDS=

DASHBOARD_ADMIN_USERNAME=admin
DASHBOARD_ADMIN_PASSWORD=

OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_FALLBACK_MODEL=mistral
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest

DATA_DIR=data
CHROMA_DIR=workspace/chroma
UPLOADS_DIR=workspace/uploads
GENERATED_DIR=workspace/generated
STRUCTURED_DIR=workspace/structured

WHISPER_MODEL=base
```

Optional images:

```text
ALLOW_IMAGE_EXTERNAL_FALLBACK=false
STABLE_DIFFUSION_MODEL=
```

Optional web:

```text
ALLOW_WEB_SEARCH=false
TAVILY_API_KEY=
TAVILY_SEARCH_DEPTH=basic
TAVILY_MAX_RESULTS=5
```

## Run Commands

Check dependencies:

```powershell
.\.venv\Scripts\python.exe main.py doctor
```

Run dashboard:

```powershell
.\.venv\Scripts\python.exe main.py dashboard
```

Run Telegram bot:

```powershell
.\.venv\Scripts\python.exe main.py bot
```

Ask a local CLI question:

```powershell
.\.venv\Scripts\python.exe main.py ask "hello"
```

Ingest files from `data/`:

```powershell
.\.venv\Scripts\python.exe main.py ingest
```

Regenerate structured JSON for one workspace:

```powershell
.\.venv\Scripts\python.exe main.py structure --tenant codsoft
```

Compile check:

```powershell
.\.venv\Scripts\python.exe -m compileall bot dashboard docs images rag utils main.py
```

## Example Telegram Prompts

Knowledge:

```text
save this to knowledge base
show my knowledge base
how many files are in my knowledge base?
remove "filename.pdf" from knowledge base
```

Questions:

```text
summarize this document
how many questions are in this PDF?
list the table rows
give more details
```

Documents:

```text
draft a rental agreement for 11 months
create a report from this document
edit the last document and change landlord name to Shadab
replace buyer name with Rahul Sharma
```

Images:

```text
generate image of a person coding on a laptop
make the previous image brighter and add labels
```

Web:

```text
search web for latest AI regulations in India
scrape https://example.com and summarize it
```

## File Structure

```text
main.py
  CLI entrypoint for doctor, ingest, structure, ask, bot, and dashboard.

run.py
  Compatibility wrapper.

bot/
  telegram_bot.py
    Active Telegram bot handlers, workspace linking, uploads, actions, image/document workflows.

dashboard/
  server.py
    Dashboard HTTP server, auth, registration, sessions, overview APIs, document APIs.

  static/index.html
    Admin/user dashboard UI.

docs/
  document_ops.py
    DOCX/XLSX/PDF/TXT creation and editing helpers.

  document_actions.py
    Generic document action detection and target resolution.

  user_manual.md
    End-user prompt and workflow guide.

images/
  generator.py
    Local Stable Diffusion hook and Pollinations fallback.

llm/
  ollama_client.py
    Ollama chat wrapper and model fallback behavior.

rag/
  knowledge_base.py
    File loading, ChromaDB ingestion, tenant collections, lexical retrieval, knowledge file management.

  pipeline.py
    Main question-answer routing pipeline.

  structured_store.py
    Universal structured decoder and structured query answering.

  document_queries.py
    Document-scoped query helpers and target file resolution.

  document_workflows.py
    Workflows for creating documents from uploaded/source documents.

  question_classifier.py
    Question-bank document generation/classification helpers.

  business_queries.py
    Deterministic business logic for selected property/rent queries.

  ocr.py
    OCR image extraction helpers.

utils/
  config.py
    Environment loading, path setup, workspace-safe IDs.

  doctor.py
    Dependency/system checker.

  intents.py
    Intent classification and prompt cleanup.

  storage.py
    JSON state storage, chat history, tenant state, notes/tasks.

  web_search.py
    Tavily Search/Extract integration and web query routing helpers.

voice/
  transcriber.py
    FFmpeg + Whisper voice transcription.

data/
  Runtime JSON state, dashboard users, admin bootstrap credentials.

workspace/
  uploads/<workspace>/
    Uploaded and current workspace documents.

  generated/<workspace>/
    Generated/edited documents and images.

  structured/<workspace>/documents.json
    Structured decoded records for that workspace.

  chroma/
    Local ChromaDB vector database files.

autonova/
  Older Phase 1 implementation retained for reference.
```

## Data, Privacy, And Runtime Files

Local-first by default:

- Ollama chat runs locally.
- Ollama embeddings run locally.
- ChromaDB is local.
- Whisper transcription is local.
- JSON runtime state is local.

External only when enabled:

- Tavily web search/extract
- Pollinations image fallback

Do not enable external features for confidential client data unless that is acceptable for the deployment.

Runtime files may contain secrets, documents, chat history, and generated legal/business content. Keep them out of Git:

```text
.env
.venv/
data/*.json
data/*.jsonl
data/dashboard_admin_bootstrap.txt
workspace/chroma/
workspace/generated/
workspace/uploads/
workspace/structured/
```

## Qualities

- Workspace isolated: company data is separated by workspace ID.
- Local-first: core LLM, embeddings, vector DB, and transcription are local.
- Dashboard protected: admin/user sessions enforce workspace access.
- Practical document support: handles common business PDFs, Word files, spreadsheets, and generated docs.
- Structured before generative: deterministic record queries are tried before LLM fallback.
- Extensible: new structured parsers and document actions can be added without rewriting the bot.

## Limitations

- Runtime state is JSON-based, not a production database.
- Dashboard auth is suitable for local/internal use, not hardened enterprise identity.
- PDF editing regenerates text-based PDFs and does not preserve complex original layouts.
- DOCX rewrite may lose advanced formatting.
- XLSX editing supports common operations, not every spreadsheet workflow.
- OCR quality depends on Tesseract and source image quality.
- Chroma/Ollama availability affects retrieval and answer quality.
- External web/image providers are disabled by default and may receive prompts/queries when enabled.
- No full audit trail, approval workflow, or document version UI yet.

## Recommended Next Improvements

- Move dashboard users, sessions, chat state, and activity logs to a real database.
- Add document version history and audit logs.
- Add confirmation/approval prompts for high-risk document changes.
- Add automated tests around workspace isolation and document actions.
- Improve PDF layout preservation and table extraction.
- Add richer dashboard previews for generated images/documents.
- Add role permissions beyond admin/user.
- Add cleanup/archive tools for old generated files.

## Troubleshooting

Run:

```powershell
.\.venv\Scripts\python.exe main.py doctor
```

Common fixes:

- Start Ollama: `ollama serve`
- Pull models: `ollama pull llama3.2`, `ollama pull mistral`, `ollama pull mxbai-embed-large`
- Install dependencies: `python -m pip install -r requirements.txt`
- Install FFmpeg for voice notes.
- Install Tesseract for OCR.
- Restart the bot/dashboard after editing code or `.env`.

