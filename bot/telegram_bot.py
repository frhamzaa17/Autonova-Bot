from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from docs.document_ops import create_docx, create_document_bundle, process_uploaded_document, read_pdf_text
from images.generator import generate_image
from llm.ollama_client import generate_response
from rag.knowledge_base import ingest_file, retrieve_context
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
from utils.storage import (
    add_knowledge,
    add_task,
    append_chat_history,
    conversation_context,
    get_chat_state,
    set_tenant_for_chat,
    tenant_for_chat,
    update_chat_state,
)
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
    chat_id = update.effective_chat.id
    tenant_id = tenant_for_chat(chat_id)
    await update.message.reply_text(
        "Local business assistant is ready.\n"
        f"Workspace: {tenant_id}\n"
        "Use /company Your Company Name to separate this chat's business knowledge."
    )


async def company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("Usage: /company Your Company Name")
        return
    state = set_tenant_for_chat(update.effective_chat.id, name)
    await update.message.reply_text(f"Company workspace set to: {state['tenant_id']}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id
    tenant_id = tenant_for_chat(chat_id)
    memory = conversation_context(chat_id)
    intent = classify(text)
    append_chat_history(chat_id, "user", text)

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
        append_chat_history(chat_id, "assistant", f"Generated image: {prompt}")
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
            append_chat_history(chat_id, "assistant", f"Updated image: {prompt}")
            return
        await update.message.reply_text("I do not have a previous image in this chat to update. Send the full image request once, then ask for changes.")
        return

    if text.lower().startswith("docx "):
        output = create_docx(text[5:].strip())
        update_chat_state(chat_id, {"last_deliverable_type": "document", "last_document_path": str(output)})
        with output.open("rb") as document_file:
            await update.message.reply_document(document=document_file, filename=output.name)
        append_chat_history(chat_id, "assistant", f"Created DOCX: {output.name}")
        return

    if intent == "document":
        prompt = document_prompt(text)
        context_text, has_context = retrieve_context(prompt, tenant_id=tenant_id)
        combined_context = "\n\n".join(part for part in [f"Recent conversation:\n{memory}" if memory else "", context_text if has_context else ""] if part)
        draft = generate_response(
            f"Draft a polished business document for this request:\n{prompt}",
            combined_context or None,
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
        append_chat_history(chat_id, "assistant", f"Drafted document bundle for: {prompt}")
        return

    if intent == "calculation":
        try:
            result = calculate(text)
            await update.message.reply_text(result)
            append_chat_history(chat_id, "assistant", result)
        except Exception as exc:
            await update.message.reply_text(f"Calculation failed: {exc}")
        return

    if intent == "task":
        task = add_task(text, "telegram")
        await update.message.reply_text(f"Task captured as #{task['id']}: {task['text']}")
        append_chat_history(chat_id, "assistant", f"Task captured as #{task['id']}")
        return

    if intent == "knowledge":
        entry = add_knowledge(knowledge_text(text), "telegram")
        await update.message.reply_text(f"Saved knowledge note #{entry['id']}.")
        append_chat_history(chat_id, "assistant", f"Saved knowledge note #{entry['id']}")
        return

    response = answer_query(text, tenant_id=tenant_id, memory=memory)
    await update.message.reply_text(response[:4096])
    append_chat_history(chat_id, "assistant", response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    voice = update.message.voice
    tg_file = await context.bot.get_file(voice.file_id)
    ogg_path = settings.uploads_dir / f"{voice.file_unique_id}.ogg"
    await tg_file.download_to_drive(str(ogg_path))
    text = transcribe_audio(ogg_path)
    chat_id = update.effective_chat.id
    tenant_id = tenant_for_chat(chat_id)
    append_chat_history(chat_id, "user", text)
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
        append_chat_history(chat_id, "assistant", f"Generated image from voice: {prompt}")
        return
    response = answer_query(text, tenant_id=tenant_id, memory=conversation_context(chat_id))
    await update.message.reply_text(f"Transcribed: {text}\n\n{response}"[:4096])
    append_chat_history(chat_id, "assistant", response)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    document = update.message.document
    tg_file = await context.bot.get_file(document.file_id)
    path = settings.uploads_dir / Path(document.file_name).name
    await tg_file.download_to_drive(str(path))
    instruction = update.message.caption or "Process this document"
    chat_id = update.effective_chat.id
    tenant_id = tenant_for_chat(chat_id)
    append_chat_history(chat_id, "user", f"Uploaded {path.name} with instruction: {instruction}")

    wants_ingest = any(word in instruction.lower() for word in ("ingest", "learn", "remember", "knowledge", "kb", "store", "save this"))
    if wants_ingest:
        chunks = ingest_file(path, tenant_id)
        update_chat_state(chat_id, {"last_uploaded_file": str(path), "last_deliverable_type": "knowledge_file"})
        message = f"Ingested {chunks} knowledge chunks into workspace {tenant_id}."
        await update.message.reply_text(message)
        append_chat_history(chat_id, "assistant", message)
        return

    revised_text = None
    if path.suffix.lower() == ".pdf":
        pdf_text = read_pdf_text(path)
        if not pdf_text:
            await update.message.reply_text("PDF saved locally, but no readable text was found.")
            return
        revised_text = generate_response(
            f"Rewrite or edit this PDF text according to the instruction. Return only the revised document text.\nInstruction: {instruction}",
            f"PDF file: {path.name}\n\n{pdf_text}",
        )

    edited = process_uploaded_document(path, instruction, revised_text=revised_text)
    if edited:
        update_chat_state(chat_id, {"last_uploaded_file": str(path), "last_document_path": str(edited), "last_deliverable_type": "document"})
        with edited.open("rb") as document_file:
            await update.message.reply_document(document=document_file, filename=edited.name)
        append_chat_history(chat_id, "assistant", f"Edited and returned file: {edited.name}")
    elif path.suffix.lower() == ".pdf":
        answer = generate_response(instruction, f"Uploaded PDF text from {path.name}:\n{read_pdf_text(path)}")
        await update.message.reply_text(answer[:4096])
        append_chat_history(chat_id, "assistant", answer)
    else:
        chunks = ingest_file(path, tenant_id)
        await update.message.reply_text(f"File saved locally. I also ingested {chunks} chunks if the format was supported.")


def run_bot() -> None:
    settings = load_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env before running the bot.")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("company", company))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
