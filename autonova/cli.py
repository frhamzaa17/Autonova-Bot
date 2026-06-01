from __future__ import annotations

import argparse

from .assistant import Assistant
from .config import TELEGRAM_TOKEN, ensure_directories
from .llm import ollama_status
from .telegram_bot import TelegramBot


def main() -> None:
    ensure_directories()
    parser = argparse.ArgumentParser(description="AutoNova Phase 1 assistant")
    sub = parser.add_subparsers(dest="command")
    dashboard = sub.add_parser("dashboard", help="Run secure web dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)
    sub.add_parser("bot", help="Run Telegram bot")
    sub.add_parser("doctor", help="Check LLM and Telegram configuration")
    once = sub.add_parser("once", help="Send one local test message")
    once.add_argument("message")
    args = parser.parse_args()

    if args.command == "bot":
        TelegramBot().run()
    elif args.command == "doctor":
        llm = ollama_status()
        print("LLM/Ollama:")
        print(f"  URL: {llm.get('url')}")
        print(f"  Model: {llm.get('model')}")
        print(f"  Available: {llm.get('available')}")
        if llm.get("models") is not None:
            print(f"  Installed models: {', '.join(llm.get('models') or [])}")
        if llm.get("error"):
            print(f"  Error: {llm.get('error')}")
        print("Telegram:")
        print(f"  Token configured: {bool(TELEGRAM_TOKEN)}")
        if not TELEGRAM_TOKEN:
            print("  Add TELEGRAM_BOT_TOKEN to run the real Telegram bot.")
    elif args.command == "once":
        result = Assistant().handle(args.message, source="cli")
        print(result["text"])
        for url in result.get("images", []):
            print(url)
        for path in result.get("files", []):
            print(path)
    else:
        from dashboard.server import run_dashboard

        run_dashboard(args.host, args.port)
