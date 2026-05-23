from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from docs.document_ops import create_docx, create_document_bundle, process_uploaded_document, read_pdf_text
from images.generator import generate_image
from llm.ollama_client import generate_response
from rag.knowledge_base import retrieve_context
from rag.pipeline import answer_query
from utils.config import Settings, load_settings
from utils.intents import (
    calculate,
    classify,
    document_prompt,
    image_followup_prompt,
    image_prompt,
    improve_image_prompt,
    knowledge_text,
)
from utils.storage import add_knowledge, add_task, get_chat_state, update_chat_state
from voice.transcriber import transcribe_audio


def _allowed(update: Update, settings: Settings) -> bool:
    if not settings.allowed_telegram_user_ids:
        return True
    user = update.effective_user
    return bool(user and user.id in settings.allowed_telegram_user_ids)


async def _reject_if_needed(update: Update, settings: Settings) -> bool:
    if _allowed(update, settings):
        return False
    if update.message:
        await update.message.reply_text("You are not allowed to use this bot.")
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    await update.message.reply_text("Local assistant is ready.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id
    intent = classify(text)

    if intent == "image":
        prompt = improve_image_prompt(image_prompt(text))
        try:
            output = Path(generate_image(prompt))
        except Exception as exc:
            await update.message.reply_text(f"Image generation failed: {exc}")
            return
        update_chat_state(
            chat_id,
            {
                "last_deliverable_type": "image",
                "last_image_prompt": prompt,
                "last_image_path": str(output),
            },
        )
        with output.open("rb") as image_file:
            await update.message.reply_photo(photo=image_file)
        return

    if intent == "image_followup":
        state = get_chat_state(chat_id)
        last_prompt = state.get("last_image_prompt")
        if last_prompt:
            prompt = image_followup_prompt(last_prompt, text)
            try:
                output = Path(generate_image(prompt))
            except Exception as exc:
                await update.message.reply_text(f"Image update failed: {exc}")
                return
            update_chat_state(
                chat_id,
                {
                    "last_deliverable_type": "image",
                    "last_image_prompt": prompt,
                    "last_image_path": str(output),
                },
            )
            await update.message.reply_text("Updated the previous image request with your changes.")
            with output.open("rb") as image_file:
                await update.message.reply_photo(photo=image_file)
            return
        await update.message.reply_text("I do not have a previous image in this chat to update. Send the full image request once, then ask for changes.")
        return

    if text.lower().startswith("docx "):
        output = create_docx(text[5:].strip())
        update_chat_state(chat_id, {"last_deliverable_type": "document", "last_document_path": str(output)})
        with output.open("rb") as document_file:
            await update.message.reply_document(document=document_file, filename=output.name)
        return

    if intent == "document":
        prompt = document_prompt(text)
        context_text, has_context = retrieve_context(prompt)
        draft = generate_response(
            f"Draft a polished business document for this request:\n{prompt}",
            context_text if has_context else None,
        )
        files = create_document_bundle(draft, "telegram_draft")
        update_chat_state(
            chat_id,
            {
                "last_deliverable_type": "document",
                "last_document_prompt": prompt,
                "last_document_path": str(files[-1]),
            },
        )
        await update.message.reply_text("Draft created. Review business/legal details before use.")
        for file_path in files:
            with file_path.open("rb") as document_file:
                await update.message.reply_document(document=document_file, filename=file_path.name)
        return

    if intent == "calculation":
        try:
            await update.message.reply_text(calculate(text))
        except Exception as exc:
            await update.message.reply_text(f"Calculation failed: {exc}")
        return

    if intent == "task":
        task = add_task(text, "telegram")
        await update.message.reply_text(f"Task captured as #{task['id']}: {task['text']}")
        return

    if intent == "knowledge":
        entry = add_knowledge(knowledge_text(text), "telegram")
        await update.message.reply_text(f"Saved knowledge note #{entry['id']}.")
        return

    response = answer_query(text)
    await update.message.reply_text(response[:4096])


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    voice = update.message.voice
    tg_file = await context.bot.get_file(voice.file_id)
    ogg_path = settings.uploads_dir / f"{voice.file_unique_id}.ogg"
    await tg_file.download_to_drive(str(ogg_path))
    text = transcribe_audio(ogg_path)
    if classify(text) == "image":
        prompt = improve_image_prompt(image_prompt(text))
        output = Path(generate_image(prompt))
        update_chat_state(
            update.effective_chat.id,
            {
                "last_deliverable_type": "image",
                "last_image_prompt": prompt,
                "last_image_path": str(output),
            },
        )
        with output.open("rb") as image_file:
            await update.message.reply_photo(photo=image_file)
        return
    response = answer_query(text)
    await update.message.reply_text(f"Transcribed: {text}\n\n{response}"[:4096])


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    document = update.message.document
    tg_file = await context.bot.get_file(document.file_id)
    path = settings.uploads_dir / Path(document.file_name).name
    await tg_file.download_to_drive(str(path))
    instruction = update.message.caption or "Process this document"
    edited = process_uploaded_document(path, instruction)
    if edited:
        with edited.open("rb") as document_file:
            await update.message.reply_document(document=document_file, filename=edited.name)
    elif path.suffix.lower() == ".pdf":
        pdf_text = read_pdf_text(path)
        if not pdf_text:
            await update.message.reply_text("PDF saved locally, but no readable text was found.")
            return
        answer = generate_response(instruction, f"Uploaded PDF text from {path.name}:\n{pdf_text}")
        await update.message.reply_text(answer[:4096])
    else:
        await update.message.reply_text("File saved locally. Supported edit formats: .docx and .xlsx.")


def run_bot() -> None:
    settings = load_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env before running the bot.")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
