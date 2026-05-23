from __future__ import annotations

import ast
import operator
import re


IMAGE_RE = re.compile(
    r"\b(generate|create|make|draw|design)\b.*\b(image|photo|picture|visual|banner|poster|mockup|logo|blueprint|floor\s*plan|layout|map|drawing)\b"
    r"|\b(image|photo|picture|visual|banner|poster|mockup|logo|blueprint|floor\s*plan|layout|drawing)\s+of\b",
    flags=re.I,
)
IMAGE_FOLLOWUP_RE = re.compile(
    r"\b(mark|label|add labels|annotate|name|show|change|modify|edit|make it|update|revise)\b.*\b(it|this|that|drawing|image|photo|picture|visual|blueprint|floor\s*plan|layout|rooms?)\b"
    r"|\b(mark|label|annotate)\b",
    flags=re.I,
)
DOCUMENT_RE = re.compile(
    r"\b(draft|write|create|prepare|format|make)\b.*\b(document|docx|word|pdf|agreement|contract|letter|report|proposal|brochure)\b"
    r"|\b(draft|agreement|contract|proposal|report)\b",
    flags=re.I,
)
TASK_RE = re.compile(r"^\s*(task|remind|reminder|follow up|todo|to-do)\b", flags=re.I)
ADD_KB_RE = re.compile(r"^\s*(remember|save knowledge|add kb)\s*:?", flags=re.I)
CALC_RE = re.compile(r"^\s*(calculate|calc|compute)\b|[\d\)]\s*[\+\-\*/%]\s*[\d\(]", flags=re.I)

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


def classify(text: str) -> str:
    if ADD_KB_RE.search(text):
        return "knowledge"
    if IMAGE_RE.search(text):
        return "image"
    if IMAGE_FOLLOWUP_RE.search(text):
        return "image_followup"
    if DOCUMENT_RE.search(text):
        return "document"
    if TASK_RE.search(text):
        return "task"
    if CALC_RE.search(text):
        return "calculation"
    return "chat"


def image_prompt(text: str) -> str:
    prompt = re.sub(
        r"^\s*(generate|create|make|draw|design)\s+(an?\s+)?(image|photo|picture|visual|blueprint|floor\s*plan|layout|drawing)\s+(of\s+)?",
        "",
        text,
        flags=re.I,
    )
    prompt = re.sub(r"^\s*(image|photo|picture|visual|blueprint|floor\s*plan|layout|drawing)\s+of\s+", "", prompt, flags=re.I)
    return prompt.strip() or text.strip()


def improve_image_prompt(prompt: str) -> str:
    lower = prompt.lower()
    additions = []
    if any(word in lower for word in ("blueprint", "floor plan", "floorplan", "layout", "2bhk", "3bhk", "flat", "apartment")):
        for phrase in (
            "architectural floor plan blueprint",
            "top-down view",
            "clear black linework on white background",
            "clearly labelled rooms",
            "labels for bedroom, bathroom, kitchen, living room, balcony, entry, dimensions",
            "readable text labels",
        ):
            if phrase not in lower:
                additions.append(phrase)
    if additions:
        return prompt + ", " + ", ".join(additions)
    return prompt


def image_followup_prompt(last_prompt: str, instruction: str) -> str:
    combined = f"{last_prompt}. Apply this change: {instruction}."
    if re.search(r"\b(mark|label|annotate|name|what'?s|whats|room|bedroom|bathroom|kitchen)\b", instruction, flags=re.I):
        combined += " Regenerate the complete image with clear readable labels for every room and area."
    return improve_image_prompt(combined)


def document_prompt(text: str) -> str:
    return re.sub(r"^\s*(docx|document)\s+", "", text, flags=re.I).strip()


def knowledge_text(text: str) -> str:
    return ADD_KB_RE.sub("", text).strip()


def calculation_expression(text: str) -> str:
    expression = re.sub(r"^\s*(calculate|calc|compute)\s*", "", text, flags=re.I).strip()
    expression = expression.replace(",", "")
    expression = re.sub(r"\blakh\b", "*100000", expression, flags=re.I)
    expression = re.sub(r"\bcrore\b", "*10000000", expression, flags=re.I)
    expression = expression.replace("%", "/100")
    return expression


def _eval_math(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval_math(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval_math(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval_math(node.left), _eval_math(node.right))
    raise ValueError("Only arithmetic expressions are allowed.")


def calculate(text: str) -> str:
    expression = calculation_expression(text)
    tree = ast.parse(expression, mode="eval")
    result = _eval_math(tree)
    if isinstance(result, float):
        return f"{expression} = {result:,.2f}"
    return f"{expression} = {result:,}"
