from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from utils.config import load_settings


def _safe_stem(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()[:48] or "assistant_output"


def _generated_path(stem: str, suffix: str) -> Path:
    settings = load_settings()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return settings.generated_dir / f"{stamp}_{_safe_stem(stem)}.{suffix}"


def create_docx(text: str, filename: str | None = None) -> Path:
    settings = load_settings()
    path = settings.generated_dir / filename if filename else _generated_path(text, "docx")
    document = Document()
    for paragraph in text.splitlines() or [text]:
        document.add_paragraph(paragraph)
    document.save(path)
    return path


def create_text_file(text: str, stem: str = "assistant_output") -> Path:
    path = _generated_path(stem, "txt")
    path.write_text(text, encoding="utf-8")
    return path


def create_pdf(text: str, stem: str = "assistant_output") -> Path:
    path = _generated_path(stem, "pdf")
    lines = []
    for raw_line in text.splitlines():
        line = raw_line
        while len(line) > 88:
            lines.append(line[:88])
            line = line[88:]
        lines.append(line)

    content = ["BT", "/F1 11 Tf", "50 780 Td", "14 TL"]
    for index, line in enumerate(lines[:48]):
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index:
            content.append("T*")
        content.append(f"({safe}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode("ascii") + stream + b"\nendstream endobj\n",
    ]
    out = [b"%PDF-1.4\n"]
    offsets = [0]
    for obj in objects:
        offsets.append(sum(len(part) for part in out))
        out.append(obj)
    xref_start = sum(len(part) for part in out)
    xref = [b"xref\n0 6\n", b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(xref)
    out.append(b"trailer << /Size 6 /Root 1 0 R >>\n")
    out.append(f"startxref\n{xref_start}\n%%EOF".encode("ascii"))
    path.write_bytes(b"".join(out))
    return path


def create_document_bundle(text: str, stem: str = "assistant_output") -> list[Path]:
    return [create_text_file(text, stem), create_docx(text), create_pdf(text, stem)]


def _iter_docx_paragraphs(document: Document):
    for paragraph in document.paragraphs:
        yield paragraph
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield paragraph


def _docx_text(document: Document) -> str:
    return "\n".join(paragraph.text for paragraph in _iter_docx_paragraphs(document) if paragraph.text.strip())


def _replace_in_docx(document: Document, replacements: dict[str, str]) -> int:
    changed = 0
    for paragraph in _iter_docx_paragraphs(document):
        text = paragraph.text
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != text:
            paragraph.text = updated
            changed += 1
    return changed


def _extract_party_names(instruction: str) -> dict[str, str]:
    parties: dict[str, str] = {}
    buyer_match = re.search(r"\bbuyer(?:\s+name)?\s*(?:is|=|:|as|to)?\s*(.+)", instruction, flags=re.I)
    seller_match = re.search(r"\b(?:seller|vendor)(?:\s+name)?\s*(?:is|=|:|as|to)?\s*(.+)", instruction, flags=re.I)

    if buyer_match:
        buyer = re.split(r"\s+(?:and\s+)?(?:seller|vendor)(?:\s+name)?\b|[,;]", buyer_match.group(1), maxsplit=1, flags=re.I)[0]
        buyer = re.sub(r"\b(for|in|on|with)\b.*$", "", buyer, flags=re.I).strip(" .,'-")
        if buyer:
            parties["buyer"] = buyer
    if seller_match:
        seller = re.split(r"\s+(?:and\s+)?(?:buyer|purchaser)(?:\s+name)?\b|[,;]", seller_match.group(1), maxsplit=1, flags=re.I)[0]
        seller = re.sub(r"\b(for|in|on|with)\b.*$", "", seller, flags=re.I).strip(" .,'-")
        if seller:
            parties["seller"] = seller
    return parties


def _party_replacements(parties: dict[str, str]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    if buyer := parties.get("buyer"):
        replacements.update(
            {
                "[BUYER]": buyer,
                "[BUYER NAME]": buyer,
                "{{BUYER}}": buyer,
                "{{BUYER_NAME}}": buyer,
                "<BUYER>": buyer,
                "<BUYER NAME>": buyer,
                "BUYER_NAME": buyer,
                "Purchaser Name": buyer,
                "Buyer Name": buyer,
                "Name of Buyer": buyer,
            }
        )
    if seller := parties.get("seller"):
        replacements.update(
            {
                "[SELLER]": seller,
                "[SELLER NAME]": seller,
                "{{SELLER}}": seller,
                "{{SELLER_NAME}}": seller,
                "{{VENDOR}}": seller,
                "<SELLER>": seller,
                "<SELLER NAME>": seller,
                "SELLER_NAME": seller,
                "Vendor Name": seller,
                "Seller Name": seller,
                "Name of Seller": seller,
            }
        )
    return replacements


def _rewrite_docx_with_llm(path: Path, instruction: str, original_text: str) -> Path:
    from llm.ollama_client import generate_response

    prompt = (
        "Rewrite this DOCX template according to the user's instruction. "
        "Return only the revised document text. Preserve the legal/document structure, headings, clauses, "
        "numbering intent, and all unchanged details. Do not append an explanation.\n\n"
        f"Instruction:\n{instruction}"
    )
    revised = generate_response(prompt, f"Original DOCX text from {path.name}:\n{original_text[:18000]}")
    return create_docx(revised, f"{path.stem}_edited.docx")


def modify_docx(path: Path, instruction: str) -> Path:
    settings = load_settings()
    document = Document(path)
    changed = 0
    replace_match = re.search(r"replace\s+(.+?)\s+with\s+(.+)", instruction, flags=re.I)
    if replace_match:
        old, new = replace_match.groups()
        changed += _replace_in_docx(document, {old: new})
    elif re.search(r"\b(add|append)\b", instruction, flags=re.I):
        content = re.sub(r"^\s*(add|append)\s+(paragraph|section|text)?\s*:?", "", instruction, flags=re.I).strip()
        document.add_paragraph(content or instruction)
        changed += 1
    else:
        parties = _extract_party_names(instruction)
        if parties:
            changed += _replace_in_docx(document, _party_replacements(parties))
        if changed == 0:
            return _rewrite_docx_with_llm(path, instruction, _docx_text(document))
    output = settings.generated_dir / f"{path.stem}_edited{path.suffix}"
    document.save(output)
    return output


def update_xlsx(path: Path, instruction: str) -> Path:
    settings = load_settings()
    workbook = load_workbook(path)
    sheet = workbook.active
    lower = instruction.lower()

    percent_match = re.search(r"column\s+([a-z0-9_ ]+)\s*\+(\d+(?:\.\d+)?)%", lower)
    if percent_match:
        header_name = percent_match.group(1).strip()
        multiplier = 1 + float(percent_match.group(2)) / 100
        headers = {
            str(cell.value).strip().lower(): cell.column
            for cell in sheet[1]
            if cell.value is not None
        }
        column = headers.get(header_name)
        if column:
            for row in range(2, sheet.max_row + 1):
                cell = sheet.cell(row=row, column=column)
                if isinstance(cell.value, (int, float)):
                    cell.value = cell.value * multiplier

    formula_match = re.search(r"formula\s+([a-z]+\d+)\s*=\s*(.+)", instruction, flags=re.I)
    if formula_match:
        cell_ref, formula = formula_match.groups()
        sheet[cell_ref.upper()] = formula if formula.startswith("=") else f"={formula}"

    set_match = re.search(r"(?:set|update)\s+([a-z]+\d+)\s*(?:=|to)\s*(.+)", instruction, flags=re.I)
    if set_match:
        cell_ref, value = set_match.groups()
        value = value.strip()
        try:
            parsed_value = float(value) if "." in value else int(value)
        except ValueError:
            parsed_value = value
        sheet[cell_ref.upper()] = parsed_value

    status_match = re.search(r"mark\s+(?:all\s+)?(?:rows\s+)?(?:as\s+)?([a-zA-Z ]+)", instruction, flags=re.I)
    if status_match:
        headers = [str(cell.value or "").strip().lower() for cell in sheet[1]]
        if "status" in headers:
            status_col = headers.index("status") + 1
        else:
            status_col = sheet.max_column + 1
            sheet.cell(row=1, column=status_col).value = "status"
        status_value = status_match.group(1).strip().title()
        for row in range(2, sheet.max_row + 1):
            sheet.cell(row=row, column=status_col).value = status_value

    output = settings.generated_dir / f"{path.stem}_edited{path.suffix}"
    workbook.save(output)
    return output


def edit_pdf_as_new_pdf(path: Path, instruction: str, revised_text: str | None = None) -> Path:
    original = read_pdf_text(path)
    if revised_text:
        text = revised_text
    else:
        text = f"Edited PDF content based on instruction: {instruction}\n\nOriginal extracted text:\n{original}"
    return create_pdf(text, f"{path.stem}_edited")


def process_uploaded_document(path: Path, instruction: str, revised_text: str | None = None) -> Path | None:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return modify_docx(path, instruction)
    if suffix == ".xlsx":
        return update_xlsx(path, instruction)
    if suffix == ".pdf":
        return edit_pdf_as_new_pdf(path, instruction, revised_text)
    return None


def read_pdf_text(path: Path, max_chars: int = 12000) -> str:
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
        if sum(len(part) for part in parts) >= max_chars:
            break
    return "\n".join(parts).strip()[:max_chars]
