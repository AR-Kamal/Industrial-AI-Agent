"""Knowledge-ingestion exceptions with safe application meanings."""


class KnowledgeBaseError(Exception):
    """Base ingestion exception."""


class UnsupportedDocumentError(KnowledgeBaseError):
    """The file format or content signature is unsupported."""


class DuplicateDocumentError(KnowledgeBaseError):
    """An identical source file is already registered."""


class UnapprovedDocumentError(KnowledgeBaseError):
    """The document has not passed the approval gate."""


class ExtractionError(KnowledgeBaseError):
    """Text extraction failed."""


class ManualReviewRequired(ExtractionError):
    """Extraction cannot safely proceed without human review."""
