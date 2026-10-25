from __future__ import annotations

from dataclasses import dataclass, field
from src.contracts.source import SourceDocument
from src.parsing.enums import DocumentFormat

@dataclass
class TextBlock:
    text: str
    global_start: int
    global_end: int
    source_id: str
    local_start: int
    local_end: int

    paragraph: int | None = None
    table: int | None = None
    row: int | None = None

    page: int | None = None
    pdf_char_offset_start: int | None = None
    pdf_char_offset_end: int | None = None


@dataclass
class PdfCharBBox:
    char_index: int
    page: int
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass
class ParsedSource:
    source: SourceDocument
    format: DocumentFormat
    full_text: str
    blocks: list[TextBlock] = field(default_factory=list)
    page_count: int | None = None
    metadata: dict = field(default_factory=dict)
    pdf_char_bboxes: list[PdfCharBBox] = field(default_factory=list)


@dataclass
class RawParseResult:
    format: DocumentFormat
    full_text: str
    blocks: list[dict]
    page_count: int | None = None
    metadata: dict = field(default_factory=dict)
    pdf_char_bboxes: list[dict] = field(default_factory=list)