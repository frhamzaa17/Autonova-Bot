# Phase 2 Cost & Stack Recommendation

## Recommended Production Stack

| Layer | Phase 1 | Phase 2 Recommended | Why |
| --- | --- | --- | --- |
| Telegram Bot | Python long polling | Python webhook behind HTTPS | More reliable and production friendly. |
| LLM | Local/demo rule engine, Ollama-ready | Ollama on private GPU/VPS or privacy-controlled API | Keeps sensitive business context controlled. |
| RAG Store | JSON keyword search | ChromaDB or PostgreSQL + pgvector | Better retrieval, metadata filters, backups. |
| Documents | TXT/DOCX/CSV helpers | python-docx, openpyxl, LibreOffice headless | Real Word, Excel, and PDF conversion support. |
| Voice | Placeholder | Local Whisper or faster-whisper | Voice notes remain private. |
| Images | Pollinations link | Local Stable Diffusion or approved paid image API | Better output control and privacy policy review. |
| Dashboard | Stdlib web dashboard | FastAPI + React/Next.js | Stronger auth, file management, analytics. |
| Hosting | Local machine | Private VPS or client-owned cloud | More reliable uptime and backups. |

## Estimated Monthly Costs

| Option | Estimate | Trade-off |
| --- | ---: | --- |
| Local office PC with Ollama | INR 0 infra, hardware owned | Low recurring cost, uptime depends on machine. |
| VPS CPU-only | INR 800-3000 | Good for bot/dashboard, weak for local LLM. |
| GPU cloud for local LLM | INR 8000-50000+ | Private inference but higher cost. |
| Privacy-safe hosted LLM API | Usage-based | Faster setup, requires data-processing review. |
| Managed database/backups | INR 1000-5000 | Worth it for production reliability. |

## Production Priorities

1. Add authentication to dashboard.
2. Move logs and knowledge base to PostgreSQL.
3. Add real document processing packages.
4. Add local Whisper transcription.
5. Create backup and audit log policies.
6. Confirm official portal integration access before building portal automation.

## Recommendation

For the client handover, use a private VPS for the bot/dashboard/database and either a client-owned local GPU machine or a vetted privacy-safe LLM API. Keep all property documents, contacts, and conversations in the client-controlled database with encrypted backups.

