from __future__ import annotations

from pathlib import Path

from src.parsing.factory import get_parser
from src.parsing.result_model import ParsedDocument
from src.parsing.enums import AttachmentType
from src.parsing.models import ParsedSource, PdfCharBBox, RawParseResult, SourceDocument, TextBlock


class MultiFileParser:

    def __init__(self, separator: str = "\n\n"):
        self.separator = separator

    def parse(self, sources: list[SourceDocument]) -> ParsedDocument:
        if not sources:
            raise ValueError("Нет файлов для парсинга")

        sources = sorted(
            sources,
            key=lambda s: 0 if s.attachment_type == AttachmentType.MAIN else 1,
        )

        all_parts: list[str] = []
        all_blocks: list[TextBlock] = []
        parsed_sources: dict[str, ParsedSource] = {}
        separators: list[tuple[int, int]] = []
        global_cursor = 0

        for source in sources:
            raw: RawParseResult = get_parser(Path(source.path)).parse(Path(source.path))

            if all_parts:
                sep_start = global_cursor
                all_parts.append(self.separator)
                global_cursor += len(self.separator)
                separators.append((sep_start, global_cursor))

            source_blocks: list[TextBlock] = []
            for b in raw.blocks:
                source_blocks.append(TextBlock(
                    text=b["text"],
                    global_start=global_cursor + b["local_start"],
                    global_end=global_cursor + b["local_end"],
                    source_id=source.source_id,
                    local_start=b["local_start"],
                    local_end=b["local_end"],
                    paragraph=b.get("paragraph"),
                    table=b.get("table"),
                    row=b.get("row"),
                    page=b.get("page"),
                    pdf_char_offset_start=b.get("pdf_char_offset_start"),
                    pdf_char_offset_end=b.get("pdf_char_offset_end"),
                ))

            pdf_char_bboxes = [
                PdfCharBBox(
                    char_index=bb["char_index"],
                    page=bb["page"],
                    x0=bb["x0"],
                    top=bb["top"],
                    x1=bb["x1"],
                    bottom=bb["bottom"],
                )
                for bb in raw.pdf_char_bboxes
            ]

            parsed_sources[source.source_id] = ParsedSource(
                source=source,
                format=raw.format,
                full_text=raw.full_text,
                blocks=source_blocks,
                page_count=raw.page_count,
                metadata=raw.metadata or {},
                pdf_char_bboxes=pdf_char_bboxes,
            )

            all_parts.append(raw.full_text)
            global_cursor += len(raw.full_text)
            all_blocks.extend(source_blocks)

        full_text = "".join(all_parts)

        return ParsedDocument(
            full_text=full_text,
            blocks=all_blocks,
            sources=parsed_sources,
            separators=separators,
        )