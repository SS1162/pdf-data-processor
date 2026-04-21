"""Concrete :class:`~core.interfaces.IReportStrategy` for the *overtime*
Hebrew attendance PDF format (``a_r_9.pdf`` family).

Schema identification
---------------------
This format has **10 columns** including overtime-percentage buckets and a
break-time column:

    ``["תאריך", "יום בשבוע", "כניסה", "יציאה", "הפסקה", 'סה"כ', "100%", "125%", "150%", "שווי"]``

Unique identifiers that cannot appear in other formats:
``"הפסקה"`` (break), ``"100%"``, ``"125%"``, ``"150%"`` — these are checked
in :attr:`REQUIRED_COLUMNS` to guarantee unambiguous detection.

Summary block
-------------
The PDF also includes a summary table at the bottom with rows keyed by labels
such as ``'שעות 100%'``, ``'שעות 125%'``, ``'שעות 150%'``.  These are
extracted and stored in :attr:`OvertimeProcessedReportDTO.summary` when found.
"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple

from core.exceptions import ParseError, TransformError, ValidationError
from core.interfaces import ILogger, IReportStrategy
from domain.dtos.report_dtos import (
    BaseProcessedReportDTO,
    BaseReportDTO,
    OvertimeProcessedReportDTO,
    OvertimeRecord,
    OvertimeReportDTO,
    RawFileData,
)

# ---------------------------------------------------------------------------
# Required column set — uniquely identifies this PDF family
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: Set[str] = {
    "תאריך",
    "כניסה",
    "יציאה",
    "הפסקה",
    'סה"כ',
    "100%",
    "125%",
    "150%",
}

# The day-of-week column name can vary between report generators
_DAY_COLUMN_CANDIDATES: List[str] = ["יום בשבוע", "יום"]


class OvertimeAttendanceStrategy(IReportStrategy):
    """Full processing pipeline for the 10-column overtime attendance PDF format.

    Corresponds to the ``a_r_9.pdf`` PDF family.  Beyond the standard clock-in /
    clock-out times it records a break duration, net daily total, and splits
    worked hours into 100 % / 125 % / 150 % overtime buckets.

    Args:
        logger: An :class:`~core.interfaces.ILogger` instance, injected by
            :class:`~container.Container`.

    Example:
        >>> strategy = OvertimeAttendanceStrategy(logger=my_logger)
        >>> if strategy.can_handle(raw_data):
        ...     strategy.validate(raw_data)
        ...     report = strategy.parse(raw_data)
        ...     result = strategy.transform(report)
    """

    _COL_DATE: str = "תאריך"
    _COL_ENTRY: str = "כניסה"
    _COL_EXIT: str = "יציאה"
    _COL_BREAK: str = "הפסקה"
    _COL_TOTAL: str = 'סה"כ'
    _COL_100: str = "100%"
    _COL_125: str = "125%"
    _COL_150: str = "150%"
    _COL_VALUE: str = "שווי"

    def __init__(self, logger: ILogger) -> None:
        self._logger = logger

    # ------------------------------------------------------------------
    # IReportStrategy — public API
    # ------------------------------------------------------------------

    def can_handle(self, raw_data: RawFileData) -> bool:
        """Return ``True`` when *raw_data* contains the overtime-specific columns.

        Checks for the presence of ``"הפסקה"``, ``"100%"``, ``"125%"``,
        ``"150%"`` in addition to the common time-entry columns.

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
        """Assert that *raw_data* contains every required overtime column.

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

        found: Set[str] = {str(c).strip() for c in header_row if c}
        missing = REQUIRED_COLUMNS - found
        if missing:
            msg = f"OvertimeAttendanceStrategy: missing columns: {missing}"
            self._logger.error(msg)
            raise ValidationError(msg)

        return True

    def parse(self, raw_data: RawFileData) -> BaseReportDTO:
        """Parse raw table rows into an :class:`~domain.dtos.report_dtos.OvertimeReportDTO`.

        Automatically detects whether the day-of-week column is named
        ``"יום בשבוע"`` or ``"יום"`` and maps it accordingly.

        Args:
            raw_data: Validated, extracted PDF data.

        Returns:
            An :class:`~domain.dtos.report_dtos.OvertimeReportDTO` with every
            attendance row mapped to an
            :class:`~domain.dtos.report_dtos.OvertimeRecord`.

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

        # Resolve the day-of-week column dynamically
        day_col: str = self._resolve_day_column(col_map)

        records: List[OvertimeRecord] = []
        table = raw_data.tables[table_idx]

        for row in table[header_row_idx + 1 :]:
            if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                continue
            date_val = self._cell(row, col_map, self._COL_DATE)
            if not date_val or not any(ch.isdigit() for ch in date_val):
                continue  # skip footer / summary rows

            records.append(
                OvertimeRecord(
                    date=date_val,
                    day_of_week=self._cell(row, col_map, day_col),
                    entry_time=self._cell(row, col_map, self._COL_ENTRY),
                    exit_time=self._cell(row, col_map, self._COL_EXIT),
                    break_time=self._cell(row, col_map, self._COL_BREAK),
                    total_hours=self._cell(row, col_map, self._COL_TOTAL),
                    hours_100=self._cell(row, col_map, self._COL_100),
                    hours_125=self._cell(row, col_map, self._COL_125),
                    hours_150=self._cell(row, col_map, self._COL_150),
                    value=self._cell(row, col_map, self._COL_VALUE),
                )
            )

        self._logger.info(
            f"OvertimeAttendanceStrategy.parse: extracted {len(records)} records."
        )
        return OvertimeReportDTO(
            employee_name=self._extract_employee_name(raw_data),
            period=self._extract_period(raw_data),
            headers=headers,
            records=records,
        )

    def transform(self, report: BaseReportDTO) -> BaseProcessedReportDTO:
        """Aggregate totals and overtime-bucket sums for the report.

        Args:
            report: An :class:`~domain.dtos.report_dtos.OvertimeReportDTO`
                returned by :meth:`parse`.

        Returns:
            An :class:`~domain.dtos.report_dtos.OvertimeProcessedReportDTO`
            with ``total_hours_sum``, ``hours_100_sum``, ``hours_125_sum``,
            ``hours_150_sum``, and ``working_days`` computed.

        Raises:
            TransformError: When an unrecoverable error occurs during aggregation.
        """
        if not isinstance(report, OvertimeReportDTO):
            msg = (
                f"OvertimeAttendanceStrategy.transform expects OvertimeReportDTO, "
                f"got {type(report).__name__}"
            )
            self._logger.error(msg)
            raise TransformError(msg)
        try:
            ph = self._parse_hours
            total_hours: float = sum(ph(r.total_hours) for r in report.records)
            hours_100: float = sum(ph(r.hours_100) for r in report.records)
            hours_125: float = sum(ph(r.hours_125) for r in report.records)
            hours_150: float = sum(ph(r.hours_150) for r in report.records)
            working_days: int = sum(
                1 for r in report.records
                if r.entry_time or r.exit_time
            )
        except Exception as exc:
            msg = f"Aggregation failed: {exc}"
            self._logger.error(msg, exc_info=True)
            raise TransformError(msg) from exc

        self._logger.info(
            f"OvertimeAttendanceStrategy.transform: total={total_hours:.2f}h, "
            f"100%={hours_100:.2f}h, 125%={hours_125:.2f}h, "
            f"150%={hours_150:.2f}h, working_days={working_days}."
        )
        return OvertimeProcessedReportDTO(
            employee_name=report.employee_name,
            period=report.period,
            records=report.records,
            total_hours_sum=round(total_hours, 2),
            hours_100_sum=round(hours_100, 2),
            hours_125_sum=round(hours_125, 2),
            hours_150_sum=round(hours_150, 2),
            working_days=working_days,
            summary={
                "total_hours": total_hours,
                "hours_100": hours_100,
                "hours_125": hours_125,
                "hours_150": hours_150,
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
        """Scan all tables for the first row that contains every required overtime column.

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
    def _resolve_day_column(col_map: dict[str, int]) -> str:
        """Return the first candidate day-column name that is present in *col_map*.

        Falls back to ``"יום"`` if none of the candidates match.

        Args:
            col_map: Mapping of column header name -> column index.

        Returns:
            Resolved column name string.
        """
        for candidate in _DAY_COLUMN_CANDIDATES:
            if candidate in col_map:
                return candidate
        return _DAY_COLUMN_CANDIDATES[-1]

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
