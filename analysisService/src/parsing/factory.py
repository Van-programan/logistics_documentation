from pathlib import Path

from src.parsing.document_template import DocumentParser
from src.parsing.docx_parser import DocxParser
from src.parsing.pdf_parser import PdfParser


class UnsupportedFormatError(ValueError):
    pass


_PARSERS: list[DocumentParser] = [DocxParser(), PdfParser()]


def get_parser(path: Path) -> DocumentParser:
    for parser in _PARSERS:
        if parser.supports(path):
            return parser
    raise UnsupportedFormatError(f"Неподдерживаемый формат: {path.suffix}")


def parse_file(path: Path):
    return get_parser(path).parse(path)