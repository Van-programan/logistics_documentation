from dataclasses import dataclass

from src.parsing.enums import AttachmentType


@dataclass
class SourceDocument:
    source_id: str
    file_name: str
    attachment_type: AttachmentType
    path: str