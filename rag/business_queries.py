from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rag.knowledge_base import _candidate_files, _load_file
from utils.config import load_settings


PROPERTY_ID_RE = re.compile(r"^(P[RC]-\d{3,})$", re.I)
AGREEMENT_ID_RE = re.compile(r"^([RC]A-\d{3,})$", re.I)
COUNT_RE = re.compile(r"\b(how\s+many|count|number\s+of|total)\b", re.I)
PROPERTY_RE = re.compile(r"\b(prop(?:erty|erties|rties)?|properties|listings?)\b", re.I)
RENT_RE = re.compile(r"\b(rent|rental|tenant|tenants|collection)\b", re.I)
PENDING_RE = re.compile(r"\b(pending|left|outstanding|overdue|due|collect|balance|unpaid|owe|owes|owed|owing)\b", re.I)
STATUSES = ("Available", "Under Offer", "Sold", "Rented")


@dataclass(frozen=True)
class PropertyRecord:
    prop_id: str
    category: str
    location: str
    status: str


@dataclass(frozen=True)
class RentRecord:
    agreement_id: str
    tenant: str
    property_id: str
    rent_amount: int
    paid_amount: int
    status: str

    @property
    def pending_amount(self) -> int:
        return max(self.rent_amount - self.paid_amount, 0)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _money(value: str) -> int:
    cleaned = re.sub(r"[^\d]", "", value)
    return int(cleaned or "0")


def _is_master_property_listing(path: Path, text: str) -> bool:
    haystack = f"{path.name}\n{text[:500]}".lower()
    return (
        ("property" in haystack and "listing" in haystack)
        or "property portfolio" in haystack
        or "master listing" in haystack
    )


def _is_rent_collection_tracker(path: Path, text: str) -> bool:
    haystack = f"{path.name}\n{text[:500]}".lower()
    return "rent" in haystack and "collection" in haystack


def _parse_property_records(text: str) -> list[PropertyRecord]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    records: list[PropertyRecord] = []
    for index, line in enumerate(lines):
        match = PROPERTY_ID_RE.match(line)
        if not match:
            continue

        prop_id = match.group(1).upper()
        category = "residential" if prop_id.startswith("PR-") else "commercial"
        location = lines[index + 1] if index + 1 < len(lines) else ""
        window = lines[index + 1 : index + 10]
        status = next((candidate for candidate in STATUSES if candidate in window), "")
        if status:
            records.append(PropertyRecord(prop_id, category, location, status))
    return records


def _parse_rent_records(text: str) -> list[RentRecord]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    records: list[RentRecord] = []
    for index, line in enumerate(lines):
        match = AGREEMENT_ID_RE.match(line)
        if not match:
            continue

        agreement_id = match.group(1).upper()
        window = lines[index + 1 : index + 10]
        if len(window) < 7:
            continue

        tenant = window[0]
        property_id = window[1]
        rent_amount = _money(window[3])
        paid_amount = _money(window[4])
        status = window[7] if agreement_id.startswith("RA-") and len(window) > 7 else window[6]
        if rent_amount:
            records.append(
                RentRecord(
                    agreement_id=agreement_id,
                    tenant=tenant,
                    property_id=property_id,
                    rent_amount=rent_amount,
                    paid_amount=paid_amount,
                    status=status,
                )
            )
    return records


def _property_records(tenant_id: str | None = None) -> list[PropertyRecord]:
    settings = load_settings()
    records: list[PropertyRecord] = []
    for path in _candidate_files(settings, tenant_id):
        try:
            docs = _load_file(path)
        except Exception:
            continue
        text = "\n".join(doc.page_content for doc in docs if doc.page_content.strip())
        if _is_master_property_listing(path, text):
            records.extend(_parse_property_records(text))
    return records


