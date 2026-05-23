# Local AI Assistant

Production-ready local assistant for Telegram, Ollama, ChromaDB RAG, Whisper voice transcription, document editing, and optional image generation.

## System Requirements

- Python 3.10 or newer, recommended 3.11
- FFmpeg on PATH
- Ollama installed and running
- Ollama model: `llama3.2:latest` or `mistral`
- Ollama embedding model: `mxbai-embed-large:latest`

Check everything:

```powershell
py -3.11 main.py doctor
```

If the doctor reports missing dependencies, run the exact commands it prints.

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set your Telegram token in `.env`:

```text
TELEGRAM_BOT_TOKEN=123456:ABC...
```

## Knowledge Base

Put `.txt`, `.md`, `.pdf`, or `.docx` files in `data/`, then ingest:

```powershell
python main.py ingest
```

Knowledge base context always has priority. If relevant context is found in ChromaDB, it is sent to Ollama before the user query. If not, the assistant falls back to direct local LLM answering.

## Run

Ask locally:

```powershell
python main.py ask "What do we know about the uploaded documents?"
```

Run Telegram bot:

```powershell
python main.py bot
```

Telegram supports:

- Text messages
- Voice messages through FFmpeg + local Whisper
- File uploads for `.docx` and `.xlsx`
- Edited file replies
- Natural image prompts like `generate an image of a car`
- Natural document prompts like `draft an agreement for buyer...`
- Calculations and reminders/tasks

## Document Commands

Examples as Telegram captions when uploading files:

```text
update column price +10%
formula E2 = SUM(B2:D2)
```

DOCX uploads are copied into a generated edited DOCX with the instruction appended.

## Images

The system first tries local Stable Diffusion if `STABLE_DIFFUSION_MODEL` is configured. External image fallback is disabled by default.

To allow Pollinations fallback:

```text
ALLOW_IMAGE_EXTERNAL_FALLBACK=true
```

## Test Commands

```powershell
python main.py doctor
python main.py ingest
python main.py ask "hello"
python -m compileall bot llm rag voice docs images utils main.py
```
