from __future__ import annotations

from dataclasses import dataclass, field

from src.parsing.enums import DocumentFormat


@dataclass
class ExportSegment:
    """Один непрерывный кусок фрагмента риска внутри одного блока.

    Несёт координаты в ДВУХ системах:
      - global_* — в склеенном ParsedDocument.full_text (для анализа);
      - local_*  — в тексте СВОЕГО файла (для сервиса экспорта).
    """
    source_id: str
    format: DocumentFormat
    local_start: int
    local_end: int
    global_start: int
    global_end: int

    # DOCX
    paragraph: int | None = None
    table: int | None = None
    row: int | None = None

    # PDF
    page: int | None = None
    pdf_char_offset_start: int | None = None
    pdf_char_offset_end: int | None = None


@dataclass
class ExportInfo:
    """Рецепт подсветки фрагмента риска в исходных файлах.

    Может содержать несколько сегментов, если фрагмент пересекает
    границы блоков (абзацев DOCX / страниц PDF) или файлов.
    """
    segments: list[ExportSegment] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Для сериализации в JSON (событие Kafka, БД)."""
        return {
            "segments": [
                {
                    "source_id": s.source_id,
                    "format": s.format.value,
                    "local_start": s.local_start,
                    "local_end": s.local_end,
                    "global_start": s.global_start,
                    "global_end": s.global_end,
                    "paragraph": s.paragraph,
                    "table": s.table,
                    "row": s.row,
                    "page": s.page,
                    "pdf_char_offset_start": s.pdf_char_offset_start,
                    "pdf_char_offset_end": s.pdf_char_offset_end,
                }
                for s in self.segments
            ],
            "source_ids": self.source_ids,
        }