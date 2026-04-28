"""Lean pytest suite for the PDF data-processor pipeline.

Coverage pillars
----------------
1. Classification   — registry selects the correct strategy per report type.
2. Core Logic       — `_parse_hours` determinism; `total_hours_sum` == Σ daily hours.
3. End-Time Rule    — parsed exit_time is chronologically later than entry_time.
4. Structure Integrity — output headers preserve input column order (integration).
5. Edge Case        — empty report (header only) does not crash and yields zero totals.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.registry import ReportRegistry
from core.exceptions import StrategyNotFoundError
from domain.dtos.report_dtos import (
    AttendanceRecord,
    RawFileData,
    ReportDTO,
)
from domain.strategies.hebrew_attendance_strategy import (
    HebrewAttendanceStrategy,
)
from domain.strategies.overtime_attendance_strategy import (
    OvertimeAttendanceStrategy,
)
from domain.strategies.simple_attendance_strategy import (
    SimpleAttendanceStrategy,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _null_logger() -> MagicMock:
    """Return a silent mock that satisfies ILogger."""
    return MagicMock()


def _raw_data_for(columns: list[str], data_rows: list[list[str | None]] | None = None) -> RawFileData:
    """Build a minimal RawFileData containing one table.

    The table has the given header row followed by *data_rows* (empty by default).
    Every column that appears in *columns* is included in document order.
    """
    table: list[list[str | None]] = [columns]
    if data_rows:
        table.extend(data_rows)
    return RawFileData(file_path="dummy.pdf", tables=[table])


# ---------------------------------------------------------------------------
# 1. Classification — registry resolves the right strategy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "strategy_cls, columns",
    [
        (
            HebrewAttendanceStrategy,
            ["תאריך", "יום בשבוע", "שעות כניסה", "שעת יציאה", 'סה"כ שעות', "הערות"],
        ),
        (
            SimpleAttendanceStrategy,
            ["תאריך", "יום", "כניסה", "יציאה", 'סה"כ שעות', "הערות"],
        ),
        (
            OvertimeAttendanceStrategy,
            ["תאריך", "יום בשבוע", "כניסה", "יציאה", "הפסקה", 'סה"כ', "100%", "125%", "150%", "שווי"],
        ),
    ],
    ids=["hebrew", "simple", "overtime"],
)
def test_registry_resolves_correct_strategy(strategy_cls, columns):
    """Registry must select the matching strategy and no other."""
    logger = _null_logger()
    strategies = [
        HebrewAttendanceStrategy(logger),
        SimpleAttendanceStrategy(logger),
        OvertimeAttendanceStrategy(logger),
    ]
    registry = ReportRegistry(strategies=strategies, logger=logger)
    raw = _raw_data_for(columns)

    resolved = registry.resolve(raw)

    assert isinstance(resolved, strategy_cls)


def test_registry_raises_when_no_strategy_matches():
    """Registry must raise StrategyNotFoundError for an unrecognised schema."""
    logger = _null_logger()
    registry = ReportRegistry(
        strategies=[
            HebrewAttendanceStrategy(logger),
            SimpleAttendanceStrategy(logger),
            OvertimeAttendanceStrategy(logger),
        ],
        logger=logger,
    )
    raw = _raw_data_for(["col_a", "col_b", "col_c"])

    with pytest.raises(StrategyNotFoundError):
        registry.resolve(raw)


# ---------------------------------------------------------------------------
# 2. Core Logic — _parse_hours (the deterministic brain)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_value, expected",
    [
        ("8:30", 8.5),          # HH:MM clock format
        ("8.5", 8.5),           # decimal string
        ("0:00", 0.0),          # midnight / zero entry
        ("", 0.0),              # empty cell → safe zero
        ("N/A", 0.0),           # unparseable text → safe zero
    ],
    ids=["hh_mm", "decimal", "zero_time", "empty", "garbage"],
)
def test_parse_hours_returns_correct_float(raw_value, expected):
    """_parse_hours must convert every recognised format to the right decimal."""
    strategy = HebrewAttendanceStrategy(_null_logger())
    assert strategy._parse_hours(raw_value) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 3. Core Logic — total_hours_sum == Σ daily hours
# ---------------------------------------------------------------------------

def test_transform_total_hours_equals_sum_of_daily_records():
    """transform() must produce total_hours_sum that matches the arithmetic sum
    of every record's individual total_hours after _parse_hours conversion."""
    strategy = HebrewAttendanceStrategy(_null_logger())

    records = [
        AttendanceRecord(date="01/04/2025", day_of_week="ראשון",
                         entry_time="08:00", exit_time="17:00",
                         total_hours="9:00", notes=""),
        AttendanceRecord(date="02/04/2025", day_of_week="שני",
                         entry_time="08:30", exit_time="16:30",
                         total_hours="8:00", notes=""),
        AttendanceRecord(date="03/04/2025", day_of_week="שלישי",
                         entry_time="09:00", exit_time="18:00",
                         total_hours="9.5", notes=""),
    ]
    expected_sum = sum(strategy._parse_hours(r.total_hours) for r in records)

    report = ReportDTO(
        employee_name="ישראל ישראלי",
        period="אפריל 2025",
        headers=["תאריך", "יום בשבוע", "שעות כניסה", "שעת יציאה", 'סה"כ שעות', "הערות"],
        records=records,
    )
    result = strategy.transform(report)

    assert result.total_hours_sum == pytest.approx(expected_sum, abs=1e-9)
    assert result.working_days == 3