def _rent_records(tenant_id: str | None = None) -> list[RentRecord]:
    settings = load_settings()
    records_by_id: dict[str, RentRecord] = {}
    files = sorted(_candidate_files(settings, tenant_id), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in files:
        try:
            docs = _load_file(path)
        except Exception:
            continue
        text = "\n".join(doc.page_content for doc in docs if doc.page_content.strip())
        if _is_rent_collection_tracker(path, text):
            for record in _parse_rent_records(text):
                records_by_id.setdefault(record.agreement_id, record)
    return list(records_by_id.values())


def _query_mentions_record(query: str, record: RentRecord) -> bool:
    normalized_query = _normalize(query)
    tenant = _normalize(record.tenant)
    tenant_parts = [part for part in tenant.split() if len(part) >= 3]
    return (
        _normalize(record.agreement_id) in normalized_query
        or _normalize(record.property_id) in normalized_query
        or tenant in normalized_query
        or any(part in normalized_query for part in tenant_parts)
    )


def _amounts_in_query(query: str) -> set[int]:
    amounts: set[int] = set()
    for raw in re.findall(r"(?:rs\.?|inr)?\s*(\d[\d,]*)", query, flags=re.I):
        amount = _money(raw)
        if amount:
            amounts.add(amount)
    return amounts


def _rent_record_line(record: RentRecord) -> str:
    return (
        f"- {record.tenant} ({record.property_id}, {record.agreement_id}): "
        f"Rs. {record.pending_amount:,} pending "
        f"(rent Rs. {record.rent_amount:,}, paid Rs. {record.paid_amount:,}, status: {record.status})."
    )


def answer_property_count(query: str, tenant_id: str | None = None) -> str | None:
    if not (COUNT_RE.search(query) and PROPERTY_RE.search(query)):
        return None

    records = _property_records(tenant_id)
    if not records:
        return None

    lower = query.lower()
    requested_status = None
    for status in STATUSES:
        if status.lower() in lower:
            requested_status = status
            break

    selected = [record for record in records if not requested_status or record.status == requested_status]
    residential = [record for record in selected if record.category == "residential"]
    commercial = [record for record in selected if record.category == "commercial"]

    if requested_status:
        label = requested_status.lower()
        ids = ", ".join(record.prop_id for record in selected)
        return (
            f"You have {len(selected)} {label} properties: "
            f"{len(residential)} residential and {len(commercial)} commercial.\n"
            f"Property IDs: {ids}."
        )

    return (
        f"You have {len(selected)} properties listed in the master property listing: "
        f"{len(residential)} residential and {len(commercial)} commercial."
    )


def answer_pending_rent(query: str, tenant_id: str | None = None) -> str | None:
    records = _rent_records(tenant_id)
    mentioned_records = [record for record in records if _query_mentions_record(query, record)]
    is_rent_query = RENT_RE.search(query) or mentioned_records
    if not (is_rent_query and PENDING_RE.search(query)):
        return None

    if not records:
        return None

    lower = query.lower()
    amounts = _amounts_in_query(query)
    scoped_records = mentioned_records or records

    if mentioned_records:
        lines: list[str] = []
        for record in mentioned_records:
            if record.pending_amount:
                lines.append(_rent_record_line(record))
            else:
                lines.append(
                    f"- {record.tenant} ({record.property_id}, {record.agreement_id}) has no pending rent: "
                    f"rent Rs. {record.rent_amount:,}, paid Rs. {record.paid_amount:,}, status: {record.status}."
                )
        return "\n".join(lines)

    if "overdue" in lower and not any(word in lower for word in ("pending", "left", "outstanding", "balance", "unpaid")):
        pending = [record for record in scoped_records if record.pending_amount > 0 and record.status.lower() == "overdue"]
        label = "overdue rent"
    else:
        pending = [record for record in scoped_records if record.pending_amount > 0]
        label = "pending rent left to collect"

    if amounts:
        amount_matches = [record for record in pending if record.pending_amount in amounts]
        if amount_matches:
            pending = amount_matches
        else:
            paid_or_rent_matches = [
                record
                for record in records
                if record.rent_amount in amounts or record.paid_amount in amounts
            ]
            lines = [f"No tenant/account has {', '.join(f'Rs. {amount:,}' for amount in sorted(amounts))} pending rent."]
            for record in paid_or_rent_matches:
                lines.append(
                    f"- {record.tenant} ({record.property_id}, {record.agreement_id}) has rent Rs. {record.rent_amount:,}, "
                    f"paid Rs. {record.paid_amount:,}, pending Rs. {record.pending_amount:,}, status: {record.status}."
                )
            return "\n".join(lines)

    total = sum(record.pending_amount for record in pending)
    if not pending:
        return f"No {label} was found based on the rent collection tracker."

    lines = [
        f"{label.capitalize()} is Rs. {total:,} from {len(pending)} tenant/account(s):"
    ]
    for record in pending:
        lines.append(_rent_record_line(record))
    return "\n".join(lines)
