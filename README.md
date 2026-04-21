# PDF Attendance Report Engine

> Extract Hebrew employee-attendance tables from PDF files and export them as
> formatted Excel workbooks — automatically, from the command line.

---

## What it does

| Step | Action |
|------|--------|
| 1 | Opens the source PDF with **pdfplumber** |
| 2 | Detects the report format automatically (3 formats supported) |
| 3 | Validates the required column schema |
| 4 | Parses every attendance row into typed data objects |
| 5 | Aggregates totals (worked hours, working days, overtime buckets) |
| 6 | Writes a styled **Excel (.xlsx)** file with RTL layout for Hebrew |

---

## Supported PDF formats

| Format | Strategy | Unique columns |
|--------|----------|----------------|
| **Generic Hebrew** | `HebrewAttendanceStrategy` | `שעות כניסה`, `שעת יציאה`, `יום בשבוע` |
| **Simple** | `SimpleAttendanceStrategy` | `כניסה`, `יציאה`, `יום` (short names) |
| **Overtime** | `OvertimeAttendanceStrategy` | `הפסקה`, `100%`, `125%`, `150%` |

The engine tries each strategy in that priority order; the first match wins.

---

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run

```bash
python main.py <INPUT_PDF> <OUTPUT_XLSX>
```

**Example:**

```bash
python main.py reports/april_2025.pdf output/april_2025.xlsx
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Handled processing error (details logged to stderr) |

---

## Project structure

```
├── main.py                          # CLI entry point
├── container.py                     # Dependency-injection root
├── config.py                        # All tuneable constants (log level, format)
│
├── core/
│   ├── interfaces.py                # Abstract interfaces (ILogger, IPDFReader, …)
│   ├── exceptions.py                # Exception hierarchy (all inherit PDFProcessingError)
│   └── logger.py                    # StandardLogger — wraps Python logging
│
├── application/
│   ├── registry.py                  # Chain-of-responsibility strategy resolver
│   └── use_cases/
│       └── process_report.py        # Orchestrates the 6-step pipeline
│
├── domain/
│   ├── dtos/
│   │   └── report_dtos.py           # Immutable data-transfer objects
│   └── strategies/
│       ├── hebrew_attendance_strategy.py
│       ├── simple_attendance_strategy.py
│       └── overtime_attendance_strategy.py
│
└── infrastructure/
    ├── pdf_reader.py                # PdfPlumberReader — concrete IPDFReader
    └── pdf_generator.py             # ExcelReportGenerator — concrete IPDFGenerator
```

---

## Architecture

The engine follows **Clean Architecture** with strict layer separation:

```
         ┌─────────────────────────────┐
         │         main.py  (CLI)      │
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │    container.py  (DI Root)  │  ◄──  only place that imports concrete classes
         └──────────────┬──────────────┘
                        │ injects interfaces
         ┌──────────────▼──────────────┐
         │  application/  (Use Cases)  │  depends only on core interfaces
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │   domain/  (Strategies)     │  pure business logic, no I/O
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │  infrastructure/  (I/O)     │  pdfplumber + openpyxl
         └─────────────────────────────┘
         ┌─────────────────────────────┐
         │  core/  (Cross-cutting)     │  interfaces · exceptions · logger
         └─────────────────────────────┘
```

Every layer depends **inward only**. The `container.py` is the single place
allowed to import concrete classes and wire them together.

---

## Exception hierarchy

All exceptions share a common base, so callers can catch broadly or narrowly:

```
PDFProcessingError
├── PDFFileNotFoundError   — input PDF does not exist
├── ExtractionError        — pdfplumber failed to parse
├── StrategyNotFoundError  — no registered strategy matches the schema
├── ValidationError        — required columns missing
├── ParseError             — cannot map rows to typed DTOs
├── TransformError         — aggregation / business-logic failure
└── GenerationError        — cannot create or write the output file
```

Every raise is **preceded by a `logger.error` call**, so failures always appear
in the log before the exception propagates.

---

## Logging

Logging is controlled entirely from [`config.py`](config.py):

```python
LOG_LEVEL = logging.WARNING   # change to logging.INFO or logging.DEBUG locally
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
```

| Level | When it fires |
|-------|--------------|
| `ERROR` | Every `raise` — always logged before the exception propagates |
| `WARNING` | Unexpected but recoverable conditions |
| `INFO` | Pipeline milestones (extraction complete, parse record counts) |
| `DEBUG` | Fine-grained tracing — disabled in production (`LOG_LEVEL = WARNING`) |

---

## Adding a new PDF format

1. Create `domain/strategies/my_strategy.py` implementing `IReportStrategy`
   (`can_handle`, `validate`, `parse`, `transform`).
2. Register it in `container.py` — add it to the `strategies=[...]` list
   **before** more generic strategies:

```python
self._my_strategy = MyStrategy(logger=self._logger)

self._registry = ReportRegistry(
    strategies=[
        self._my_strategy,          # most specific — checked first
        self._overtime_strategy,
        self._simple_strategy,
        self._hebrew_attendance_strategy,
    ],
    logger=self._logger,
)
```

No other files need to change.

---

## Requirements

| Package | Purpose |
|---------|---------|
| `pdfplumber >= 0.10.0` | PDF table extraction |
| `openpyxl >= 3.1.0` | Excel report generation |

Python **3.9+** required.

---

## License

MIT
