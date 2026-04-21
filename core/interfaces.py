"""Abstract Base Classes (interfaces / ports) for every layer.

All application and infrastructure code must depend on these abstractions,
never on concrete implementations — enforcing the Dependency Inversion Principle.

Imports of domain DTOs are guarded by ``TYPE_CHECKING`` so that the core layer
retains *zero* runtime dependencies on outer layers (strict Clean Architecture).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from domain.dtos.report_dtos import (
        BaseProcessedReportDTO,
        BaseReportDTO,
        ProcessedReportDTO,
        RawFileData,
        ReportDTO,
    )


# ---------------------------------------------------------------------------
# Logging interface
# ---------------------------------------------------------------------------


class ILogger(ABC):
    """Contract for structured logging across all layers."""

    @abstractmethod
    def warning(self, message: str) -> None:
        """Emit a WARNING-level log entry.

        Args:
            message: Human-readable warning message.
        """

    @abstractmethod
    def error(self, message: str, exc_info: bool = False) -> None:
        """Emit an ERROR-level log entry.

        Args:
            message: Human-readable error description.
            exc_info: When ``True``, attach the current exception traceback.
        """


# ---------------------------------------------------------------------------
# PDF Reader interface
# ---------------------------------------------------------------------------


class IPDFReader(ABC):
    """Contract for extracting raw tabular data from a PDF source file."""

    @abstractmethod
    def extract(self, file_path: str) -> "RawFileData":
        """Open *file_path* and return all tables found within it.

        Args:
            file_path: Absolute or relative path to the source PDF.

        Returns:
            A :class:`~domain.dtos.report_dtos.RawFileData` instance containing
            the extracted tables and file-level metadata.

        Raises:
            PDFFileNotFoundError: If *file_path* does not exist.
            ExtractionError: If the PDF cannot be opened or parsed.
        """


# ---------------------------------------------------------------------------
# Report Strategy interface
# ---------------------------------------------------------------------------


class IReportStrategy(ABC):
    """Contract for a fully self-contained report-processing pipeline.

    A concrete strategy bundles:
    - **Schema validation** — ``validate()``
    - **Structural parsing** — ``parse()``
    - **Business-logic transformation** — ``transform()``

    The :class:`~application.registry.ReportRegistry` queries ``can_handle()``
    to select the correct strategy at runtime without coupling the use-case to
    any specific implementation.
    """

    @abstractmethod
    def can_handle(self, raw_data: "RawFileData") -> bool:
        """Return ``True`` when this strategy is capable of processing *raw_data*.

        Args:
            raw_data: Extracted PDF data to inspect.

        Returns:
            ``True`` if the strategy recognises the data schema; ``False``
            otherwise. Must not raise.
        """

    @abstractmethod
    def validate(self, raw_data: "RawFileData") -> bool:
        """Assert that *raw_data* conforms to the expected schema.

        Args:
            raw_data: Extracted PDF data to validate.

        Returns:
            ``True`` when validation succeeds.

        Raises:
            ValidationError: When required columns are absent or malformed.
        """

    @abstractmethod
    def parse(self, raw_data: "RawFileData") -> "BaseReportDTO":
        """Convert *raw_data* into a structured, typed DTO.

        Args:
            raw_data: Validated, extracted PDF data.

        Returns:
            A :class:`~domain.dtos.report_dtos.BaseReportDTO` subtype
            (:class:`~domain.dtos.report_dtos.ReportDTO` for simple formats,
            :class:`~domain.dtos.report_dtos.OvertimeReportDTO` for overtime).

        Raises:
            ParseError: When the data cannot be mapped to the expected structure.
        """

    @abstractmethod
    def transform(self, report: "BaseReportDTO") -> "BaseProcessedReportDTO":
        """Apply business-logic transformations to produce an output-ready DTO.

        Args:
            report: Parsed report data (a :class:`~domain.dtos.report_dtos.BaseReportDTO`
                subtype returned by :meth:`parse`).

        Returns:
            A :class:`~domain.dtos.report_dtos.BaseProcessedReportDTO` subtype
            enriched with computed fields (totals, overtime sums, etc.).

        Raises:
            TransformError: When a transformation rule cannot be applied.
        """


# ---------------------------------------------------------------------------
# PDF / Report Generator interface
# ---------------------------------------------------------------------------


class IPDFGenerator(ABC):
    """Contract for writing a processed report to an output file."""

    @abstractmethod
    def generate(self, data: "BaseProcessedReportDTO", output_path: str) -> None:
        """Persist *data* to the file at *output_path*.

        Args:
            data: Fully processed report data (any
                :class:`~domain.dtos.report_dtos.BaseProcessedReportDTO` subtype)
                ready for serialisation.
            output_path: Destination file path (format inferred from extension).

        Raises:
            GenerationError: If the file cannot be written.
        """
