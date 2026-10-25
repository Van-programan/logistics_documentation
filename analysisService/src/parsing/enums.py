from enum import Enum


class DocumentFormat(str, Enum):
    DOCX = "DOCX"
    PDF = "PDF"


class AttachmentType(str, Enum):
    MAIN = "MAIN"
    SPECIFICATION = "SPECIFICATION"
    SCHEDULE = "SCHEDULE"
    ADDENDUM = "ADDENDUM"
    OTHER = "OTHER"