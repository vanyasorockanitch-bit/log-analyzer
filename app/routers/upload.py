from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogFile, RawLog
from app.parsers import detect_log_format
from app.services.cleanup import clear_all_uploaded_logs
from app.services.log_files import resolve_log_file
from app.services.parsing import parse_log_file

router = APIRouter(prefix="/upload", tags=["upload"])


def _serialize_log_file(log_file: LogFile) -> dict:
    return {
        "log_file_id": log_file.id,
        "filename": log_file.original_filename,
        "detected_format": log_file.detected_format,
        "parse_status": log_file.parse_status,
        "line_count": log_file.line_count,
        "uploaded_at": (
            log_file.uploaded_at.isoformat()
            if getattr(log_file, "uploaded_at", None)
            else None
        ),
        "last_parsed_at": (
            log_file.last_parsed_at.isoformat()
            if getattr(log_file, "last_parsed_at", None)
            else None
        ),
    }


@router.get("/")
def list_uploaded_files(db: Session = Depends(get_db)):
    """Return uploaded log files for future UI navigation and report linking."""

    log_files = db.query(LogFile).order_by(LogFile.id.desc()).all()
    return {"items": [_serialize_log_file(log_file) for log_file in log_files]}


@router.delete("/clear")
def clear_uploaded_files(
    confirm: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Clear uploaded logs and temporary analysis data, keeping saved reports."""

    if not confirm:
        raise HTTPException(status_code=400, detail="Confirmation is required")

    result = clear_all_uploaded_logs(db)
    result["status"] = "cleared"
    return result


@router.get("/{file_ref}")
def get_uploaded_file(file_ref: str, db: Session = Depends(get_db)):
    log_file = resolve_log_file(db, file_ref)
    if log_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return _serialize_log_file(log_file)


@router.post("/")
async def upload_log_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a log file, detect its format and store raw lines in the database."""

    if not file.filename.endswith((".log", ".txt")):
        raise HTTPException(status_code=400, detail="Only .log or .txt files are allowed")

    try:
        contents = await file.read()
        text = contents.decode("utf-8", errors="ignore")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read file: {exc}")

    lines = text.splitlines()
    non_empty_lines = [line.strip() for line in lines if line.strip()]
    sample_lines = non_empty_lines[:50]
    detected_format = detect_log_format(sample_lines)

    log_file = LogFile(
        original_filename=file.filename,
        detected_format=detected_format,
        line_count=len(non_empty_lines),
        parse_status="uploaded",
    )
    db.add(log_file)
    db.flush()

    raw_logs = []
    for line_num, line in enumerate(lines, start=1):
        cleaned_line = line.strip()
        if cleaned_line:
            raw_logs.append(
                {
                    "log_file_id": log_file.id,
                    "filename": file.filename,
                    "line_number": line_num,
                    "raw_text": cleaned_line,
                }
            )

    db.bulk_insert_mappings(RawLog, raw_logs)
    db.commit()
    db.refresh(log_file)

    auto_parse_result = None
    auto_parse_error = None
    try:
        # The main UI scenario should be ready for statistics immediately after
        # upload. Manual parsing still stays available for re-processing.
        auto_parse_result = parse_log_file(db, log_file)
        db.refresh(log_file)
    except HTTPException as exc:
        auto_parse_error = exc.detail

    response = _serialize_log_file(log_file)
    response.update(
        {
            "lines_received": len(raw_logs),
            "auto_parse": auto_parse_result,
            "auto_parse_error": auto_parse_error,
            "message": "File uploaded, saved to database and parsed when possible",
        }
    )
    return response
