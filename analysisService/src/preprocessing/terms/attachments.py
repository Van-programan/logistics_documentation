from __future__ import annotations

import re
from dataclasses import dataclass

from src.parsing.enums import AttachmentType
from src.parsing.result_model import ParsedDocument


_ATTACHMENT_PATTERNS: list[tuple[str, AttachmentType, str]] = [
    (
        r"приложени\w*\s*№?\s*\d*[\s\S]{0,200}?спецификаци\w*",
        AttachmentType.SPECIFICATION,
        "Спецификация",
    ),
    (
        r"приложени\w*\s*№?\s*\d*[\s\S]{0,200}?график\w*\s*поставк",
        AttachmentType.SCHEDULE,
        "График поставки",
    ),
    (
        r"приложени\w*\s*№?\s*\d*[\s\S]{0,200}?(?:дополнительн\w*\s*соглашени|допсоглашени)",
        AttachmentType.ADDENDUM,
        "Доп. соглашение",
    ),
]


_EMBEDDED_PATTERNS: dict[AttachmentType, list[str]] = {
    AttachmentType.SPECIFICATION: [
        r"[Сс]пецификация\s*№\s*\d+",
        r"(?:^|\n)\s*СПЕЦИФИКАЦИЯ(?:\s+ТОВАРА)?\s*(?:\n|$)",
    ],
    AttachmentType.SCHEDULE: [
        r"[Гг]рафик\s+поставки\s*№\s*\d+",
        r"(?:^|\n)\s*ГРАФИК\s+ПОСТАВКИ(?:\s+ТОВАРА)?\s*(?:\n|$)",
    ],
    AttachmentType.ADDENDUM: [
        r"[Дд]ополнительное\s+соглашение\s*№\s*\d+",
    ],
}


@dataclass
class MissingAttachment:
    referenced_name: str
    referenced_type: AttachmentType


def detect_missing_attachments(doc: ParsedDocument, loaded_sources) -> list[MissingAttachment]:
    loaded_types = {
        s.attachment_type
        for s in loaded_sources
        if s.attachment_type != AttachmentType.MAIN
    }

    found: list[MissingAttachment] = []

    for pattern, att_type, display_name in _ATTACHMENT_PATTERNS:
        if att_type in loaded_types:
            continue
        if not re.search(pattern, doc.full_text, flags=re.IGNORECASE):
            continue
        if _is_embedded(doc, att_type):
            continue

        found.append(MissingAttachment(
            referenced_name=display_name,
            referenced_type=att_type,
        ))

    return found


def _is_embedded(doc: ParsedDocument, att_type: AttachmentType) -> bool:
    patterns = _EMBEDDED_PATTERNS.get(att_type, [])
    if not patterns:
        return False

    for pat in patterns:
        if re.search(pat, doc.full_text, flags=re.IGNORECASE | re.MULTILINE):
            return True

    return False