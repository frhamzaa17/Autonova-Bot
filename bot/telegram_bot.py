from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from docs.document_actions import perform_document_action
from docs.document_ops import create_docx, create_document_bundle, process_uploaded_document, read_pdf_text
from images.generator import generate_image
from llm.ollama_client import generate_response
from rag.knowledge_base import clear_knowledge_base, ingest_file, knowledge_summary, remove_knowledge_file, retrieve_context
from rag.pipeline import answer_query
from rag.document_workflows import create_source_document_bundle, wants_source_document_bundle
from rag.question_classifier import (
    create_important_questions_bundle,
    create_question_classification_bundle,
    wants_important_questions_document,
    wants_question_classification_document,
)
from utils.config import Settings, load_settings, safe_workspace_id, tenant_uploads_dir
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
    now_iso,
    read_json,
    set_tenant_for_chat,
    tenant_for_chat,
    update_chat_state,
    write_json,
)
from voice.transcriber import transcribe_audio


INGEST_WORDS = (
    "ingest",
    "learn",
    "remember",
    "knowledge",
    "kb",
    "store",
    "save this",
    "save these",
    "save them",
    "business details",
    "company details",
)

EDIT_WORDS = (
    "edit",
    "rewrite",
    "revise",
    "update",
    "replace",
    "change",
    "modify",
    "correct",
    "fill",
    "add paragraph",
    "set ",
    "formula",
    "mark ",
)

DASHBOARD_USERS_FILE = "dashboard_users.json"


def _dashboard_users() -> list[dict]:
    return read_json(DASHBOARD_USERS_FILE, [])


def _save_dashboard_users(users: list[dict]) -> None:
    write_json(DASHBOARD_USERS_FILE, users)


def _dashboard_user_for_telegram(user_id: int | None) -> dict | None:
    if user_id is None:
        return None
    return next(
        (
            user
            for user in _dashboard_users()
            if user.get("role") == "user"
            and user.get("status") == "active"
            and str(user.get("telegram_user_id", "")) == str(user_id)
        ),
        None,
    )


def _dashboard_user_for_workspace(workspace: str) -> dict | None:
    safe = workspace.lower()
    return next(
        (
            user
            for user in _dashboard_users()
            if user.get("role") == "user"
            and user.get("status") == "active"
            and str(user.get("workspace", "")).lower() == safe
        ),
        None,
    )


def _link_dashboard_user(code: str, update: Update) -> dict | None:
    users = _dashboard_users()
    normalized = code.strip()
    for user in users:
        if user.get("role") != "user" or user.get("status") != "active":
            continue
        if not user.get("telegram_link_code") or user.get("telegram_link_code") != normalized:
            continue
        tg_user = update.effective_user
        user["telegram_user_id"] = tg_user.id if tg_user else ""
        user["telegram_username"] = tg_user.username if tg_user else ""
        user["telegram_chat_id"] = update.effective_chat.id
        user["telegram_linked_at"] = now_iso()
        _save_dashboard_users(users)
        return user
    return None


def _public_reply(text: str) -> str:
    cleaned_lines = []
    skip_json_record = False
    skip_source_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if skip_source_section:
            if not stripped:
                skip_source_section = False
            continue
        if re.match(r"^(source rows used)\s*:", stripped, flags=re.I):
            skip_source_section = True
            continue
        if re.match(r"^(source)\s*:", stripped, flags=re.I):
            skip_json_record = True
            continue
        if re.search(r"\bknowledge base context\b.*\brecord\b", stripped, flags=re.I):
            continue
        if re.search(r"[A-Za-z]:\\Users\\", stripped):
            continue
        if stripped.startswith(("Record: {", "- Record #")):
            skip_json_record = True
            continue
        if skip_json_record and ("source_file" in stripped or stripped.startswith(("{", '"source_file"', "- Answer Key:"))):
            continue
        cleaned_lines.append(line)
        skip_json_record = False
    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r'\{[^{}]*"source_file"\s*:\s*"[^"]+"[^{}]*\}', "", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip() or text


def _allowed(update: Update, settings: Settings) -> bool:
    if not settings.allowed_telegram_user_ids:
        return True
    user = update.effective_user
    return bool(user and (user.id in settings.allowed_telegram_user_ids or _dashboard_user_for_telegram(user.id)))


async def _reject_if_needed(update: Update, settings: Settings) -> bool:
    if _allowed(update, settings):
        return False
    if update.message:
        await update.message.reply_text("You are not allowed to use this bot.")
    return True


