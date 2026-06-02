# AutoNova Bot

AutoNova Bot is a local-first business assistant that lets users upload company documents, ask questions in natural language, generate or edit documents, and operate through either a web dashboard or Telegram. It combines Docling document conversion, structured JSON extraction, Chroma vector search, local Ollama LLMs, and deterministic business/query logic.

The project is currently an active local prototype for demos, internal workflows, and controlled business use. It is not yet a hardened production SaaS platform.

## Table Of Contents

- [Core Idea](#core-idea)
- [What It Can Do](#what-it-can-do)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Workspace And Storage Model](#workspace-and-storage-model)
- [Document Ingestion Pipeline](#document-ingestion-pipeline)
- [How Question Answering Works](#how-question-answering-works)
- [Dashboard](#dashboard)
- [Telegram Bot](#telegram-bot)
- [Document Generation And Editing](#document-generation-and-editing)
- [Voice, Images, And Web Search](#voice-images-and-web-search)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Run Commands](#run-commands)
- [File Structure](#file-structure)
- [Privacy And Data Handling](#privacy-and-data-handling)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)

## Core Idea

AutoNova is designed around one main workflow:

1. A company or user uploads business documents.
2. The documents are converted into clean Markdown using Docling.
3. The Markdown is parsed into structured JSON records and vector-search chunks.
4. The user asks questions through the dashboard or Telegram.
5. The bot answers using deterministic structured logic where possible, and local LLM reasoning over retrieved document context where needed.

The assistant is intended to answer questions from the user's own files, not from generic memory. Examples:

```text
How many tenants have pending rent?
List all available properties under 1 crore.
What does this agreement say about notice period?
Give me the code for prime number from the TCS NQT document.
Summarize the uploaded inspection report.
Edit the last document and change the tenant name.
```

## What It Can Do

- Run a secure local dashboard for admins and company users.
- Run a Telegram bot connected to the same company workspace.
- Register company users and isolate each company into its own workspace.
- Bulk upload documents from the dashboard.
- Upload documents from Telegram.
- Convert PDFs, DOCX, XLSX, PPTX, HTML, text, Markdown, images, and other supported formats through Docling/fallback converters.
- Store converted Markdown sidecars for inspection and re-use.
- Extract structured records from uploaded documents.
- Store semantic chunks in ChromaDB for retrieval.
- Answer count, list, total, detail, FAQ, table, agreement, rent, property, coding-question, and general document questions.
- Draft TXT, DOCX, and PDF document bundles.
- Edit supported uploaded/generated documents and re-ingest updated versions.
- Generate images.
- Transcribe Telegram voice notes.
- Optionally search/scrape the web through Tavily.

## System Architecture

```text
User
  |
  | Dashboard upload / Telegram upload / Telegram text / CLI ask
  v
Entry Layer
  dashboard/server.py
  bot/telegram_bot.py
  main.py
  |
  v
Document Pipeline
  rag/markdown_converter.py     Docling -> MarkItDown -> local fallback
  rag/structured_store.py       structured JSON extraction
  rag/knowledge_base.py         Chroma vector ingestion and retrieval
  |
  v
Answer Pipeline
  rag/pipeline.py               routing and answer orchestration
  rag/document_queries.py       document-scoped full Markdown answers
  rag/business_queries.py       deterministic business queries
  rag/structured_store.py       structured query answers
  llm/ollama_client.py          local LLM final generation
  |
  v
Outputs
  Telegram reply
  Dashboard state/API response
  Generated TXT/DOCX/PDF/image files
```

The older `autonova/` package is retained as legacy/reference code. The active runtime uses the top-level `bot/`, `dashboard/`, `rag/`, `docs/`, `images/`, `voice/`, `utils/`, and `llm/` packages.

## Tech Stack

Runtime:

- Python 3.10+, recommended Python 3.11
- `python-telegram-bot` for Telegram integration
- Built-in `http.server` for the dashboard backend
- Plain HTML/CSS/JavaScript dashboard UI
- Lucide icons in the dashboard

Document processing:

- Docling as the primary document-to-Markdown converter
- Bundled MarkItDown source as a fallback converter
- `pypdf` / `pdfminer.six` / `pdfplumber` for PDF extraction fallback paths
- `python-docx` for DOCX reading/writing
- `openpyxl` and `pandas` for spreadsheets
- `python-pptx` for PowerPoint support through conversion dependencies
- `Pillow`, `pytesseract`, and Tesseract OCR for image text extraction

RAG and structured knowledge:

- ChromaDB through `langchain-chroma`
- LangChain document loaders and text splitters
- Ollama embeddings through `langchain-ollama`
- Structured local JSON indexes under `workspace/structured`

LLM and generation:

- Ollama for local chat models
- Ollama fallback model support
- OpenAI Whisper package for local voice transcription
- FFmpeg for Telegram voice conversion
- Optional local Stable Diffusion through `diffusers`
- Optional Pollinations image fallback
- Optional Tavily Search/Extract for web search

Storage:

- Local JSON files for users, sessions, chat state, tasks, and logs
- Local workspace folders for uploads, generated outputs, structured records, and ChromaDB

## Workspace And Storage Model

Every company is mapped to a safe workspace ID:

```text
AFF -> aff
CodSoft -> codsoft
Prestige Realty Pvt. Ltd. -> prestige_realty_pvt_ltd
```

Workspace files live here:

```text
workspace/uploads/<workspace>/
workspace/generated/<workspace>/
workspace/generated/<workspace>/_markdown_ingest/
workspace/structured/<workspace>/documents.json
workspace/chroma/
```

Important paths:

- `workspace/uploads/<workspace>/`: uploaded source files
- `workspace/generated/<workspace>/`: generated documents, images, edited outputs, and Markdown sidecars
- `workspace/generated/<workspace>/_markdown_ingest/`: converted Markdown used for RAG
- `workspace/structured/<workspace>/documents.json`: parsed structured records
- `workspace/chroma/`: ChromaDB vector database
- `data/dashboard_users.json`: dashboard user accounts
- `data/conversation_state.json`: Telegram/chat state
- `data/dashboard_admin_bootstrap.txt`: first-run admin password if no password is configured

## Document Ingestion Pipeline

Implemented mainly in:

```text
rag/markdown_converter.py
rag/structured_store.py
rag/knowledge_base.py
```

### 1. Upload

Files can arrive through:

- dashboard bulk upload
- Telegram document upload
- existing files in the workspace/data folder
- generated/edited document re-ingestion

The dashboard and Telegram paths both save files under:

```text
workspace/uploads/<workspace>/
```

### 2. Markdown Conversion

AutoNova converts uploaded documents into Markdown sidecars:

```text
workspace/generated/<workspace>/_markdown_ingest/<filename>.<hash>.md
```

Converter priority:

1. Docling
2. MarkItDown fallback
3. local fallback readers/OCR

The Markdown preserves more useful structure for LLM and parser use:

- headings
- paragraphs
- tables
- code blocks
- lists
- page text
- extracted image/OCR text where available

### 3. Structured JSON

`rag/structured_store.py` parses converted text into JSON records:

- `document_profile`
- `heading`
- `section`
- `paragraph`
- `key_value`
- `entity_line`
- `table`
- `table_row`
- `list_item`
- `qa_pair`
- `question`
- domain records where identifiable, such as `property`, `rent`, `agreement`, `contact`, and `renewal_action`

Structured records are stored in:

```text
workspace/structured/<workspace>/documents.json
```

### 4. Vector Knowledge

`rag/knowledge_base.py` loads the converted Markdown, splits it into chunks, and stores embeddings in ChromaDB. Chunks keep metadata linking them back to the original file and Markdown sidecar.

### 5. Re-Ingestion

When a file is edited or regenerated, AutoNova attempts to re-run the same conversion, structuring, and vector ingestion flow so future answers use the current version.

## How Question Answering Works

Implemented mainly in:

```text
rag/pipeline.py
rag/structured_store.py
rag/document_queries.py
rag/knowledge_base.py
llm/ollama_client.py
```

The answer pipeline uses several layers.

### 1. Conversation Context

Short follow-ups like:

```text
give more details
list them
what about this document?
```

are contextualized from recent chat state where possible.

### 2. Local vs Web Routing

The bot prefers local workspace documents when uploaded documents are relevant. Web search is used only when:

- the user explicitly asks for web/current/latest information
- web search is enabled
- the query is not clearly answerable from local documents

### 3. Deterministic Structured Answers

Structured JSON is checked before general LLM fallback for operations such as:

- counts
- totals
- averages
- highest/lowest values
- property availability
- pending rent
- agreement expiry
- contacts
- question counts
- table rows
- FAQ answers
- coding question lookup

This is faster and more reliable than asking the LLM to infer everything.

### 4. Full Document / Universal Markdown Answers

For broad questions, the bot reads relevant sections from converted Markdown. This is used for questions such as:

```text
What is the core purpose of the bot according to uploaded documents?
Summarize this inspection report.
What conditions are mentioned in the agreement?
List details from the tenant register.
What does the invoice say about commission?
```

The universal document layer scores headings, tables, paragraphs, and excerpts, then asks the local LLM to answer only from the extracted document content.

### 5. Semantic Retrieval

ChromaDB semantic search and lexical fallback retrieve relevant chunks when exact structured matching is not enough.

### 6. LLM Generation

Ollama generates final natural-language answers using the available local context. The model is instructed to avoid guessing when the uploaded documents do not contain enough information.

## Dashboard

Implemented in:

```text
dashboard/server.py
dashboard/static/index.html
```

Run:

```powershell
.\.venv\Scripts\python.exe main.py dashboard
```

Open:

```text
http://127.0.0.1:8765
```

Use another port if needed:

```powershell
.\.venv\Scripts\python.exe main.py dashboard --port 8766
```

### Admin Dashboard

Admin users can:

- view all workspaces
- inspect workspace stats
- see recent activity
- manage registered companies
- view integration health
- open each workspace's files
- upload/download/remove documents inside a selected workspace

The `ALL` workspace is read-only for uploads. Choose a specific workspace before uploading.

### User Dashboard

Company users can:

- access only their own workspace
- upload documents in bulk
- download/remove workspace files
- view generated documents/images
- see Telegram link code
- track onboarding/activity

### Dashboard Upload Behavior

The dashboard supports bulk upload. Each selected file is processed independently:

1. saved to workspace uploads
2. converted to Markdown
3. structured into JSON
4. vector-ingested into Chroma
5. shown in the Knowledge Base Manager

If one file fails, other files in the same batch can still upload.

## Telegram Bot

Implemented in:

```text
bot/telegram_bot.py
```

Run:

```powershell
.\.venv\Scripts\python.exe main.py bot
```

Commands:

```text
/start
/company Your Company Name
/link DASHBOARD_CODE
```

Use `/link CODE` for a dashboard-registered company. The code is shown in the user dashboard. Once linked, Telegram and dashboard use the same workspace.

Use `/company Company Name` for local/non-dashboard workspaces. Dashboard-registered workspaces are protected from unrelated Telegram users.

Telegram supports:

- document uploads
- image/document generation
- document editing
- voice note transcription
- local knowledge questions
- workspace knowledge management

## Document Generation And Editing

Implemented mainly in:

```text
docs/document_ops.py
docs/document_actions.py
rag/document_workflows.py
rag/question_classifier.py
```

Generation examples:

```text
draft a rental agreement for 11 months
create a report from this document
make important questions from this PDF
prepare a client proposal
```

Outputs can include:

- `.txt`
- `.docx`
- `.pdf`

Editing examples:

```text
edit the last document and change tenant name to Rahul
replace buyer name with Priya Shah
add a paragraph about maintenance responsibility
set status to paid in the spreadsheet
```

PDF editing note: PDFs are not layout-edited in place. AutoNova extracts readable text and regenerates a new text-based PDF.

## Voice, Images, And Web Search

### Voice

Implemented in:

```text
voice/transcriber.py
```

Telegram voice flow:

1. download `.ogg`
2. convert with FFmpeg
3. transcribe with Whisper
4. answer through the same RAG pipeline

### Images

Implemented in:

```text
images/generator.py
```

Generated images are stored under:

```text
workspace/generated/<workspace>/
```

External Pollinations fallback is disabled by default.

### Web Search

Implemented in:

```text
utils/web_search.py
```

Disabled by default. Enable only when external/current information is needed.

## Setup

Create a virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create `.env`:

```powershell
Copy-Item .env.example .env
```

Install and start Ollama:

```powershell
ollama pull llama3.2
ollama pull mistral
ollama pull mxbai-embed-large
ollama serve
```

Install optional local tools:

- FFmpeg for voice notes
- Tesseract OCR for image text extraction

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

Images:

```text
ALLOW_IMAGE_EXTERNAL_FALLBACK=false
STABLE_DIFFUSION_MODEL=
```

Web search:

```text
ALLOW_WEB_SEARCH=false
TAVILY_API_KEY=
TAVILY_SEARCH_DEPTH=basic
TAVILY_MAX_RESULTS=5
```

## Run Commands

Doctor check:

```powershell
.\.venv\Scripts\python.exe main.py doctor
```

Dashboard:

```powershell
.\.venv\Scripts\python.exe main.py dashboard
```

Telegram bot:

```powershell
.\.venv\Scripts\python.exe main.py bot
```

Ask from CLI:

```powershell
.\.venv\Scripts\python.exe main.py ask "what documents are uploaded?"
```

Ingest files from `data/`:

```powershell
.\.venv\Scripts\python.exe main.py ingest
```

Rebuild structured JSON:

```powershell
.\.venv\Scripts\python.exe main.py structure --tenant aff
```

Compile check:

```powershell
.\.venv\Scripts\python.exe -m compileall bot dashboard docs images rag utils voice llm main.py
```

## File Structure

```text
main.py
  CLI entrypoint for doctor, ingest, structure, ask, bot, dashboard.

bot/
  telegram_bot.py
    Active Telegram bot handlers and workflows.

dashboard/
  server.py
    Dashboard HTTP server, auth, registrations, overview API, document API.
  static/index.html
    Dashboard frontend.

docs/
  document_ops.py
    TXT/DOCX/PDF/XLSX helpers.
  document_actions.py
    Document action detection, target resolution, edit orchestration.

images/
  generator.py
    Image generation and optional fallback.

llm/
  ollama_client.py
    Ollama chat wrapper and fallback model handling.

rag/
  markdown_converter.py
    Docling/MarkItDown/local conversion to Markdown.
  knowledge_base.py
    Chroma ingestion, retrieval, knowledge file management.
  structured_store.py
    Structured JSON extraction and deterministic structured answers.
  document_queries.py
    Document-scoped and universal Markdown answering helpers.
  pipeline.py
    Main answer routing pipeline.
  business_queries.py
    Selected deterministic business query handlers.
  document_workflows.py
    Source-document based output workflows.
  question_classifier.py
    Question-bank document helpers.
  ocr.py
    Image OCR helpers.

utils/
  config.py
    Environment and workspace path settings.
  storage.py
    Local JSON state helpers.
  intents.py
    Intent classification and prompt cleanup.
  doctor.py
    Dependency checker.
  web_search.py
    Tavily search/extract integration.

voice/
  transcriber.py
    FFmpeg + Whisper voice transcription.

data/
  Runtime dashboard users, chat state, bootstrap credentials.

workspace/
  uploads/
  generated/
  structured/
  chroma/

autonova/
  Legacy/reference Phase 1 implementation.
```

## Privacy And Data Handling

Local by default:

- Ollama chat runs locally.
- Ollama embeddings run locally.
- ChromaDB is local.
- Whisper transcription is local.
- Workspace files and JSON state are local.

External only when explicitly enabled:

- Tavily web search/extract
- Pollinations image fallback

Do not enable external services for confidential client data unless that is acceptable for the deployment.

Keep runtime data out of Git:

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

## Limitations

- The project is a local prototype, not a production SaaS system.
- Dashboard auth is simple local authentication, not enterprise identity.
- Runtime state is JSON-based rather than a transactional database.
- LLM answers depend on model quality and retrieved context.
- No LLM can guarantee perfect answers for every possible document question.
- PDF editing regenerates text-based PDFs and does not preserve complex original layout.
- DOCX rewrite can lose advanced formatting.
- XLSX editing supports common workflows, not every possible spreadsheet action.
- OCR quality depends on source scan quality and Tesseract availability.
- Chroma/Ollama must be healthy for best retrieval quality.
- There is no full audit/versioning UI yet.

## Troubleshooting

Run:

```powershell
.\.venv\Scripts\python.exe main.py doctor
```

Common fixes:

- Restart the dashboard after code changes.
- Hard refresh the browser after frontend changes.
- Start Ollama with `ollama serve`.
- Pull models with `ollama pull llama3.2`, `ollama pull mistral`, and `ollama pull mxbai-embed-large`.
- Install dependencies with `python -m pip install -r requirements.txt`.
- Install FFmpeg for voice.
- Install Tesseract for OCR.
- Rebuild structured records with `main.py structure --tenant <workspace>`.
- Re-upload or re-ingest documents if Markdown sidecars are stale.

## Recommended Next Improvements

- Replace JSON runtime state with a database.
- Add persistent server-side sessions.
- Add document version history and audit logs.
- Add background ingestion jobs for large bulk uploads.
- Add dashboard ingestion progress/status per file.
- Add preview pages for Markdown sidecars and structured records.
- Add stronger role permissions.
- Add automated tests for upload, workspace isolation, and RAG answers.
- Add a queue for long-running Docling/OCR conversions.
