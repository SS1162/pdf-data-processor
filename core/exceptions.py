"""Domain-specific exceptions for the PDF processing engine.

All exceptions are subclasses of :class:`PDFProcessingError`, allowing callers
to catch the entire family with a single ``except PDFProcessingError`` clause
while still being able to handle fine-grained cases individually.
"""


class PDFProcessingError(Exception):
    """Base exception for all PDF processing engine errors."""


class PDFFileNotFoundError(PDFProcessingError):
    """Raised when the input PDF file path does not exist on disk."""


class ExtractionError(PDFProcessingError):
    """Raised when pdfplumber (or another reader) fails to open or parse a PDF."""


class ValidationError(PDFProcessingError):
    """Raised when extracted data fails schema validation (e.g. missing columns)."""


class StrategyNotFoundError(PDFProcessingError):
    """Raised when no registered :class:`~core.interfaces.IReportStrategy` can
    handle the provided :class:`~domain.dtos.report_dtos.RawFileData`."""


class ParseError(PDFProcessingError):
    """Raised when the strategy cannot map raw table data to a typed DTO."""


class TransformError(PDFProcessingError):
    """Raised when a business-logic transformation rule cannot be applied."""


class GenerationError(PDFProcessingError):
    """Raised when the output file cannot be created or written."""