async def _reject_claimed_workspace(update: Update, tenant_id: str) -> bool:
    claimed_by = _dashboard_user_for_workspace(tenant_id)
    if not claimed_by:
        return False
    tg_user = update.effective_user
    if tg_user and str(claimed_by.get("telegram_user_id", "")) == str(tg_user.id):
        return False
    if update.message:
        await update.message.reply_text(
            "This company workspace is protected by a dashboard account. "
            "Open that company dashboard and send its Telegram link command here, for example: /link CODE"
        )
    return True


def _wants_knowledge_ingest(instruction: str) -> bool:
    lower = instruction.lower()
    return any(word in lower for word in INGEST_WORDS)


def _recent_upload_mode(chat_id: int, minutes: int = 10) -> str | None:
    state = get_chat_state(chat_id)
    if state.get("last_upload_mode") != "knowledge":
        return None
    try:
        updated_at = datetime.fromisoformat(state.get("updated_at", ""))
    except ValueError:
        return None
    age = datetime.now() - updated_at
    if age.total_seconds() <= minutes * 60:
        return "knowledge"
    return None


def _wants_document_edit(instruction: str) -> bool:
    lower = instruction.lower()
    return any(word in lower for word in EDIT_WORDS)


def _ingest_safely(path: Path, tenant_id: str) -> tuple[int, str | None]:
    try:
        return ingest_file(path, tenant_id), None
    except Exception as exc:
        return 0, str(exc)


def _structure_safely(path: Path, tenant_id: str) -> str | None:
    try:
        from rag.structured_store import upsert_document

        upsert_document(path, tenant_id)
        return None
    except Exception as exc:
        return str(exc)


