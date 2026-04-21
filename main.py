"""CLI entry point for the PDF processing engine.

Usage::

    python main.py <input_pdf> <output_xlsx>

Example::

    python main.py reports/april_2025.pdf output/april_2025.xlsx
"""
from __future__ import annotations

import argparse
import sys

from container import Container
from core.exceptions import PDFProcessingError


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-engine",
        description="PDF attendance report processing engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py reports/april_2025.pdf output/april_2025.xlsx\n"
        ),
    )
    parser.add_argument(
        "input",
        metavar="INPUT_PDF",
        help="Path to the source PDF attendance report.",
    )
    parser.add_argument(
        "output",
        metavar="OUTPUT_FILE",
        help="Destination path for the generated Excel report (.xlsx).",
    )
    return parser


def main() -> int:
    """Parse CLI arguments, wire dependencies, and execute the pipeline.

    Returns:
        ``0`` on success, ``1`` on any handled error.
    """
    args = _build_arg_parser().parse_args()

    container = Container()
    logger = container.logger

    try:
        container.process_report_use_case.execute(
            input_path=args.input,
            output_path=args.output,
        )
        return 0

    except PDFProcessingError as exc:
        logger.error(f"Processing error: {exc}", exc_info=False)
        return 1

    except Exception as exc:  # noqa: BLE001 — last-resort catch for unexpected errors
        logger.error(f"Unexpected error: {exc}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
