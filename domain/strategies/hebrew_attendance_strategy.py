"""Concrete :class:`~core.interfaces.IReportStrategy` for Hebrew attendance PDFs.

Schema identification
---------------------
A table is considered a Hebrew attendance report when its header row contains
**all** of the following column labels (order-independent):

    ``["הערות", 'סה"כ שעות', "שעת יציאה", "שעות כניסה", "יום בשבוע", "תאריך"]``

The strategy bundles three distinct concerns, each isolated in its own private
method group:

* **Validator** — ``_find_header_row_*``, ``validate()``
* **Parser** — ``parse()``, ``_extract_employee_name()``, ``_extract_period()``
* **Transformer** — ``transform()``, ``_parse_hours()``
"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple

from core.exceptions import ParseError, TransformError, ValidationError
from core.interfaces import ILogger, IReportStrategy
from domain.dtos.report_dtos import (
    AttendanceRecord,
    BaseProcessedReportDTO,
    BaseReportDTO,
    ProcessedReportDTO,
    RawFileData,
    ReportDTO,
)

# ---------------------------------------------------------------------------
# Required column set — 100 % certain identification
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: Set[str] = {
    "הערות",
    'סה"כ שעות',
    "שעת יציאה",
    "שעות כניסה",
    "יום בשבוע",
    "תאריך",
}


class HebrewAttendanceStrategy(IReportStrategy):
    """Full processing pipeline for Hebrew employee-attendance PDF reports.

    Implements :class:`~core.interfaces.IReportStrategy` using three internal
    phases — validate / parse / transform — each delegating to private helpers
    so every phase remains independently testable.

    Args:
        logger: An :class:`~core.interfaces.ILogger` instance injected by the
            :class:`~container.Container`.

    Example:
        >>> strategy = HebrewAttendanceStrategy(logger=my_logger)
        >>> if strategy.can_handle(raw_data):
        ...     strategy.validate(raw_data)
        ...     report = strategy.parse(raw_data)
        ...     result = strategy.transform(report)
    """

    # Column name constants
    _COL_DATE: str = "תאריך"
    _COL_DAY: str = "יום בשבוע"
    _COL_ENTRY: str = "שעות כניסה"
    _COL_EXIT: str = "שעת יציאה"
    _COL_TOTAL: str = 'סה"כ שעות'
    _COL_NOTES: str = "הערות"

    def __init__(self, logger: ILogger) -> None:
        self._logger = logger

    # ------------------------------------------------------------------
    # IReportStrategy — public API
    # ------------------------------------------------------------------

    def can_handle(self, raw_data: RawFileData) -> bool:
        """Return ``True`` when *raw_data* contains all required Hebrew columns.

        Args:
            raw_data: Extracted PDF data to inspect.

        Returns:
            ``True`` if the strategy recognises the schema; ``False`` on any
            error or missing column (never raises).
        """
        try:
            header_row, _, _ = self._locate_header_row(raw_data)
            return header_row is not None
        except Exception:
            return False

    def validate(self, raw_data: RawFileData) -> bool:
        """Assert that *raw_data* contains every required Hebrew column header.

        Args:
            raw_data: Extracted PDF data to validate.

        Returns:
            ``True`` when all required columns are present.

        Raises:
            ValidationError: When one or more required columns are absent.
        """
        header_row, _, _ = self._locate_header_row(raw_data)
        if header_row is None:
            msg = f"No table header row found. Required columns: {REQUIRED_COLUMNS}"
            self._logger.error(msg)
            raise ValidationError(msg)

        found: Set[str] = {str(cell).strip() for cell in header_row if cell}
        missing = REQUIRED_COLUMNS - found
        if missing:
            msg = f"Schema validation failed. Missing columns: {missing}"
            self._logger.error(msg)
            raise ValidationError(msg)

        return True

    def parse(self, raw_data: RawFileData) -> BaseReportDTO:
        """Parse raw table rows into a typed :class:`~domain.dtos.report_dtos.ReportDTO`.

        Args:
            raw_data: Validated, extracted PDF data.

        Returns:
            A :class:`~domain.dtos.report_dtos.ReportDTO` with every attendance
            row mapped to an :class:`~domain.dtos.report_dtos.AttendanceRecord`.

        Raises:
            ParseError: When the header row or a required column cannot be found.
        """
        header_row, table_idx, header_row_idx = self._locate_header_row(raw_data)
        if header_row is None:
            msg = "parse() called without a valid header row in raw data."
            self._logger.error(msg)
            raise ParseError(msg)

        headers: List[str] = [str(cell).strip() if cell else "" for cell in header_row]
        col_map: dict[str, int] = {
            name: idx for idx, name in enumerate(headers) if name
        }

        # Guard — every required column must map to an index
        for required in REQUIRED_COLUMNS:
            if required not in col_map:
                msg = f"Required column '{required}' not in parsed headers: {headers}"
                self._logger.error(msg)
                raise ParseError(msg)

        records: List[AttendanceRecord] = []
        table = raw_data.tables[table_idx]

        for row in table[header_row_idx + 1 :]:
            if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                continue  # skip blank / separator rows

            date_val = self._cell(row, col_map, self._COL_DATE)
            # Skip footer / summary rows that contain no recognisable date digits
            if not date_val or not any(ch.isdigit() for ch in date_val):
                continue

            records.append(
                AttendanceRecord(
                    date=date_val,
                    day_of_week=self._cell(row, col_map, self._COL_DAY),
                    entry_time=self._cell(row, col_map, self._COL_ENTRY),
                    exit_time=self._cell(row, col_map, self._COL_EXIT),
                    total_hours=self._cell(row, col_map, self._COL_TOTAL),
                    notes=self._cell(row, col_map, self._COL_NOTES),
                )
            )

        self._logger.info(
            f"HebrewAttendanceStrategy.parse: extracted {len(records)} attendance records."
        )
        return ReportDTO(
            employee_name=self._extract_employee_name(raw_data),
            period=self._extract_period(raw_data),
            headers=headers,
            records=records,
        )

    def transform(self, report: BaseReportDTO) -> BaseProcessedReportDTO:
        """Aggregate totals and enrich the parsed report with summary statistics.

        Args:
            report: A :class:`~domain.dtos.report_dtos.ReportDTO` returned by
                :meth:`parse`.

        Returns:
            A :class:`~domain.dtos.report_dtos.ProcessedReportDTO` with
            ``total_hours_sum`` and ``working_days`` computed.

        Raises:
            TransformError: When an unrecoverable error occurs during aggregation.
        """
        if not isinstance(report, ReportDTO):
            msg = (
                f"HebrewAttendanceStrategy.transform expects ReportDTO, "
                f"got {type(report).__name__}"
            )
            self._logger.error(msg)
            raise TransformError(msg)
        try:
            total_hours: float = sum(
                self._parse_hours(r.total_hours) for r in report.records
            )
            working_days: int = sum(
                1 for r in report.records if r.entry_time or r.exit_time
            )
        except Exception as exc:
            msg = f"Aggregation failed: {exc}"
            self._logger.error(msg, exc_info=True)
            raise TransformError(msg) from exc

        self._logger.info(
            f"HebrewAttendanceStrategy.transform: "
            f"total_hours={total_hours:.2f}, working_days={working_days}."
        )
        return ProcessedReportDTO(
            employee_name=report.employee_name,
            period=report.period,
            records=report.records,
            total_hours_sum=round(total_hours, 2),
            working_days=working_days,
            summary={
                "total_hours": total_hours,
                "working_days": working_days,
                "employee": report.employee_name,
                "period": report.period,
                "record_count": len(report.records),
            },
        )

    # ------------------------------------------------------------------
    # Private — Validator helpers
    # ------------------------------------------------------------------

    def _locate_header_row(
        self,
        raw_data: RawFileData,
    ) -> Tuple[Optional[List[Optional[str]]], int, int]:
        """Scan all tables for the first row that contains every required column.

        Args:
            raw_data: Extracted PDF data to search.

        Returns:
            A ``(header_row, table_index, row_index)`` tuple.
            Returns ``(None, -1, -1)`` when no matching row is found.
        """
        for t_idx, table in enumerate(raw_data.tables):
            for r_idx, row in enumerate(table):
                cell_values: Set[str] = {
                    str(cell).strip() for cell in row if cell
                }
                if REQUIRED_COLUMNS.issubset(cell_values):
                    return row, t_idx, r_idx
        return None, -1, -1

    # ------------------------------------------------------------------
    # Private — Parser helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cell(
        row: List[Optional[str]],
        col_map: dict[str, int],
        column_name: str,
    ) -> str:
        """Safely retrieve and strip a cell value by column name.

        Args:
            row: A single table row.
            col_map: Mapping of column name → column index.
            column_name: The column to retrieve.

        Returns:
            The stripped string value, or ``""`` when the cell is absent/empty.
        """
        idx = col_map.get(column_name)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx] or "").strip()

    def _extract_employee_name(self, raw_data: RawFileData) -> Optional[str]:
        """Attempt to locate the employee name from metadata or pre-header rows.

        Checks :attr:`~domain.dtos.report_dtos.RawFileData.metadata` first,
        then scans the first five rows of every table for a cell containing
        the Hebrew keyword ``"שם"`` and returns the next adjacent cell.

        Args:
            raw_data: Extracted PDF data.

        Returns:
            Employee name string, or ``None`` if not detectable.
        """
        name = raw_data.metadata.get("employee_name")
        if name:
            return str(name)

        for table in raw_data.tables:
            for row in table[:5]:
                for col_idx, cell in enumerate(row):
                    if cell and "שם" in str(cell):
                        if col_idx + 1 < len(row) and row[col_idx + 1]:
                            return str(row[col_idx + 1]).strip()
        return None

    def _extract_period(self, raw_data: RawFileData) -> Optional[str]:
        """Attempt to locate the reporting period from metadata or pre-header rows.

        Checks :attr:`~domain.dtos.report_dtos.RawFileData.metadata` first,
        then scans for cells containing the keywords ``"חודש"`` or ``"תקופה"``.

        Args:
            raw_data: Extracted PDF data.

        Returns:
            Period string, or ``None`` if not detectable.
        """
        period = raw_data.metadata.get("period")
        if period:
            return str(period)

        for table in raw_data.tables:
            for row in table[:5]:
                for col_idx, cell in enumerate(row):
                    if cell and ("חודש" in str(cell) or "תקופה" in str(cell)):
                        if col_idx + 1 < len(row) and row[col_idx + 1]:
                            return str(row[col_idx + 1]).strip()
        return None

    # ------------------------------------------------------------------
    # Private — Transformer helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_hours(value: str) -> float:
        """Convert a hours string to a decimal float.

        Supports both ``"HH:MM"`` (clock format) and decimal strings such as
        ``"8.5"``.

        Args:
            value: Raw hours string from the PDF cell.

        Returns:
            Decimal hours as a ``float``; ``0.0`` for empty or unparseable values.
        """
        value = value.strip()
        if not value:
            return 0.0
        try:
            if ":" in value:
                parts = value.split(":")
                return int(parts[0]) + int(parts[1]) / 60.0
            return float(value)
        except (ValueError, IndexError):
            return 0.0
