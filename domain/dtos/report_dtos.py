"""Data Transfer Objects (DTOs) used throughout the processing pipeline.

DTOs are plain Python dataclasses — they carry no business logic and depend on
nothing outside the standard library, keeping them safe to import from any layer.

Pipeline flow::

    PDF file
        │
        v
    RawFileData                  <- produced by IPDFReader.extract()
        │
        v
    BaseReportDTO (subtype)
    +-- ReportDTO                <- Format A/C: simple attendance
    +-- OvertimeReportDTO        <- Format B:   overtime attendance
        │
        v
    BaseProcessedReportDTO (subtype)
    +-- ProcessedReportDTO       <- Format A/C
    +-- OvertimeProcessedReportDTO <- Format B
        │
        v
    Output file                  <- produced by IPDFGenerator.generate()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Marker base classes (support Liskov-safe return types across strategies)
# ---------------------------------------------------------------------------


class BaseReportDTO:
    """Marker base for all parsed-report DTOs.

    Allows :class:`~core.interfaces.IReportStrategy` to declare a single
    return type for :meth:`parse` while concrete strategies return
    format-specific subtypes (covariant return).
    """


class BaseProcessedReportDTO:
    """Marker base for all processed-report DTOs.

    Allows :class:`~core.interfaces.IReportStrategy` to declare a single
    return type for :meth:`transform` and :class:`~core.interfaces.IPDFGenerator`
    to accept any processed-report subtype.
    """


# ---------------------------------------------------------------------------
# Raw extracted data (format-agnostic)
# ---------------------------------------------------------------------------


@dataclass
class RawFileData:
    """Raw, unprocessed data extracted directly from a PDF file.

    Attributes:
        file_path: Absolute path to the source PDF.
        tables: All tables found across all pages.
            Shape: ``tables[table_index][row_index][col_index]``.
            Cell values are ``str | None`` as returned by *pdfplumber*.
        metadata: Arbitrary key/value pairs gathered from the PDF (page count,
            author, creation date, etc.) or injected by the reader for
            downstream use (e.g. ``employee_name``, ``period``).
    """

    file_path: str
    tables: List[List[List[Optional[str]]]]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AttendanceRecord:
    """A single row in the attendance table as parsed from the raw data.

    All fields are kept as raw strings so that no data is inadvertently lost
    during parsing; transformation to typed values happens in the transformer.

    Attributes:
        date: The calendar date of the entry (e.g. ``"01/04/2025"``).
        day_of_week: Hebrew day name (e.g. ``"ראשון"``).
        entry_time: Clock-in time as a string (e.g. ``"08:30"``).
        exit_time: Clock-out time as a string (e.g. ``"17:00"``).
        total_hours: Computed daily total (e.g. ``"8:30"`` or ``"8.5"``).
        notes: Free-text remarks column (``"הערות"``).
    """

    date: str
    day_of_week: str
    entry_time: str
    exit_time: str
    total_hours: str
    notes: str


@dataclass
class ReportDTO(BaseReportDTO):
    """Structured simple-attendance report produced by :meth:`IReportStrategy.parse`.

    Contains typed, cleaned fields ready for business-logic transformation.

    Attributes:
        employee_name: Name of the employee (``None`` if not detectable).
        period: Reporting month/period string (``None`` if not detectable).
        headers: Ordered list of column names as they appear in the source table.
        records: Individual attendance entries in document order.
        metadata: Pass-through bag for any additional context needed by the
            transformer (e.g. department code, contract type).
    """

    employee_name: Optional[str]
    period: Optional[str]
    headers: List[str]
    records: List[AttendanceRecord]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedReportDTO(BaseProcessedReportDTO):
    """Fully processed simple-attendance report, ready for :class:`IPDFGenerator`.

    Attributes:
        employee_name: Name of the employee.
        period: Reporting month/period string.
        records: Attendance records (unchanged from :class:`ReportDTO`).
        total_hours_sum: Aggregate of all daily ``total_hours`` values as a
            decimal float (e.g. ``168.5``).
        working_days: Count of days where at least one of *entry_time* or
            *exit_time* was recorded.
        summary: Key/value summary for quick access in templates/generators.
    """

    employee_name: Optional[str]
    period: Optional[str]
    records: List[AttendanceRecord]
    total_hours_sum: float
    working_days: int
    summary: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Format B: overtime attendance  (a_r_9.pdf)
# ---------------------------------------------------------------------------


@dataclass
class OvertimeRecord:
    """A single row in an overtime-computed attendance table.

    Reflects the extra columns present in the ``a_r_9.pdf`` family of reports.

    Attributes:
        date: The calendar date of the entry.
        day_of_week: Hebrew day name.
        entry_time: Clock-in time.
        exit_time: Clock-out time.
        break_time: Unpaid break duration (e.g. ``"0:30"``).
        total_hours: Net daily total after subtracting break.
        hours_100: Hours billable at the 100 % (regular) rate.
        hours_125: Overtime hours at the 125 % rate.
        hours_150: Overtime hours at the 150 % rate.
        value: Monetary/unit value for the row (``""`` when not printed).
    """

    date: str
    day_of_week: str
    entry_time: str
    exit_time: str
    break_time: str
    total_hours: str
    hours_100: str
    hours_125: str
    hours_150: str
    value: str


@dataclass
class OvertimeReportDTO(BaseReportDTO):
    """Parsed overtime-attendance report produced by :meth:`IReportStrategy.parse`.

    Attributes:
        employee_name: Name of the employee (``None`` if not detectable).
        period: Reporting month/period string (``None`` if not detectable).
        headers: Ordered list of column names as they appear in the source table.
        records: Individual overtime-attendance entries in document order.
        metadata: Pass-through bag for additional transformer context.
    """

    employee_name: Optional[str]
    period: Optional[str]
    headers: List[str]
    records: List[OvertimeRecord]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OvertimeProcessedReportDTO(BaseProcessedReportDTO):
    """Fully processed overtime-attendance report, ready for :class:`IPDFGenerator`.

    Attributes:
        employee_name: Name of the employee.
        period: Reporting month/period string.
        records: Overtime-attendance records.
        total_hours_sum: Aggregate net daily hours.
        hours_100_sum: Total hours at the 100 % (regular) rate.
        hours_125_sum: Total overtime hours at the 125 % rate.
        hours_150_sum: Total overtime hours at the 150 % rate.
        working_days: Count of days with at least one time entry.
        summary: Key/value summary for quick access in templates/generators.
    """

    employee_name: Optional[str]
    period: Optional[str]
    records: List[OvertimeRecord]
    total_hours_sum: float
    hours_100_sum: float
    hours_125_sum: float
    hours_150_sum: float
    working_days: int
    summary: Dict[str, Any] = field(default_factory=dict)
