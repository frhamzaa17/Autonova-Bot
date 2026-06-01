from __future__ import annotations

import argparse
import sys

from utils.config import load_settings
from utils.doctor import run_doctor


def doctor_or_stop() -> None:
    settings = load_settings()
    result = run_doctor(settings)
    print("\n".join(result.lines))
    if result.ok:
        return
    print("\nMissing dependencies. Run:")
    for command in dict.fromkeys(result.missing_commands):
        print(f"  {command}")
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local AI assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("ingest")
    structure_parser = sub.add_parser("structure")
    structure_parser.add_argument("--tenant", default=None)
    ask_parser = sub.add_parser("ask")
    ask_parser.add_argument("query", nargs="+")
    sub.add_parser("bot")
    dashboard_parser = sub.add_parser("dashboard")
    dashboard_parser.add_argument("--host", default="127.0.0.1")
    dashboard_parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.command == "doctor":
        doctor_or_stop()
    elif args.command == "ingest":
        doctor_or_stop()
        from rag.knowledge_base import ingest_data_folder

        count = ingest_data_folder()
        print(f"Ingested {count} chunks into local ChromaDB.")
    elif args.command == "structure":
        from rag.structured_store import structure_existing_files

        count = structure_existing_files(args.tenant)
        print(f"Decoded {count} file(s) into the structured knowledge base.")
    elif args.command == "ask":
        doctor_or_stop()
        from rag.pipeline import answer_query

        print(answer_query(" ".join(args.query)))
    elif args.command == "bot":
        doctor_or_stop()
        from bot.telegram_bot import run_bot

        run_bot()
    elif args.command == "dashboard":
        from dashboard.server import run_dashboard

        run_dashboard(args.host, args.port)
    else:
        parser.print_help()
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
