"""Dependency Injection (DI) container — the composition root.

This is the **only** module in the entire codebase that is allowed to:

* Import concrete classes from ``infrastructure/`` and ``domain/strategies/``.
* Instantiate those classes.
* Wire them together by passing instances through constructors.

Every other module receives dependencies as abstract interfaces defined in
``core/interfaces.py``, achieving complete Inversion of Control (IoC).

Wiring diagram::

    StandardLogger
        |
        +-> PdfPlumberReader(logger)              -> IPDFReader
        +-> ExcelReportGenerator(logger)          -> IPDFGenerator
        +-> OvertimeAttendanceStrategy(logger)    -> IReportStrategy  (Format B)
        +-> SimpleAttendanceStrategy(logger)      -> IReportStrategy  (Format A)
        +-> HebrewAttendanceStrategy(logger)      -> IReportStrategy  (generic)
        |
        +-> ReportRegistry(
        |       strategies=[
        |           OvertimeAttendanceStrategy,   # matched first (most specific)
        |           SimpleAttendanceStrategy,     # matched second
        |           HebrewAttendanceStrategy,     # fallback
        |       ],
        |       logger
        |   )
        |
        +-> ProcessReportUseCase(
                reader    = PdfPlumberReader,
                generator = ExcelReportGenerator,
                registry  = ReportRegistry,
                logger    = StandardLogger,
            )

Usage::

    >>> from container import Container
    >>> container = Container()
    >>> container.process_report_use_case.execute("input.pdf", "output.xlsx")
"""
from __future__ import annotations

from core.logger import StandardLogger
from infrastructure.pdf_reader import PdfPlumberReader
from infrastructure.pdf_generator import ExcelReportGenerator
from domain.strategies.hebrew_attendance_strategy import HebrewAttendanceStrategy
from domain.strategies.simple_attendance_strategy import SimpleAttendanceStrategy
from domain.strategies.overtime_attendance_strategy import OvertimeAttendanceStrategy
from application.registry import ReportRegistry
from application.use_cases.process_report import ProcessReportUseCase


class Container:
    """Composition root that constructs and wires all application dependencies.

    Instantiate once at the application entry point and access fully configured
    objects via its properties.

    All concrete classes are built **eagerly** so that wiring errors surface
    immediately at start-up rather than lazily at first use.

    Example:
        >>> container = Container()
        >>> container.process_report_use_case.execute(
        ...     "april_2025_attendance.pdf",
        ...     "output/april_2025.xlsx",
        ... )
    """

    def __init__(self) -> None:
        # ------------------------------------------------------------------
        # 1. Cross-cutting concerns
        # ------------------------------------------------------------------
        self._logger = StandardLogger(name="pdf_engine")

        # ------------------------------------------------------------------
        # 2. Infrastructure — concrete I/O adapters
        # ------------------------------------------------------------------
        self._reader = PdfPlumberReader(logger=self._logger)
        self._generator = ExcelReportGenerator(logger=self._logger)

        # ------------------------------------------------------------------
        # 3. Domain — concrete strategy implementations
        #    Registration order determines resolution priority:
        #    1. OvertimeAttendanceStrategy — Format B (a_r_9.pdf):   uniquely
        #       identified by "הפסקה", "100%", "125%", "150%" columns.
        #    2. SimpleAttendanceStrategy   — Format A (n_r_5_n.pdf): short
        #       Hebrew column names ("כניסה" / "יציאה" / "יום").
        #    3. HebrewAttendanceStrategy   — generic fallback: full verbose
        #       column names ("שעות כניסה" / "שעת יציאה" / "יום בשבוע").
        # ------------------------------------------------------------------
        self._overtime_strategy = OvertimeAttendanceStrategy(logger=self._logger)
        self._simple_strategy = SimpleAttendanceStrategy(logger=self._logger)
        self._hebrew_attendance_strategy = HebrewAttendanceStrategy(logger=self._logger)

        # ------------------------------------------------------------------
        # 4. Application — registry + use case (pure interfaces from here on)
        # ------------------------------------------------------------------
        self._registry = ReportRegistry(
            strategies=[
                self._overtime_strategy,          # most specific — checked first
                self._simple_strategy,
                self._hebrew_attendance_strategy, # generic fallback
            ],
            logger=self._logger,
        )

        self._process_report_use_case = ProcessReportUseCase(
            reader=self._reader,
            generator=self._generator,
            registry=self._registry,
            logger=self._logger,
        )

        self._logger.debug("Container: all dependencies wired successfully.")

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def process_report_use_case(self) -> ProcessReportUseCase:
        """The fully wired :class:`~application.use_cases.process_report.ProcessReportUseCase`.

        Returns:
            The single shared use-case instance.
        """
        return self._process_report_use_case

    @property
    def registry(self) -> ReportRegistry:
        """The configured :class:`~application.registry.ReportRegistry`.

        Expose to allow callers to register additional strategies at runtime::

            container.registry.register(MyNewStrategy(logger=container.logger))

        Returns:
            The single shared registry instance.
        """
        return self._registry

    @property
    def logger(self) -> StandardLogger:
        """The shared :class:`~core.logger.StandardLogger` instance.

        Returns:
            The application-wide logger.
        """
        return self._logger
