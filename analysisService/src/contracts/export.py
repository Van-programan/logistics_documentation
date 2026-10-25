from __future__ import annotations

from dataclasses import dataclass, field
from src.parsing.models import DocumentFormat


@dataclass
class ExportSegment:
    source_id: str
    format: DocumentFormat
    local_start: int
    local_end: int
    global_start: int
    global_end: int

    paragraph: int | None = None
    table: int | None = None
    row: int | None = None

    page: int | None = None
    pdf_char_offset_start: int | None = None
    pdf_char_offset_end: int | None = None


@dataclass
class ExportInfo:
    segments: list[ExportSegment] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict: ...