# ---------------------------------------------------------------------------
# 4. Core Logic — End Time > Start Time
# ---------------------------------------------------------------------------

def test_parsed_records_have_exit_time_after_entry_time():
    """After parsing, every data row's exit_time must be chronologically later
    than its entry_time.  This validates that the column-mapping logic has not
    swapped the two time columns."""
    logger = _null_logger()
    strategy = HebrewAttendanceStrategy(logger)

    columns = ["תאריך", "יום בשבוע", "שעות כניסה", "שעת יציאה", 'סה"כ שעות', "הערות"]
    data_rows = [
        ["01/04/2025", "ראשון", "08:00", "17:00", "9:00", ""],
        ["02/04/2025", "שני",   "09:00", "18:30", "9:30", ""],
    ]
    raw = _raw_data_for(columns, data_rows)

    report = strategy.parse(raw)

    for record in report.records:
        entry_parts = record.entry_time.split(":")
        exit_parts  = record.exit_time.split(":")
        entry_minutes = int(entry_parts[0]) * 60 + int(entry_parts[1])
        exit_minutes  = int(exit_parts[0])  * 60 + int(exit_parts[1])
        assert exit_minutes > entry_minutes, (
            f"exit_time {record.exit_time!r} is not after entry_time {record.entry_time!r}"
        )


# ---------------------------------------------------------------------------
# 5. Structure Integrity — output headers preserve input column order
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "strategy_cls, columns",
    [
        (
            HebrewAttendanceStrategy,
            ["תאריך", "יום בשבוע", "שעות כניסה", "שעת יציאה", 'סה"כ שעות', "הערות"],
        ),
        (
            SimpleAttendanceStrategy,
            ["תאריך", "יום", "כניסה", "יציאה", 'סה"כ שעות', "הערות"],
        ),
        (
            OvertimeAttendanceStrategy,
            ["תאריך", "יום בשבוע", "כניסה", "יציאה", "הפסקה", 'סה"כ', "100%", "125%", "150%", "שווי"],
        ),
    ],
    ids=["hebrew", "simple", "overtime"],
)
def test_parsed_headers_match_input_column_order(strategy_cls, columns):
    """The parsed report's headers list must exactly mirror the source column
    order — guaranteeing that the output PDF will carry identical column names
    in the same sequence as the input."""
    strategy = strategy_cls(_null_logger())
    raw = _raw_data_for(columns)

    report = strategy.parse(raw)

    assert report.headers == columns


# ---------------------------------------------------------------------------
# 6. Edge Case — empty report (header row only, no data rows)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "strategy_cls, columns",
    [
        (
            HebrewAttendanceStrategy,
            ["תאריך", "יום בשבוע", "שעות כניסה", "שעת יציאה", 'סה"כ שעות', "הערות"],
        ),
        (
            SimpleAttendanceStrategy,
            ["תאריך", "יום", "כניסה", "יציאה", 'סה"כ שעות', "הערות"],
        ),
    ],
    ids=["hebrew_empty", "simple_empty"],
)
def test_empty_report_does_not_crash_and_yields_zero_totals(strategy_cls, columns):
    """An attendance PDF with a header row but no data rows must not raise and
    must produce zero totals — never a division-by-zero or AttributeError."""
    strategy = strategy_cls(_null_logger())
    raw = _raw_data_for(columns)  # no data rows

    report = strategy.parse(raw)
    result = strategy.transform(report)

    assert result.total_hours_sum == 0.0
    assert result.working_days == 0
    assert len(report.records) == 0