def _extract_remove_selector(text: str) -> str:
    quoted = re.search(r"[\"']([^\"']+)[\"']", text)
    if quoted:
        return quoted.group(1).strip()
    cleaned = re.sub(
        r"\b(remove|delete|forget|clear)\b|\b(from|in)\s+(my\s+)?knowledge\s+base\b|\bknowledge\s+base\b|\bfile\b",
        "",
        text,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-")
    return cleaned


def _knowledge_management_response(text: str, tenant_id: str) -> str | None:
    lower = text.lower()
    mentions_kb = re.search(r"\b(knowledge\s+base|kb|uploaded\s+files?|saved\s+files?)\b", lower)
    if re.search(r"\b(how many|count|list|show)\b", lower) and mentions_kb:
        return knowledge_summary(tenant_id)
    if re.search(r"\b(clear|delete all|remove all|reset|empty)\b", lower) and mentions_kb:
        result = clear_knowledge_base(tenant_id)
        return (
            f"Knowledge base cleared for this workspace. "
            f"Removed {len(result.removed_files)} file(s) and {result.structured_removed} structured document record(s)."
        )
    if re.search(r"\b(remove|delete|forget)\b", lower) and mentions_kb:
        selector = _extract_remove_selector(text)
        if not selector:
            return "Tell me which file to remove, for example: remove Quiz.pdf from knowledge base."
        result = remove_knowledge_file(selector, tenant_id)
        if not result.removed_files and result.structured_removed == 0:
            return f"I could not find a knowledge-base file matching: {selector}"
        names = ", ".join(path.name for path in result.removed_files) or selector
        return (
            f"Removed {names} from this workspace's knowledge base. "
            f"Structured records removed: {result.structured_removed}."
        )
    return None


async def _send_document_bundle(update: Update, chat_id: int, text: str, summary: str, files: list[Path]) -> None:
    update_chat_state(
        chat_id,
        {
            "last_deliverable_type": "document",
            "last_document_prompt": text,
            "last_document_path": str(files[-1]),
        },
    )
    await update.message.reply_text(summary)
    for file_path in files:
        with file_path.open("rb") as document_file:
            await update.message.reply_document(document=document_file, filename=file_path.name)
    append_chat_history(chat_id, "assistant", summary)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    chat_id = update.effective_chat.id
    tenant_id = tenant_for_chat(chat_id)
    await update.message.reply_text(
        "Local business assistant is ready.\n"
        f"Workspace: {tenant_id}\n"
        "Use /company Your Company Name for a local workspace, or /link CODE from the dashboard to connect a registered company."
    )


async def link_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    code = " ".join(context.args).strip()
    if not code:
        await update.message.reply_text("Usage: /link CODE from your company dashboard.")
        return
    user = _link_dashboard_user(code, update)
    if not user:
        await update.message.reply_text("Invalid or expired dashboard link code.")
        return
    update_chat_state(
        update.effective_chat.id,
        {
            "tenant_id": user.get("workspace"),
            "company_name": user.get("company_name"),
            "dashboard_user_id": user.get("id"),
        },
    )
    await update.message.reply_text(
        f"Telegram is linked to {user.get('company_name')}.\n"
        f"Workspace: {user.get('workspace')}\n"
        "Uploads and questions here now use the same dashboard workspace."
    )


async def company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("Usage: /company Your Company Name")
        return
    requested = safe_workspace_id(name)
    claimed_by = _dashboard_user_for_workspace(requested)
    if claimed_by:
        tg_user = update.effective_user
        if not tg_user or str(claimed_by.get("telegram_user_id", "")) != str(tg_user.id):
            await update.message.reply_text(
                "That company is registered in the dashboard. Use the dashboard Telegram link command instead: /link CODE"
            )
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
    if await _reject_claimed_workspace(update, tenant_id):
        return
    memory = conversation_context(chat_id)
    intent = classify(text)
    append_chat_history(chat_id, "user", text)

    knowledge_management = _knowledge_management_response(text, tenant_id)
    if knowledge_management:
        await update.message.reply_text(_public_reply(knowledge_management))
        append_chat_history(chat_id, "assistant", knowledge_management)
        return

    if wants_question_classification_document(text):
        result = create_question_classification_bundle(
            text,
            tenant_id,
            preferred_file=get_chat_state(chat_id).get("last_uploaded_file"),
        )
        if result:
            summary, files = result
            await _send_document_bundle(update, chat_id, text, summary, files)
            return

    if wants_important_questions_document(text):
        result = create_important_questions_bundle(
            text,
            tenant_id,
            preferred_file=get_chat_state(chat_id).get("last_uploaded_file"),
        )
        if result:
            summary, files = result
            await _send_document_bundle(update, chat_id, text, summary, files)
            return

    state = get_chat_state(chat_id)
    preferred_file = state.get("last_uploaded_file")
    if wants_source_document_bundle(text, preferred_file=preferred_file):
        result = create_source_document_bundle(text, tenant_id, preferred_file=preferred_file)
        if result:
            summary, files = result
            await _send_document_bundle(update, chat_id, text, summary, files)
            return

    try:
        document_action = perform_document_action(text, get_chat_state(chat_id), tenant_id)
    except Exception as exc:
        await update.message.reply_text(f"I could not complete the document action: {exc}")
        append_chat_history(chat_id, "assistant", f"Document action failed: {exc}")
        return

    if document_action:
        state_updates = {"last_deliverable_type": "document", "last_upload_mode": "document_edit"}
        if document_action.files:
            state_updates["last_document_path"] = str(document_action.files[-1])
        update_chat_state(
            chat_id,
            state_updates,
        )
        if document_action.ingest_error:
            await update.message.reply_text(_public_reply(f"{document_action.summary}\nKnowledge re-ingestion failed: {document_action.ingest_error}"))
        elif document_action.ingested_chunks is not None:
            await update.message.reply_text(_public_reply(f"{document_action.summary}\nI have saved the updated version for future questions."))
        else:
            await update.message.reply_text(_public_reply(document_action.summary))
        for output in document_action.files:
            with output.open("rb") as document_file:
                await update.message.reply_document(document=document_file, filename=output.name)
        append_chat_history(chat_id, "assistant", document_action.summary)
        return

    if intent == "image":
        prompt = improve_image_prompt(image_prompt(text))
        try:
            output = Path(generate_image(prompt, tenant_id=tenant_id))
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
                output = Path(generate_image(prompt, tenant_id=tenant_id))
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
        output = create_docx(text[5:].strip(), tenant_id=tenant_id)
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
        files = create_document_bundle(draft, "telegram_draft", tenant_id)
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
            await update.message.reply_text(_public_reply(result))
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

    response = answer_query(text, tenant_id=tenant_id, memory=memory, preferred_file=get_chat_state(chat_id).get("last_uploaded_file"))
    await update.message.reply_text(_public_reply(response)[:4096])
    append_chat_history(chat_id, "assistant", response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    voice = update.message.voice
    tg_file = await context.bot.get_file(voice.file_id)
    chat_id = update.effective_chat.id
    tenant_id = tenant_for_chat(chat_id)
    if await _reject_claimed_workspace(update, tenant_id):
        return
    ogg_path = tenant_uploads_dir(settings, tenant_id) / f"{voice.file_unique_id}.ogg"
    await tg_file.download_to_drive(str(ogg_path))
    text = transcribe_audio(ogg_path)
    append_chat_history(chat_id, "user", text)
    if classify(text) == "image":
        prompt = improve_image_prompt(image_prompt(text))
        output = Path(generate_image(prompt, tenant_id=tenant_id))
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
    response = answer_query(text, tenant_id=tenant_id, memory=conversation_context(chat_id), preferred_file=get_chat_state(chat_id).get("last_uploaded_file"))
    await update.message.reply_text(_public_reply(f"Transcribed: {text}\n\n{response}")[:4096])
    append_chat_history(chat_id, "assistant", response)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    document = update.message.document
    tg_file = await context.bot.get_file(document.file_id)
    chat_id = update.effective_chat.id
    tenant_id = tenant_for_chat(chat_id)
    if await _reject_claimed_workspace(update, tenant_id):
        return
    path = tenant_uploads_dir(settings, tenant_id) / Path(document.file_name).name
    await tg_file.download_to_drive(str(path))
    structure_error = _structure_safely(path, tenant_id)
    caption = (update.message.caption or "").strip()
    inherited_ingest = not caption and _recent_upload_mode(chat_id) == "knowledge"
    wants_ingest = _wants_knowledge_ingest(caption) or inherited_ingest
    instruction = caption or ("Save this document in the knowledge base" if wants_ingest else "Process this document")
    append_chat_history(chat_id, "user", f"Uploaded {path.name} with instruction: {instruction}")

    if wants_ingest or not _wants_document_edit(instruction):
        chunks, ingest_error = _ingest_safely(path, tenant_id)
        update_chat_state(
            chat_id,
            {
                "last_uploaded_file": str(path),
                "last_deliverable_type": "knowledge_file",
                "last_upload_mode": "knowledge",
            },
        )
        if chunks:
            message = f"{path.name} has been saved and added to the knowledge base."
        elif ingest_error:
            message = f"{path.name} has been saved, but I could not read its text clearly. {ingest_error}"
        elif structure_error:
            message = f"{path.name} has been saved, but structured conversion had an issue: {structure_error}"
        else:
            message = f"{path.name} has been saved, but I could not read its text clearly."
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

    edited = process_uploaded_document(path, instruction, revised_text=revised_text, tenant_id=tenant_id)
    if edited:
        chunks, ingest_error = _ingest_safely(edited, tenant_id)
        update_chat_state(
            chat_id,
            {
                "last_uploaded_file": str(path),
                "last_document_path": str(edited),
                "last_deliverable_type": "document",
                "last_upload_mode": "document_edit",
            },
        )
        with edited.open("rb") as document_file:
            await update.message.reply_document(document=document_file, filename=edited.name)
        if ingest_error:
            await update.message.reply_text(f"Edited file returned, but knowledge re-ingestion failed: {ingest_error}")
        elif chunks:
            await update.message.reply_text("I saved the edited version for future dashboard and knowledge-base use.")
        append_chat_history(chat_id, "assistant", f"Edited and returned file: {edited.name}")
    elif path.suffix.lower() == ".pdf":
        answer = generate_response(instruction, f"Uploaded PDF text from {path.name}:\n{read_pdf_text(path)}")
        await update.message.reply_text(_public_reply(answer)[:4096])
        append_chat_history(chat_id, "assistant", answer)
    else:
        chunks, ingest_error = _ingest_safely(path, tenant_id)
        if chunks:
            await update.message.reply_text(f"{path.name} has been saved and added to the knowledge base.")
        elif ingest_error:
            await update.message.reply_text(f"{path.name} has been saved, but I could not read its text clearly. {ingest_error}")
        else:
            await update.message.reply_text(f"{path.name} has been saved, but I could not read its text clearly.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    if await _reject_if_needed(update, settings):
        return
    chat_id = update.effective_chat.id
    tenant_id = tenant_for_chat(chat_id)
    if await _reject_claimed_workspace(update, tenant_id):
        return
    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    path = tenant_uploads_dir(settings, tenant_id) / f"{photo.file_unique_id}.jpg"
    await tg_file.download_to_drive(str(path))
    caption = (update.message.caption or "").strip()
    append_chat_history(chat_id, "user", f"Uploaded image document {path.name}" + (f" with instruction: {caption}" if caption else ""))

    chunks, ingest_error = _ingest_safely(path, tenant_id)
    update_chat_state(
        chat_id,
        {
            "last_uploaded_file": str(path),
            "last_deliverable_type": "knowledge_file",
            "last_upload_mode": "knowledge",
        },
    )
    if chunks:
        message = f"{path.name} has been saved and added to the knowledge base."
    elif ingest_error:
        message = f"{path.name} has been saved, but I could not read its text clearly. {ingest_error}"
    else:
        message = f"{path.name} has been saved, but I could not read its text clearly."
    await update.message.reply_text(message)
    append_chat_history(chat_id, "assistant", message)


def run_bot() -> None:
    settings = load_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env before running the bot.")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link_company))
    app.add_handler(CommandHandler("company", company))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
