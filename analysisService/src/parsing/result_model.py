from __future__ import annotations

from dataclasses import dataclass, field
from src.parsing.models import DocumentFormat, ParsedSource, TextBlock

@dataclass
class ParsedDocument:
    full_text: str
    blocks: list[TextBlock] = field(default_factory=list)
    sources: dict[str, ParsedSource] = field(default_factory=dict)
    separators: list[tuple[int, int]] = field(default_factory=list)

    def slice(self, start: int, end: int) -> str:
        return self.full_text[start:end]

    def block_for_position(self, pos: int) -> TextBlock | None:
        for b in self.blocks:
            if b.global_start <= pos < b.global_end:
                return b
        return None

    def blocks_in_range(self, global_start: int, global_end: int) -> list[TextBlock]:
        result = [
            b for b in self.blocks
            if b.global_start < global_end and b.global_end > global_start
        ]
        result.sort(key=lambda b: b.global_start)
        return result

    def export_info(self, global_start: int, global_end: int) -> dict | None:
        if global_start >= global_end:
            return None

        overlapping = self.blocks_in_range(global_start, global_end)
        if not overlapping:
            return None

        segments: list[dict] = []
        seen_sources: set[str] = set()

        for block in overlapping:
            seg_start = max(global_start, block.global_start)
            seg_end = min(global_end, block.global_end)
            if seg_start >= seg_end:
                continue

            source = self.sources.get(block.source_id)
            if source is None:
                continue

            local_start = block.local_start + (seg_start - block.global_start)
            local_end = block.local_start + (seg_end - block.global_start)

            segment: dict = {
                "source_id": block.source_id,
                "format": source.format.value,
                "local_start": local_start,
                "local_end": local_end,
                "global_start": seg_start,
                "global_end": seg_end,
            }

            if source.format == DocumentFormat.DOCX:
                segment["paragraph"] = block.paragraph
                segment["table"] = block.table
                segment["row"] = block.row
            else:
                segment["page"] = block.page
                if block.pdf_char_offset_start is not None:
                    segment["pdf_char_offset_start"] = (
                            block.pdf_char_offset_start + (seg_start - block.global_start)
                    )
                if block.pdf_char_offset_end is not None:
                    segment["pdf_char_offset_end"] = (
                            block.pdf_char_offset_start + (seg_end - block.global_start)
                    )

            segments.append(segment)
            seen_sources.add(block.source_id)

        if not segments:
            return None

        return {
            "segments": segments,
            "source_ids": sorted(seen_sources),
        }