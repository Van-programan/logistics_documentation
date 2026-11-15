from __future__ import annotations

from dataclasses import dataclass, field
from src.parsing.models import ParsedSource, TextBlock

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