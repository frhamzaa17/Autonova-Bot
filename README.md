# AutoNova Business Operations Assistant

AutoNova is a local-first Telegram business assistant for company operations. It combines local LLM responses, company knowledge retrieval, document ingestion, document generation/editing, spreadsheet operations, voice transcription, image generation, structured business calculations, and optional Tavily web search.

The project is intended to behave like an operations assistant for a business owner:

- understand uploaded internal company documents
- answer operational questions from company data
- retrieve and reason over PDFs, DOCX, XLSX, TXT, and MD files
- draft letters, agreements, proposals, reports, and other business documents
- edit uploaded or previously generated documents
- update business records where supported
- return generated/edited files on Telegram
- remember chat context and current workspace
- optionally search or scrape the web for updated external information

## Current Status

This is an evolving local assistant, not a finished enterprise system. It now has several grounded paths for common business operations, but production use still needs stronger audit controls, database-backed state, richer table extraction, user permissions, and proper document-layout preservation.

The active command entrypoint is:

```powershell
python main.py
```

The newer active bot is in:

```text
bot/telegram_bot.py
```

The older Phase 1 implementation remains in:

```text
autonova/
```

It is kept for compatibility/reference and has partial support for the newer action layer.

## Major Capabilities

### Telegram Assistant

- Handles text messages.
- Handles voice notes through Whisper.
- Handles uploaded files.
- Sends generated documents, edited files, and images back to the user.
- Maintains per-chat workspace state.
- Supports `/company Your Company Name` to separate business workspaces.

### Company Knowledge Base

Uploaded files can be ingested into a company-specific ChromaDB collection.

Supported ingestion formats:

- `.pdf`
- `.docx`
- `.xlsx`
- `.txt`
- `.md`

The bot stores uploaded files under:

```text
workspace/uploads/
```

Vector database files are stored under:

```text
workspace/chroma/
```

The assistant retrieves knowledge before answering business questions.

### Document Upload Behavior

The bot is designed to avoid accidental editing.

If a document is uploaded with a caption like:

```text
save to knowledge base
these are my business details, save them
ingest this
remember this document
```

the file is ingested into the knowledge base.

If Telegram sends multiple uploaded files and only one file has the caption, the bot can inherit recent knowledge-ingest intent for the batch.

Captionless document uploads are treated as knowledge documents by default, not as edit requests.

### Document Generation

The bot can draft business documents from natural language:

```text
draft a rental agreement for Green Valley Residency
prepare a sales proposal for buyer Rahul
write a report on available inventory
create a letter to the tenant for rent follow-up
```

Generated bundles can include:

- TXT
- DOCX
- PDF

Generated files are saved under:

```text
workspace/generated/
```

### Generic Document Action Layer

The project now includes a reusable document action router:

```text
docs/document_actions.py
```

It detects general action requests such as:

- update
- edit
- rewrite
- revise
- modify
- change
- correct
- fill
- replace
- mark
- record
- set

It can resolve the target document from:

- an exact filename mentioned in the message
- the last uploaded file
- the last generated or edited document
- matching workspace documents
- phrases such as `that pdf`, `last document`, or `same file`

Example prompts:

```text
update that PDF and add a termination clause
rewrite the last agreement with buyer name Rahul Sharma
change seller name to Priya Mehta in the document
mark all rows as reviewed in the spreadsheet
update the agreement PDF and share the updated file
```

After editing, the bot sends the updated file back and attempts to ingest the updated version into the knowledge base.

### PDF Handling

PDFs are not edited in-place at the layout level. The bot extracts readable text, applies the instruction, and generates a new PDF.

This means:

- readable text PDFs work best
- scanned/image-only PDFs need OCR support before reliable extraction
- original visual layout may not be preserved
- generated PDFs are text-based regenerated files

### DOCX Handling

The bot supports direct DOCX edits such as:

```text
replace old clause with new clause
add paragraph: Payment due within 7 days.
update deed with buyer name Rahul Sharma and seller name Priya Mehta
```

It recognizes common placeholders:

```text
[BUYER]
[BUYER NAME]
{{BUYER}}
{{BUYER_NAME}}
Buyer Name
Purchaser Name
Name of Buyer
[SELLER]
[SELLER NAME]
{{SELLER}}
{{SELLER_NAME}}
Seller Name
Vendor Name
Name of Seller
```

If direct replacement is not possible, it can ask the local LLM to rewrite the extracted document text and create a new DOCX.

### XLSX Handling

Spreadsheet operations currently support common edits:

```text
update column price +10%
set B2 = 5000
formula E2 = SUM(B2:D2)
mark all rows as reviewed
```

The XLSX editor uses `openpyxl`.

### Structured Business Logic

Some business questions should not be left to the LLM. The project includes deterministic parsers for selected operational tables:

