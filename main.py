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
    ask_parser = sub.add_parser("ask")
    ask_parser.add_argument("query", nargs="+")
    sub.add_parser("bot")
    args = parser.parse_args()

    if args.command == "doctor":
        doctor_or_stop()
    elif args.command == "ingest":
        doctor_or_stop()
        from rag.knowledge_base import ingest_data_folder

        count = ingest_data_folder()
        print(f"Ingested {count} chunks into local ChromaDB.")
    elif args.command == "ask":
        doctor_or_stop()
        from rag.pipeline import answer_query

        print(answer_query(" ".join(args.query)))
    elif args.command == "bot":
        doctor_or_stop()
        from bot.telegram_bot import run_bot

        run_bot()
    else:
        parser.print_help()
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
