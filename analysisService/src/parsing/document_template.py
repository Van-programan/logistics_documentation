from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.parsing.models import DocumentFormat, RawParseResult


class DocumentParser(ABC):
    format: DocumentFormat

    @abstractmethod
    def supports(self, path: Path) -> bool: ...

    @abstractmethod
    def parse(self, path: Path) -> RawParseResult: ...