```text
rag/business_queries.py
```

Current structured logic includes:

- property count by status
- available/sold/rented/under-offer property counts
- pending rent calculation
- overdue rent calculation
- tenant/account-specific rent checks
- amount-specific rent checks

Example answers are calculated from table rows, not guessed:

```text
how many properties are available?
```

Returns a count split by residential/commercial and lists property IDs.

```text
show pending rent list
```

Calculates:

```text
Rent Amt - Paid Amt
```

and lists only rows with a balance.

```text
does MedCare have pending rent?
```

Checks the MedCare row directly before answering.

### Business Record Update Actions

The project includes a structured updater for rent tracker PDFs.

Example:

```text
RA-2307 this tenant paid its rent, update the PDF and share the updated PDF
```

The bot:

1. Finds the rent tracker PDF.
2. Finds row `RA-2307`.
3. Updates paid amount, paid date, mode, and status.
4. Generates an updated PDF.
5. Copies it into uploads as a current version.
6. Re-ingests it into the knowledge base.
7. Sends the updated PDF back.

This is implemented as one structured tool inside the generic action layer. Similar structured updaters can be added for other recurring business workflows.

### Tavily Web Search and Scraping

The bot supports optional external web lookup through Tavily.

This is disabled by default because it sends search queries and URLs to an external service.

Enable it in `.env`:

```text
ALLOW_WEB_SEARCH=true
TAVILY_API_KEY=your_tavily_api_key
TAVILY_SEARCH_DEPTH=basic
TAVILY_MAX_RESULTS=5
```

Supported examples:

```text
search web for latest stamp duty rates in Maharashtra
look up current home loan interest rates
what is the latest real estate news in Mumbai?
scrape https://example.com/page and summarize it
```

Implementation:

```text
utils/web_search.py
```

It uses:

- Tavily `/search` for current web search
- Tavily `/extract` for direct URL/page scraping

The assistant combines local company context with web results and asks the local LLM to answer with source URLs.

### Voice Notes

Telegram voice notes are processed as follows:

1. Download `.ogg`.
2. Convert to `.wav` with FFmpeg.
3. Transcribe locally using Whisper.
4. Send the transcribed text through the same assistant pipeline.

Implementation:

```text
voice/transcriber.py
```

### Image Generation

The bot can generate images from natural prompts.

Local Stable Diffusion can be used if configured.

If enabled, Pollinations may be used as an external fallback:

```text
ALLOW_IMAGE_EXTERNAL_FALLBACK=true
```

Generated images are saved under:

```text
workspace/generated/
```

## Project Structure

```text
main.py
  Main CLI entrypoint.

run.py
  Compatibility wrapper around main.py.

bot/
  telegram_bot.py
    Active Telegram bot handlers and orchestration.

llm/
  ollama_client.py
    Local Ollama chat client and model selection.

rag/
  knowledge_base.py
    File loading, ChromaDB ingestion, tenant collections, lexical fallback retrieval.

  pipeline.py
    Main question-answer pipeline.

  business_queries.py
    Deterministic parsers/calculators for structured operational questions.

docs/
  document_ops.py
    DOCX, XLSX, PDF, TXT generation and editing helpers.

  document_actions.py
    Generic document action router for update/edit/rewrite/modify workflows.

images/
  generator.py
    Stable Diffusion hook and Pollinations fallback.

voice/
  transcriber.py
    FFmpeg conversion and Whisper transcription.

utils/
  config.py
    Environment loading and runtime directory setup.

  doctor.py
    System and dependency checker.

  intents.py
    Basic intent classification and helper parsing.

  storage.py
    JSON storage for tasks, knowledge notes, chat memory, and tenant state.

  web_search.py
    Tavily Search and Extract integration.

data/
  Runtime JSON state, tasks, logs, notes.

workspace/
  uploads/
    Uploaded/current documents.

  generated/
    Generated and edited documents/images.

  chroma/
    Local vector database.

autonova/
  Older Phase 1 implementation retained for reference and partial compatibility.
```

## Setup

Recommended Python:

```text
Python 3.11
```

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

Set your Telegram token:

```text
TELEGRAM_BOT_TOKEN=123456:ABC...
```

## Environment Settings

Core:

```text
TELEGRAM_BOT_TOKEN=
ALLOWED_TELEGRAM_USER_IDS=

OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_FALLBACK_MODEL=mistral
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest

DATA_DIR=data
CHROMA_DIR=workspace/chroma
UPLOADS_DIR=workspace/uploads
GENERATED_DIR=workspace/generated

WHISPER_MODEL=base
```

Optional external image fallback:

```text
ALLOW_IMAGE_EXTERNAL_FALLBACK=false
STABLE_DIFFUSION_MODEL=
```

Optional Tavily web search:

