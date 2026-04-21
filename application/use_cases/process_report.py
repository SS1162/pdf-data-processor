"""The central use-case of the PDF processing engine.

:class:`ProcessReportUseCase` is the sole **orchestrator** of the processing
pipeline.  All of its dependencies are injected through the constructor as
abstract interfaces — it has no knowledge of any concrete implementation and
imports nothing from ``infrastructure/``.

Dependency graph (runtime, wired by :class:`~container.Container`)::

    Container
        ├── PdfPlumberReader  ──► IPDFReader
        ├── ExcelReportGenerator ► IPDFGenerator
        ├── ReportRegistry
        │       └── HebrewAttendanceStrategy ► IReportStrategy
        └── ProcessReportUseCase
                ├── reader:    IPDFReader
                ├── generator: IPDFGenerator
                ├── registry:  ReportRegistry
                └── logger:    ILogger
"""
from __future__ import annotations

from core.interfaces import ILogger, IPDFGenerator, IPDFReader
from application.registry import ReportRegistry


class ProcessReportUseCase:
    """Orchestrates the full PDF → output-file processing pipeline.

    The six-step pipeline is::

        1. reader.extract(input_path)          → RawFileData
        2. registry.resolve(raw_data)          → IReportStrategy
        3. strategy.validate(raw_data)         → bool
        4. strategy.parse(raw_data)            → ReportDTO
        5. strategy.transform(report_dto)      → ProcessedReportDTO
        6. generator.generate(processed_dto)   → output file

    Every dependency is an **interface** defined in ``core/interfaces.py``,
    satisfying the Dependency Inversion Principle and making this class
    trivially testable with mocks.

    Args:
        reader: Concrete implementation of :class:`~core.interfaces.IPDFReader`.
        generator: Concrete implementation of :class:`~core.interfaces.IPDFGenerator`.
        registry: Configured :class:`~application.registry.ReportRegistry` holding
            all registered strategies.
        logger: An :class:`~core.interfaces.ILogger` instance.

    Example:
        >>> use_case = ProcessReportUseCase(reader, generator, registry, logger)
        >>> use_case.execute("reports/april_2025.pdf", "output/april_2025.xlsx")
    """

    def __init__(
        self,
        reader: IPDFReader,
        generator: IPDFGenerator,
        registry: ReportRegistry,
        logger: ILogger,
    ) -> None:
        self._reader = reader
        self._generator = generator
        self._registry = registry
        self._logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, input_path: str, output_path: str) -> None:
        """Run the end-to-end pipeline for a single PDF file.

        Args:
            input_path: Path to the source PDF file.
            output_path: Destination path for the generated output file.

        Raises:
            PDFFileNotFoundError: If *input_path* does not exist.
            ExtractionError: If the PDF cannot be opened or parsed.
            StrategyNotFoundError: If no registered strategy can handle the data.
            ValidationError: If the extracted data fails schema validation.
            ParseError: If the strategy cannot map the raw data to typed DTOs.
            TransformError: If a business-logic transformation rule fails.
            GenerationError: If the output file cannot be written.
        """
        # Step 1 — Extract
        raw_data = self._reader.extract(input_path)

        # Step 2 — Resolve strategy
        strategy = self._registry.resolve(raw_data)

        # Step 3 — Validate
        strategy.validate(raw_data)

        # Step 4 — Parse
        report_dto = strategy.parse(raw_data)

        # Step 5 — Transform
        processed_dto = strategy.transform(report_dto)

        # Step 6 — Generate output
        self._generator.generate(processed_dto, output_path)

        self._logger.info(
            f"ProcessReportUseCase: pipeline complete -> '{output_path}'"
        )
