"""Central configuration for the PDF processing engine.

All tuneable constants live here so that a single file controls behaviour
across the entire application without touching source code.
"""
import logging

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

#: Format string passed to :class:`logging.Formatter`.
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

#: Date/time format used in log records.
LOG_DATE_FMT: str = "%Y-%m-%d %H:%M:%S"

#: Minimum log level emitted by :class:`~core.logger.StandardLogger`.
#: Set to ``logging.DEBUG`` locally, ``logging.WARNING`` (or higher) in production.
LOG_LEVEL: int = logging.WARNING
