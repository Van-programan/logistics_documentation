from __future__ import annotations

from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from src.parsing.document_template import DocumentParser
from src.parsing.models import DocumentFormat, RawParseResult


class PdfParser(DocumentParser):
    format = DocumentFormat.PDF

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> RawParseResult:
        parts: list[str] = []
        blocks: list[dict] = []
        pdf_char_bboxes: list[dict] = []

        cursor = 0
        char_cursor = 0
        separator = "\n\n"

        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for page_idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if not text.strip():
                    text = self._fallback_page_text(path, page_idx)
                if not text.strip():
                    continue

                if parts:
                    parts.append(separator)
                    cursor += len(separator)
                    char_cursor += len(separator)

                block_start = cursor
                block_char_start = char_cursor

                parts.append(text)
                cursor += len(text)
                char_cursor += len(text)

                self._collect_char_bboxes(
                    page=page,
                    page_idx=page_idx,
                    page_text=text,
                    char_offset_in_file=block_char_start,
                    pdf_char_bboxes=pdf_char_bboxes,
                )

                blocks.append({
                    "text": text,
                    "local_start": block_start,
                    "local_end": cursor,
                    "paragraph": None,
                    "table": None,
                    "row": None,
                    "page": page_idx,
                    "pdf_char_offset_start": block_char_start,
                    "pdf_char_offset_end": char_cursor,
                })

        return RawParseResult(
            format=DocumentFormat.PDF,
            full_text="".join(parts),
            blocks=blocks,
            page_count=page_count,
            metadata={"pages_with_text": len(blocks)},
            pdf_char_bboxes=pdf_char_bboxes,
        )

    @staticmethod
    def _collect_char_bboxes(page, page_idx: int, page_text: str,
            char_offset_in_file: int, pdf_char_bboxes: list[dict]):

        pos = 0
        matched_indices = set()

        for ch in page.chars:
            ch_text = ch.get("text", "")
            if not ch_text:
                continue

            found = page_text.find(ch_text, pos)
            if found == -1:
                found = page_text.find(ch_text, 0)
                if found == -1 or found in matched_indices:
                    continue

            char_index = char_offset_in_file + found

            pdf_char_bboxes.append({
                "char_index": char_index,
                "page": page_idx,
                "x0": float(ch["x0"]),
                "top": float(ch["top"]),
                "x1": float(ch["x1"]),
                "bottom": float(ch["bottom"]),
            })

            matched_indices.add(found)
            pos = found + len(ch_text)

    @staticmethod
    def _fallback_page_text(path: Path, page_idx: int) -> str:
        try:
            reader = PdfReader(str(path))
            if page_idx < len(reader.pages):
                return reader.pages[page_idx].extract_text() or ""
        except Exception:
            pass
        return ""