from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from docs.document_ops import create_document_bundle
from rag.document_queries import _question_titles, _text_for_file, target_document


CLASSIFY_RE = re.compile(r"\b(classify|categorize|category|categories|difficulty|easy|medium|tough|hard)\b", re.I)
IMPORTANT_RE = re.compile(r"\b(important|most\s+important|top|selected|must\s+do|priority|prepare)\b", re.I)
QUESTION_RE = re.compile(r"\b(questions?|problems?|coding)\b", re.I)
DOCUMENT_RE = re.compile(r"\b(document|docx|pdf|file|report|share|provide|send|return)\b", re.I)


@dataclass(frozen=True)
class ClassifiedQuestion:
    number: int
    title: str
    difficulty: str
    reason: str


def wants_question_classification_document(text: str) -> bool:
    return bool(CLASSIFY_RE.search(text) and QUESTION_RE.search(text) and DOCUMENT_RE.search(text))


def wants_important_questions_document(text: str) -> bool:
    return bool(IMPORTANT_RE.search(text) and QUESTION_RE.search(text) and DOCUMENT_RE.search(text))


def _split_title(raw: str) -> tuple[int, str] | None:
    match = re.match(r"\s*(\d{1,3})\.\s+(.+)", raw)
    if not match:
        return None
    return int(match.group(1)), match.group(2).strip()


def _difficulty(title: str) -> tuple[str, str]:
    lower = title.lower()
    tough_terms = {
        "subarray",
        "substring",
        "permutation",
        "anagram",
        "duplicate",
        "missing",
        "rotation",
        "matrix",
        "sort",
        "merge",
        "prime numbers up to",
        "sum of prime",
    }
    medium_terms = {
        "prime",
        "armstrong",
        "strong",
        "perfect",
        "gcd",
        "lcm",
        "fibonacci",
        "palindrome",
        "array",
        "words",
        "sentence",
        "vowels",
        "consonants",
        "reverse words",
    }

    if any(term in lower for term in tough_terms):
        return "Tough", "requires stronger algorithmic thinking or careful data-structure handling"
    if any(term in lower for term in medium_terms):
        return "Medium", "requires loops plus a non-trivial condition, pattern, or helper logic"
    return "Easy", "can usually be solved with basic input, conditions, loops, or simple string operations"


def _requested_count(text: str, default: int = 20) -> int:
    match = re.search(r"\b(\d{1,3})\b", text)
    if match:
        return max(1, min(int(match.group(1)), 100))
    return default


def classify_questions_from_document(path: Path) -> list[ClassifiedQuestion]:
    titles = _question_titles(_text_for_file(path))
    classified: list[ClassifiedQuestion] = []
    for raw in titles:
        parsed = _split_title(raw)
        if not parsed:
            continue
        number, title = parsed
        difficulty, reason = _difficulty(title)
        classified.append(ClassifiedQuestion(number, title, difficulty, reason))
    return sorted(classified, key=lambda item: item.number)


def _importance_score(question: ClassifiedQuestion) -> tuple[int, int]:
    lower = question.title.lower()
    score = 0
    high_value_terms = {
        "prime": 5,
        "palindrome": 5,
        "array": 5,
        "string": 5,
        "duplicate": 5,
        "missing": 5,
        "sort": 5,
        "search": 4,
        "gcd": 4,
        "lcm": 4,
        "fibonacci": 4,
        "armstrong": 4,
        "frequency": 4,
        "two sum": 5,
        "reverse": 3,
        "digits": 3,
        "vowels": 3,
        "binary": 3,
    }
    for term, weight in high_value_terms.items():
        if term in lower:
            score += weight
    if question.difficulty == "Tough":
        score += 4
    elif question.difficulty == "Medium":
        score += 3
    else:
        score += 1
    return score, -question.number


def important_questions_from_document(path: Path, limit: int = 20) -> list[ClassifiedQuestion]:
    questions = classify_questions_from_document(path)
    ranked = sorted(questions, key=_importance_score, reverse=True)
    return sorted(ranked[:limit], key=lambda item: item.number)


def _render_document(source: Path, questions: list[ClassifiedQuestion]) -> str:
    grouped: dict[str, list[ClassifiedQuestion]] = defaultdict(list)
    for question in questions:
        grouped[question.difficulty].append(question)

    lines = [
        "Classified Coding Questions",
        "",
        f"Source document: {source.name}",
        f"Total questions classified: {len(questions)}",
        "",
        "Basis of classification: common interview-programming difficulty, required algorithmic thinking, edge-case handling, and implementation complexity.",
        "",
        "Summary",
        f"Easy: {len(grouped['Easy'])}",
        f"Medium: {len(grouped['Medium'])}",
        f"Tough: {len(grouped['Tough'])}",
        "",
    ]

    for difficulty in ("Easy", "Medium", "Tough"):
        items = grouped[difficulty]
        lines.extend([f"{difficulty} Questions ({len(items)})", ""])
        for index, question in enumerate(items, start=1):
            lines.append(f"{index}. Question {question.number}: {question.title}")
            lines.append(f"   Reason: {question.reason}.")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _render_important_document(source: Path, questions: list[ClassifiedQuestion], requested_count: int) -> str:
    lines = [
        f"Top {len(questions)} Important Coding Questions",
        "",
        f"Source document: {source.name}",
        f"Requested questions: {requested_count}",
        f"Selected questions: {len(questions)}",
        "",
        "Selection basis: common interview frequency, usefulness for fundamentals, algorithmic coverage, and implementation practice value.",
        "",
    ]
    for index, question in enumerate(questions, start=1):
        lines.append(f"{index}. Question {question.number}: {question.title}")
        lines.append(f"   Difficulty: {question.difficulty}")
        lines.append(f"   Why important: {question.reason}; this topic is useful for coding-test preparation.")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def create_question_classification_bundle(
    instruction: str,
    tenant_id: str,
    preferred_file: str | None = None,
) -> tuple[str, list[Path]] | None:
    source = target_document(instruction, tenant_id=tenant_id, preferred_file=preferred_file)
    if not source:
        return None

    questions = classify_questions_from_document(source)
    if not questions:
        return None

    document_text = _render_document(source, questions)
    files = create_document_bundle(document_text, "classified_questions", tenant_id)
    summary = (
        f"I classified {len(questions)} questions from {source.name} into Easy, Medium, and Tough categories. "
        "I have attached the classified document."
    )
    return summary, files


def create_important_questions_bundle(
    instruction: str,
    tenant_id: str,
    preferred_file: str | None = None,
) -> tuple[str, list[Path]] | None:
    source = target_document(instruction, tenant_id=tenant_id, preferred_file=preferred_file)
    if not source:
        return None

    requested_count = _requested_count(instruction, default=20)
    questions = important_questions_from_document(source, requested_count)
    if not questions:
        return None

    document_text = _render_important_document(source, questions, requested_count)
    files = create_document_bundle(document_text, f"top_{len(questions)}_important_questions", tenant_id)
    summary = (
        f"I selected {len(questions)} important questions from {source.name}. "
        "I have attached the document."
    )
    return summary, files
