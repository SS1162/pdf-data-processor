"""Concrete implementation of :class:`~core.interfaces.ILogger`.

Uses Python's standard :mod:`logging` module so the engine integrates
seamlessly with any existing logging configuration.
"""
from __future__ import annotations

import io
import logging
import sys

from config import LOG_DATE_FMT, LOG_FORMAT, LOG_LEVEL
from core.interfaces import ILogger


class StandardLogger(ILogger):
    """Wraps :class:`logging.Logger` to satisfy the :class:`ILogger` interface.

    A single :class:`~logging.StreamHandler` writing to *stdout* is attached
    when no handlers are already configured, preventing duplicate output when
    the class is instantiated multiple times with the same *name*.

    Args:
        name: Logger name used by :func:`logging.getLogger`.
        level: Minimum log level (default: :data:`~config.LOG_LEVEL`,
            currently ``logging.WARNING``).

    Example:
        >>> logger = StandardLogger(name="my_app")
        >>> logger.warning("Engine started.")
    """

    def __init__(
        self,
        name: str = "pdf_engine",
        level: int = LOG_LEVEL,
    ) -> None:
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            # Wrap stdout in a UTF-8 TextIOWrapper so Hebrew and other non-ASCII
            # characters survive on Windows consoles whose default codepage is
            # not UTF-8 (e.g. cp1255).  errors='replace' prevents fatal crashes
            # for any code point that the terminal cannot render.
            utf8_stream = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
            handler = logging.StreamHandler(utf8_stream)
            handler.setFormatter(
                logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FMT)
            )
            self._logger.addHandler(handler)
        self._logger.setLevel(level)

    # ------------------------------------------------------------------
    # ILogger implementation
    # ------------------------------------------------------------------

    def debug(self, message: str) -> None:
        """Emit a DEBUG-level log entry.

        Args:
            message: Human-readable debug message.
        """
        self._logger.debug(message)

    def info(self, message: str) -> None:
        """Emit an INFO-level log entry.

        Args:
            message: Human-readable informational message.
        """
        self._logger.info(message)

    def warning(self, message: str) -> None:
        """Emit a WARNING-level log entry.

        Args:
            message: Human-readable warning message.
        """
        self._logger.warning(message)

    def error(self, message: str, exc_info: bool = False) -> None:
        """Emit an ERROR-level log entry.

        Args:
            message: Human-readable error description.
            exc_info: When ``True``, the current exception traceback is appended.
        """
        self._logger.error(message, exc_info=exc_info)
