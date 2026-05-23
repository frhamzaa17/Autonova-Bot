# AutoNova Local Mega Business Personal Assistant

Local-first Telegram assistant for company operations. It uses Ollama for LLM responses, ChromaDB for company knowledge retrieval, Whisper for voice transcription, local file handling for documents/spreadsheets, and optional image generation.

The goal is a self-contained business assistant that can answer from company data, draft and edit documents, process spreadsheets, remember conversation flow, generate images, and operate from Telegram.

## Current Features

- Telegram bot for text, voice notes, and file uploads.
- Per-chat company workspace/session.
- Company-specific knowledge base using ChromaDB collections.
- Upload and ingest business files: property listings, contacts, pricing sheets, SOPs, FAQs.
- Knowledge-base-first answering before general LLM answers.
- Recent conversation memory per Telegram chat.
- DOCX editing and template filling.
- XLSX cell/column/formula/status updates.
- PDF text extraction and rewritten PDF output.
- Document generation as TXT, DOCX, and PDF.
- Image generation from natural prompts.
- Voice transcription with FFmpeg + local Whisper.
- Local Ollama backend with `llama3.2` and fallback model support.

## System Requirements

- Python 3.10+, recommended Python 3.11
- FFmpeg on PATH
- Ollama installed and running
- Ollama chat model: `llama3.2:latest` or `mistral`
- Ollama embedding model: `mxbai-embed-large:latest`

Check the system:

```powershell
python main.py doctor
```

If anything is missing, the doctor command prints install commands.

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set the Telegram token in `.env`:

```text
TELEGRAM_BOT_TOKEN=123456:ABC...
```

Important `.env` settings:

```text
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_FALLBACK_MODEL=mistral
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest
WHISPER_MODEL=base
ALLOW_IMAGE_EXTERNAL_FALLBACK=true
```

## Run

Run the Telegram bot:

```powershell
python main.py bot
```

Ask from terminal:

```powershell
python main.py ask "What do we know about Green Valley?"
```

Ingest files already placed in `data/`:

```powershell
python main.py ingest
```

## Project Structure

```text
bot/
  telegram_bot.py        Telegram handlers and orchestration.

llm/
  ollama_client.py       Local Ollama chat client and model selection.

rag/
  knowledge_base.py      File loaders, ChromaDB ingestion, tenant collections.
  pipeline.py            RAG-first answer pipeline.

voice/
  transcriber.py         Telegram OGG to WAV conversion and Whisper transcription.

docs/
  document_ops.py        DOCX, XLSX, PDF, TXT generation and editing.

images/
  generator.py           Local Stable Diffusion hook and Pollinations fallback.

utils/
  config.py              Loads .env and creates runtime directories.
  doctor.py              Environment/system checker.
  intents.py             Message intent detection and helper parsing.
  storage.py             JSON storage, chat memory, task and tenant helpers.

data/
  .gitkeep               Keeps folder in Git.
  *.json                 Runtime memory/tasks/logs, ignored by Git.

workspace/
  chroma/                Local ChromaDB vector database, ignored by Git.
  uploads/               Telegram uploaded files and voice notes, ignored by Git.
  generated/             Generated docs/images/edited files, ignored by Git.

autonova/
  Older Phase 1 implementation kept for reference.

main.py                  Main CLI entrypoint.
run.py                   Compatibility wrapper to main.py.
requirements.txt         Python dependencies.
.env.example             Safe config template.
.env                     Local secrets, ignored by Git.
```

## Company Workspaces

Each Telegram chat gets its own workspace automatically:

```text
telegram_<chat_id>
```

Set a company name:

```text
/company AutoNova Realty
```

This creates a workspace ID such as:

```text
autonova_realty
```

That workspace is used for:

- company knowledge base collection
- recent chat memory
- last generated document/image context
- uploaded file context

## Business Knowledge Workflow

Companies can upload files like:

- property listings
- contacts
- pricing sheets
- SOPs
- FAQs
- agreements and templates
- Excel inventories

Upload a supported file on Telegram with caption:

```text
ingest this into knowledge base
```

Supported knowledge ingestion formats:

- `.txt`
- `.md`
- `.pdf`
- `.docx`
- `.xlsx`

