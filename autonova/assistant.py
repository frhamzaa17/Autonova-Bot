from __future__ import annotations

import ast
import operator
import re
from pathlib import Path
from urllib.parse import quote_plus

from docs.document_actions import perform_document_action
from .document_ops import draft_docx, draft_pdf, draft_text_document, edit_csv, edit_xlsx, extract_document_text, summarize_text_file
from .knowledge_base import KnowledgeBase
from .llm import generate_with_ollama
from .storage import add_task, append_log


OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

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
    "set ",
    "formula",
    "mark ",
)


def wants_knowledge_ingest(message: str) -> bool:
    lower = message.lower()
    return any(word in lower for word in INGEST_WORDS)


def wants_document_edit(message: str) -> bool:
    lower = message.lower()
    return any(word in lower for word in EDIT_WORDS)


def _eval_math(node):
    if isinstance(node, ast.Expression):
        return _eval_math(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval_math(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval_math(node.left), _eval_math(node.right))
    raise ValueError("Only arithmetic expressions are allowed.")


def calculate(expression: str) -> str:
    expression = expression.replace(",", "")
    tree = ast.parse(expression, mode="eval")
    result = _eval_math(tree)
    return f"{expression} = {result:,.2f}" if isinstance(result, float) else f"{expression} = {result:,}"


class Assistant:
    def __init__(self) -> None:
        self.kb = KnowledgeBase()

    def handle(self, message: str, source: str = "dashboard", attachment: Path | None = None) -> dict:
        message = (message or "").strip()
        files = []
        try:
            result = self._handle(message, source, attachment)
        except Exception as exc:
            result = {"text": f"I hit an error while processing that: {exc}", "files": [], "images": []}
        result.setdefault("files", [])
        result.setdefault("images", [])
        append_log(source, message, result["text"], {"files": [str(path) for path in result.get("files", [])], "images": result.get("images", [])})
        return result

    def _handle(self, message: str, source: str, attachment: Path | None) -> dict:
        lower = message.lower()

        if attachment:
            return self._handle_attachment(message, attachment)

        document_action = perform_document_action(message, {}, "autonova_phase1")
        if document_action:
            return {"text": document_action.summary, "files": document_action.files}

        if lower.startswith(("add kb", "remember:")):
            content = re.sub(r"^(add kb|remember:)\s*", "", message, flags=re.I).strip()
            entry = self.kb.add("note", content[:60] or "New knowledge", content, ["telegram"])
            return {"text": f"Saved to knowledge base as {entry['id']}: {entry['title']}", "files": []}

        if lower.startswith(("calculate", "calc ")):
            expression = re.sub(r"^(calculate|calc)\s*", "", message, flags=re.I).strip()
            return {"text": calculate(expression), "files": []}

        if lower.startswith(("task ", "remind ", "reminder ")):
            task = add_task(message, source)
            return {"text": f"Task captured as #{task['id']}: {task['text']}", "files": []}

        if lower.startswith(("draft", "create document", "write document")):
            matches = self.kb.search(message)
            txt = draft_text_document(message, matches)
            docx = draft_docx(message, matches)
            pdf = draft_pdf(message, matches)
            return {"text": f"Draft created using {len(matches)} relevant knowledge-base entries.", "files": [txt, docx, pdf]}

        if lower.startswith(("image", "generate image", "make image")):
            prompt = re.sub(r"^(generate image|make image|image)\s*", "", message, flags=re.I).strip()
            url = "https://image.pollinations.ai/prompt/" + quote_plus(prompt or "modern real estate marketing banner")
            return {"text": "Generated image:", "files": [], "images": [url]}

        matches = self.kb.search(message)
        llm_answer = generate_with_ollama(message, matches)
        if llm_answer:
            label = "Local LLM answer using knowledge base:" if matches else "Local LLM answer:"
            return {"text": f"{label}\n{llm_answer}", "files": []}

        if matches:
            lines = ["Knowledge-base answer (Ollama unavailable, using local search only):"]
            for item in matches[:3]:
                lines.append(f"- {item['title']} ({item['category']}): {item['content']}")
            return {"text": "\n".join(lines), "files": []}

        return {
            "text": "I could not reach the local LLM and found no matching knowledge-base entry. Start Ollama with `ollama serve`, or add knowledge with `remember: ...`.",
            "files": [],
        }

    def _handle_attachment(self, message: str, attachment: Path) -> dict:
        suffix = attachment.suffix.lower()
        if wants_knowledge_ingest(message) or not wants_document_edit(message):
            content = extract_document_text(attachment)
            if not content and suffix in {".txt", ".md"}:
                content = summarize_text_file(attachment)
            if not content:
                return {"text": f"Received {attachment.name}, but I could not extract readable text for the knowledge base.", "files": []}
            entry = self.kb.add("document", attachment.name, content, ["upload"])
            return {"text": f"Saved {attachment.name} to knowledge base as {entry['id']}.", "files": []}
        if suffix in {".txt", ".md"}:
            summary = summarize_text_file(attachment)
            entry = self.kb.add("document", attachment.name, summary, ["upload"])
            return {"text": f"File ingested into knowledge base as {entry['id']}.\nSummary: {summary[:500]}", "files": []}
        if suffix == ".csv":
            output = edit_csv(attachment, message)
            return {"text": "CSV edited and ready to return.", "files": [output]}
        if suffix == ".xlsx":
            output = edit_xlsx(attachment, message)
            return {"text": "Excel spreadsheet edited and ready to return.", "files": [output]}
        return {
            "text": f"Received {attachment.name}. Phase 1 processes TXT/MD ingestion plus CSV/XLSX spreadsheet edits.",
            "files": [],
        }