```text
ALLOW_WEB_SEARCH=false
TAVILY_API_KEY=
TAVILY_SEARCH_DEPTH=basic
TAVILY_MAX_RESULTS=5
```

## System Requirements

- Python 3.10+, recommended 3.11
- FFmpeg on PATH for voice notes
- Ollama installed and running
- Ollama chat model, usually `llama3.2:latest` or `mistral`
- Ollama embedding model, usually `mxbai-embed-large:latest`
- Telegram bot token
- Tavily API key only if web search is enabled

Pull recommended Ollama models:

```powershell
ollama pull llama3.2
ollama pull mistral
ollama pull mxbai-embed-large
```

## Run

Check system:

```powershell
python main.py doctor
```

Run Telegram bot:

```powershell
python main.py bot
```

Ask locally:

```powershell
python main.py ask "How many properties are available?"
```

Ingest supported files from `data/`:

```powershell
python main.py ingest
```

## Telegram Workflow

### Set Company Workspace

```text
/company AutoNova Realty
```

This creates a workspace ID like:

```text
autonova_realty
```

That workspace controls:

- ChromaDB collection
- chat memory
- last uploaded file
- last generated document
- document action context

### Upload Knowledge Documents

Upload one or more files with:

```text
save to knowledge base
```

or:

```text
these are my business details, save them
```

The bot stores and ingests them.

### Ask Operational Questions

```text
how many properties are available?
show pending rent list
does MedCare have pending rent?
what is the commission for a 2 crore sale?
summarize the SOP for onboarding a property
```

### Draft Documents

```text
draft a rent follow-up letter for Kiran Desai
prepare a sales proposal for PR-003
write an agreement for buyer Rahul and seller Priya
```

### Edit Documents

```text
update that PDF and add a new termination clause
replace buyer name with Rahul Sharma in the last document
mark all rows as reviewed in the spreadsheet
RA-2307 this tenant paid its rent, update the PDF and share it
```

### Web Search

Requires Tavily enabled.

```text
search web for latest stamp duty rates in Maharashtra
scrape https://example.com and summarize it
```

## Answering Workflow

For a normal question:

1. Load recent chat memory.
2. Check deterministic business parsers for known structured operations.
3. Retrieve local company context from ChromaDB and lexical file search.
4. If the question needs current web information and Tavily is enabled, search or extract web content.
5. Send local context and/or web context to Ollama.
6. Return an answer to Telegram.

For a document action:

1. Detect action intent.
2. Resolve target document.
3. Apply direct structured update if available.
4. Otherwise use the general document editor/rewrite path.
5. Save output to `workspace/generated/`.
6. Copy current updated version to `workspace/uploads/`.
7. Re-ingest updated file if possible.
8. Send updated file to Telegram.

## Security and Privacy

Local by default:

- Ollama chat is local.
- Ollama embeddings are local.
- Whisper transcription is local.
- ChromaDB is local.
- Runtime files are ignored by Git.

External only when enabled:

- Pollinations image fallback
- Tavily web search and page extraction

Do not enable external services for confidential client data unless the business accepts that data may leave the machine.

## Runtime Files Ignored by Git

```text
.env
.venv/
data/*.json
data/*.jsonl
workspace/chroma/
workspace/generated/
workspace/uploads/
```

These may contain:

- Telegram tokens
- Tavily API keys
- uploaded client/company documents
- generated legal/business files
- vector database content
- chat history
- business memory

## Current Limitations

- PDF editing regenerates a new text-based PDF; it does not preserve original layout perfectly.
- Scanned/image-only PDFs need OCR support before reliable understanding.
- General table extraction is still basic; structured parsers exist for selected business workflows.
- DOCX full rewrite may not preserve complex formatting.
- XLSX support covers common operations, not every spreadsheet transformation.
- Runtime memory is JSON-based, not a robust multi-user database.
- Telegram chat ID is the current workspace/security boundary.
- Web search is external and only works when Tavily is configured.
- There is no full audit/approval workflow for high-risk business changes yet.

## Recommended Next Improvements

- Add OCR for scanned PDFs and image documents.
- Store extracted tables as structured JSON alongside vector chunks.
- Add a document registry with version history and audit logs.
- Add approval prompts before modifying important documents.
- Add database-backed tenants/users/permissions.
- Add richer DOCX/PDF layout preservation.
- Add more deterministic parsers for business-specific sheets.
- Add automated tests for document action workflows.

## Test Commands

```powershell
python main.py doctor
python main.py ingest
python main.py ask "hello"
python main.py ask "how many properties are available?"
python main.py ask "show pending rent list"
python -m compileall bot llm rag voice docs images utils main.py
```

## Notes

Restart the Telegram bot after code or `.env` changes. A running bot process keeps old code and old environment settings in memory.