The file is stored under `workspace/uploads/`, split into chunks, embedded with Ollama embeddings, and stored in ChromaDB under that company workspace collection.

When the user asks a question, the assistant:

1. Loads recent chat memory.
2. Searches that company workspace in ChromaDB.
3. If relevant company context exists, sends it to Ollama first.
4. Otherwise falls back to direct local LLM answering.

Knowledge base always has priority over general model knowledge.

## Conversation Memory

The bot stores recent message history per chat in:

```text
data/conversation_state.json
```

This helps with follow-up requests such as:

```text
generate a 2BHK blueprint
mark the bedroom and bathroom
make the kitchen bigger
```

It also helps business conversations where the user says:

```text
use the same buyer name
update that document
what about the last property?
```

Memory is lightweight JSON, not a full database yet.

## Telegram Capabilities

Text examples:

```text
What is the price of Green Valley Residency?
Draft a sales deed for buyer Rahul and seller Priya
Calculate 1200000 * 2%
Remind me to call the buyer tomorrow
Remember: Green Valley tower B has 4 units left
Generate an image of a luxury apartment banner
```

Voice:

1. Telegram voice note is downloaded as `.ogg`.
2. FFmpeg converts it to `.wav`.
3. Whisper transcribes locally.
4. The text goes through the same assistant pipeline.

Images:

- Natural prompts are detected.
- Local Stable Diffusion is used if configured.
- Otherwise Pollinations fallback is used when enabled.
- Generated images are saved to `workspace/generated/` and sent back as Telegram photos.

## Document Editing Workflow

Upload a file to Telegram with a caption describing the edit.

### DOCX

Supported direct edits:

```text
replace old clause with new clause
add paragraph: Payment due within 7 days.
update deed with buyer name Rahul Sharma and seller name Priya Mehta
```

The DOCX editor handles common template placeholders:

```text
[BUYER NAME]
[SELLER NAME]
{{BUYER_NAME}}
{{SELLER_NAME}}
Buyer Name
Seller Name
Name of Buyer
Name of Seller
```

If placeholders are not found, the bot uses local Ollama to rewrite the extracted DOCX text into a new edited DOCX.

### XLSX

Supported spreadsheet instructions:

```text
update column price +10%
set B2 = 5000
formula E2 = SUM(B2:D2)
mark all rows as reviewed
```

The edited spreadsheet is saved to `workspace/generated/` and returned on Telegram.

### PDF

PDFs are not edited in place. The bot extracts readable text, applies the instruction through the LLM, and creates a new generated PDF.

Example:

```text
update buyer name to Rahul Sharma and seller name to Priya Mehta
```

## Document Generation

For natural drafting requests:

```text
draft a rental agreement for Green Valley Residency
prepare a sales proposal for buyer Rahul
write a report on available inventory
```

The bot retrieves company knowledge, asks Ollama to draft the document, and returns:

- `.txt`
- `.docx`
- `.pdf`

## Runtime Data and File Handling

Ignored local runtime files:

```text
.env
.venv/
data/*.json
data/*.jsonl
workspace/chroma/
workspace/generated/
workspace/uploads/
```

These are intentionally not committed because they may contain:

- Telegram token
- company data
- uploaded documents
- generated legal/business files
- local vector DB
- chat history

## Security Model

- LLM responses use local Ollama.
- Embeddings use local Ollama.
- Voice transcription uses local Whisper.
- Company data stays local by default.
- `.env` is ignored by Git.
- Pollinations image fallback is external and should only be enabled if acceptable.

## Current Limitations

- DOCX formatting may not be perfectly preserved during full LLM rewrite fallback.
- PDF editing creates a new PDF from extracted text instead of modifying the original layout.
- Memory is lightweight JSON, not robust multi-user auth.
- Telegram chat ID is currently the session boundary.
- XLSX edits support common operations, not arbitrary spreadsheet transformations yet.
- Third-party real estate platform integrations are not implemented yet.

## Test Commands

```powershell
python main.py doctor
python main.py ingest
python main.py ask "hello"
python -m compileall bot llm rag voice docs images utils main.py
```

## Git Notes

The first committed version is:

```text
FIRST DRAFT
```

Local runtime files are excluded by `.gitignore`.
