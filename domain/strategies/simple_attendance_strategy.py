"""Concrete :class:`~core.interfaces.IReportStrategy` for the *simple* Hebrew
attendance PDF format (``n_r_5_n.pdf`` family).

Schema identification
---------------------
This format has **6 short-named columns** (all required, order-independent):

    ``["תאריך", "יום", "כניסה", "יציאה", 'סה"כ שעות', "הערות"]``

It is distinguished from the generic Hebrew strategy (which uses the verbose
``"שעות כניסה"`` / ``"שעת יציאה"`` / ``"יום בשבוע"`` names) and from the
overtime strategy by the absence of overtime-percentage columns.
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
# Required column set — uniquely identifies this PDF family
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: Set[str] = {
    "תאריך",
    "יום",
    "כניסה",
    "יציאה",
    'סה"כ שעות',
    "הערות",
}


class SimpleAttendanceStrategy(IReportStrategy):
    """Full processing pipeline for the simple 6-column attendance PDF format.

    Corresponds to the ``n_r_5_n.pdf`` PDF family.  Column headers use short
    Hebrew names (``"כניסה"`` rather than ``"שעות כניסה"`` etc.).

    Args:
        logger: An :class:`~core.interfaces.ILogger` instance, injected by
            :class:`~container.Container`.

    Example:
        >>> strategy = SimpleAttendanceStrategy(logger=my_logger)
        >>> if strategy.can_handle(raw_data):
        ...     strategy.validate(raw_data)
        ...     report = strategy.parse(raw_data)
        ...     result = strategy.transform(report)
    """

    _COL_DATE: str = "תאריך"
    _COL_DAY: str = "יום"
    _COL_ENTRY: str = "כניסה"
    _COL_EXIT: str = "יציאה"
    _COL_TOTAL: str = 'סה"כ שעות'
    _COL_NOTES: str = "הערות"

    def __init__(self, logger: ILogger) -> None:
        self._logger = logger

    # ------------------------------------------------------------------
    # IReportStrategy — public API
    # ------------------------------------------------------------------

    def can_handle(self, raw_data: RawFileData) -> bool:
        """Return ``True`` when *raw_data* contains all six simple Hebrew columns.

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
        """Assert that *raw_data* contains every required simple-format column.

        Args:
            raw_data: Extracted PDF data to validate.

        Returns:
            ``True`` when all required columns are present.

        Raises:
            ValidationError: When one or more required columns are absent.
        """
        header_row, _, _ = self._locate_header_row(raw_data)
        if header_row is None:
            msg = f"No header row found. Required columns: {REQUIRED_COLUMNS}"
            self._logger.error(msg)
            raise ValidationError(msg)

        found: Set[str] = {str(cell).strip() for cell in header_row if cell}
        missing = REQUIRED_COLUMNS - found
        if missing:
            msg = f"SimpleAttendanceStrategy: missing columns: {missing}"
            self._logger.error(msg)
            raise ValidationError(msg)

        return True

    def parse(self, raw_data: RawFileData) -> BaseReportDTO:
        """Parse raw table rows into a :class:`~domain.dtos.report_dtos.ReportDTO`.

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

        headers: List[str] = [str(c).strip() if c else "" for c in header_row]
        col_map: dict[str, int] = {n: i for i, n in enumerate(headers) if n}

        for required in REQUIRED_COLUMNS:
            if required not in col_map:
                msg = f"Required column '{required}' missing from parsed headers: {headers}"
                self._logger.error(msg)
                raise ParseError(msg)

        records: List[AttendanceRecord] = []
        table = raw_data.tables[table_idx]

        for row in table[header_row_idx + 1 :]:
            if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                continue
            date_val = self._cell(row, col_map, self._COL_DATE)
            if not date_val or not any(ch.isdigit() for ch in date_val):
                continue  # skip footer / summary rows

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
            f"SimpleAttendanceStrategy.parse: extracted {len(records)} records."
        )
        return ReportDTO(
            employee_name=self._extract_employee_name(raw_data),
            period=self._extract_period(raw_data),
            headers=headers,
            records=records,
        )

    def transform(self, report: BaseReportDTO) -> BaseProcessedReportDTO:
        """Aggregate totals for a simple-attendance report.

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
                f"SimpleAttendanceStrategy.transform expects ReportDTO, "
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
            f"SimpleAttendanceStrategy.transform: "
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
    # Private helpers
    # ------------------------------------------------------------------

    def _locate_header_row(
        self,
        raw_data: RawFileData,
    ) -> Tuple[Optional[List[Optional[str]]], int, int]:
        """Scan all tables for the first row that contains every required column.

        Args:
            raw_data: Extracted PDF data to search.

        Returns:
            ``(header_row, table_index, row_index)`` or ``(None, -1, -1)``.
        """
        for t_idx, table in enumerate(raw_data.tables):
            for r_idx, row in enumerate(table):
                cell_values: Set[str] = {str(c).strip() for c in row if c}
                if REQUIRED_COLUMNS.issubset(cell_values):
                    return row, t_idx, r_idx
        return None, -1, -1

    @staticmethod
    def _cell(
        row: List[Optional[str]],
        col_map: dict[str, int],
        column_name: str,
    ) -> str:
        """Safely retrieve and strip a cell value by column name."""
        idx = col_map.get(column_name)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx] or "").strip()

    def _extract_employee_name(self, raw_data: RawFileData) -> Optional[str]:
        """Attempt to find the employee name in metadata or pre-header rows.

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
        """Attempt to find the reporting period in metadata or pre-header rows.

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

    @staticmethod
    def _parse_hours(value: str) -> float:
        """Convert an hours string (``"HH:MM"`` or decimal) to a float.

        Args:
            value: Raw hours string from the PDF cell.

        Returns:
            Decimal hours; ``0.0`` for empty or unparseable values.
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
