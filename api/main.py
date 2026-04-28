"""FastAPI REST interface for the PDF data-processor pipeline.

Endpoints
---------
GET  /health          — liveness probe.
POST /process         — upload a PDF, receive the generated Excel file.

Run with::

    uvicorn api.main:app --reload

Or from the project root::

    python -m uvicorn api.main:app --reload
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from container import Container
from core.exceptions import (
    ExtractionError,
    ParseError,
    PDFFileNotFoundError,
    StrategyNotFoundError,
    TransformError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Application & DI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PDF Data Processor API",
    description="Upload an attendance PDF and receive a downloadable Excel file.",
    version="1.0.0",
)

_container = Container()

# ---------------------------------------------------------------------------
# Exception → HTTP status mapping
# ---------------------------------------------------------------------------

_EXCEPTION_STATUS: dict[type[Exception], int] = {
    PDFFileNotFoundError: 404,
    StrategyNotFoundError: 422,
    ValidationError: 422,
    ParseError: 422,
    ExtractionError: 400,
    TransformError: 500,
}


def _http_exception(exc: Exception) -> HTTPException:
    status = _EXCEPTION_STATUS.get(type(exc), 500)
    return HTTPException(status_code=status, detail=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", summary="Liveness probe")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/process", summary="Process an attendance PDF and download the Excel output")
async def process_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> FileResponse:
    """Upload a PDF file and receive the generated Excel report as a download.

    **Request**: ``multipart/form-data`` with a ``file`` field containing the PDF.

    **Response**: An ``application/vnd.openxmlformats-officedocument.spreadsheetml.sheet``
    file attachment ready to save.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")

    # Temp input PDF
    tmp_fd, tmp_input = tempfile.mkstemp(suffix=".pdf")
    # Temp output Excel — written by the generator
    _, tmp_output = tempfile.mkstemp(suffix=".xlsx")

    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)

        _container.process_report_use_case.execute(tmp_input, tmp_output)
    except (PDFFileNotFoundError, StrategyNotFoundError, ValidationError,
            ParseError, ExtractionError, TransformError) as exc:
        # Clean up before raising
        for p in (tmp_input, tmp_output):
            if os.path.exists(p):
                os.unlink(p)
        raise _http_exception(exc) from exc
    finally:
        # Input temp file is no longer needed
        if os.path.exists(tmp_input):
            os.unlink(tmp_input)

    # Schedule output file deletion after the response is sent
    background_tasks.add_task(os.unlink, tmp_output)

    stem = Path(file.filename).stem
    return FileResponse(
        path=tmp_output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{stem}.xlsx",
    )
