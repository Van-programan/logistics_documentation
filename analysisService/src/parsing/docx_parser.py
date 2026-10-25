from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from src.parsing.document_template import DocumentParser
from src.parsing.models import DocumentFormat, RawParseResult


class DocxParser(DocumentParser):
    format = DocumentFormat.DOCX

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".docx"

    def parse(self, path: Path) -> RawParseResult:
        doc = Document(str(path))

        parts: list[str] = []
        blocks: list[dict] = []
        cursor = 0
        separator = "\n\n"

        paragraph_count = 0
        table_count = 0

        def add_block(text, *, paragraph = None, table = None, row = None):
            nonlocal cursor
            if not text.strip():
                return
            if parts:
                parts.append(separator)
                cursor += len(separator)
            start = cursor
            parts.append(text)
            cursor += len(text)
            blocks.append({
                "text": text,
                "local_start": start,
                "local_end": cursor,
                "paragraph": paragraph,
                "table": table,
                "row": row,
                "page": None,
            })

        def iter_block_items(parent):
            if isinstance(parent, DocxDocument):
                parent_elm = parent.element.body
            elif isinstance(parent, Table):
                parent_elm = parent._tbl
            else:
                raise ValueError("Unsupported parent type")

            for element in parent_elm.iterchildren():
                if isinstance(element, CT_P):
                    yield Paragraph(element, parent)
                elif isinstance(element, CT_Tbl):
                    yield Table(element, parent)

        for block in iter_block_items(doc):
            if isinstance(block, Paragraph):
                add_block(block.text, paragraph=paragraph_count)
                paragraph_count += 1

            elif isinstance(block, Table):
                for row_idx, row in enumerate(block.rows):
                    row_text = " | ".join(cell.text.strip() for cell in row.cells)
                    add_block(row_text, table=table_count, row=row_idx)
                table_count += 1

        return RawParseResult(
            format=DocumentFormat.DOCX,
            full_text="".join(parts),
            blocks=blocks,
            page_count=None,
            metadata={"paragraphs": paragraph_count, "tables": table_count},
        )