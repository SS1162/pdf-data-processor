"""Concrete IReportStrategy implementations."""

from domain.strategies.hebrew_attendance_strategy import HebrewAttendanceStrategy
from domain.strategies.overtime_attendance_strategy import OvertimeAttendanceStrategy
from domain.strategies.simple_attendance_strategy import SimpleAttendanceStrategy

__all__ = [
    "HebrewAttendanceStrategy",
    "OvertimeAttendanceStrategy",
    "SimpleAttendanceStrategy",
]
