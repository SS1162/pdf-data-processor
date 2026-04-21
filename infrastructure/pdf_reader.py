"""Concrete :class:`~core.interfaces.IPDFReader` using *pdfplumber*.

The application layer depends only on :class:`~core.interfaces.IPDFReader`;
this module must **never** be imported by the application or domain layers.
Only :class:`~container.Container` wires it in.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pdfplumber

from core.exceptions import ExtractionError, PDFFileNotFoundError
from core.interfaces import ILogger, IPDFReader
from domain.dtos.report_dtos import RawFileData


class PdfPlumberReader(IPDFReader):
    """Extracts all tables from a PDF using *pdfplumber*.

    *pdfplumber* is chosen because it handles complex PDF table layouts,
    preserves cell boundaries, and returns ``None`` for empty cells instead
    of empty strings — which simplifies downstream validation.

    Args:
        logger: An :class:`~core.interfaces.ILogger` instance injected by the
            :class:`~container.Container`.

    Example:
        >>> reader = PdfPlumberReader(logger=my_logger)
        >>> raw = reader.extract("attendance_april.pdf")
        >>> print(len(raw.tables), "table(s) found")
    """

    def __init__(self, logger: ILogger) -> None:
        self._logger = logger

    # ------------------------------------------------------------------
    # IPDFReader implementation
    # ------------------------------------------------------------------

    def extract(self, file_path: str) -> RawFileData:
        """Open *file_path* and extract every table from every page.

        Uses :meth:`pdfplumber.Page.extract_tables` with default settings.
        Each page may contribute zero or more tables; all are collected into
        a flat ``tables`` list in document order.

        Args:
            file_path: Absolute or relative path to the source PDF.

        Returns:
            A :class:`~domain.dtos.report_dtos.RawFileData` instance where
            ``tables[i][r][c]`` is the string (or ``None``) at
            table *i*, row *r*, column *c*.

        Raises:
            PDFFileNotFoundError: If *file_path* does not resolve to an existing file.
            ExtractionError: If *pdfplumber* raises during PDF parsing.
        """
        if not os.path.isfile(file_path):
            raise PDFFileNotFoundError(f"PDF file not found: '{file_path}'")

        self._logger.info(f"PdfPlumberReader: opening '{file_path}'")

        tables: List[List[List[Optional[str]]]] = []
        metadata: Dict[str, Any] = {}

        try:
            with pdfplumber.open(file_path) as pdf:
                metadata["page_count"] = len(pdf.pages)
                # Harvest safe scalar PDF metadata (title, author, etc.)
                if pdf.metadata:
                    metadata.update(
                        {k: v for k, v in pdf.metadata.items() if isinstance(v, (str, int, float))}
                    )

                for page_num, page in enumerate(pdf.pages, start=1):
                    page_tables = page.extract_tables()
                    if page_tables:
                        tables.extend(page_tables)
                        self._logger.debug(
                            f"  Page {page_num}: {len(page_tables)} table(s) extracted."
                        )
                    else:
                        self._logger.debug(f"  Page {page_num}: no tables detected.")

        except (PDFFileNotFoundError, ExtractionError):
            raise
        except Exception as exc:
            raise ExtractionError(
                f"pdfplumber failed while reading '{file_path}': {exc}"
            ) from exc

        self._logger.info(
            f"PdfPlumberReader: extraction complete — "
            f"{len(tables)} table(s) across {metadata.get('page_count', '?')} page(s)."
        )
        return RawFileData(file_path=file_path, tables=tables, metadata=metadata)
