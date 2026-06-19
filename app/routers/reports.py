from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogFile, Report
from app.services.cleanup import clear_all_reports
from app.services.report_generation import generate_and_save_report
from app.services.report_records import (
    build_saved_report_pdf,
    ensure_saved_report_exists,
    serialize_report,
    serialize_report_list_item,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _load_report_or_404(db: Session, report_id: int) -> tuple[Report, Optional[LogFile]]:
    report = db.query(Report).filter(Report.id == report_id).first()
    ensure_saved_report_exists(report)
    log_file = None
    if report.log_file_id is not None:
        log_file = db.query(LogFile).filter(LogFile.id == report.log_file_id).first()
    return report, log_file


@router.post("/generate")
def generate_report_via_reports_router(
    filename: str,
    level: Optional[str] = None,
    language: str = "ru",
    message_sort: str = "count_desc",
    db: Session = Depends(get_db),
):
    return generate_and_save_report(
        db,
        file_ref=filename,
        level=level,
        language=language,
        message_sort=message_sort,
    )


@router.get("/")
def list_reports(
    log_file_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Report).order_by(Report.id.desc())
    if log_file_id is not None:
        query = query.filter(Report.log_file_id == log_file_id)

    reports = query.limit(limit).all()
    items = []
    for report in reports:
        log_file = None
        if report.log_file_id is not None:
            log_file = db.query(LogFile).filter(LogFile.id == report.log_file_id).first()
        items.append(serialize_report_list_item(report, log_file=log_file))

    return {"items": items}


@router.delete("/clear")
def clear_reports(
    confirm: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Clear saved reports without deleting uploaded logs."""

    if not confirm:
        raise HTTPException(status_code=400, detail="Confirmation is required")

    result = clear_all_reports(db)
    result["status"] = "cleared"
    return result


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    report, log_file = _load_report_or_404(db, report_id)
    return serialize_report(report, log_file=log_file)


@router.get("/{report_id}/pdf")
def get_report_pdf(report_id: int, db: Session = Depends(get_db)):
    report, log_file = _load_report_or_404(db, report_id)
    payload = serialize_report(report, log_file=log_file)
    pdf_bytes = build_saved_report_pdf(payload)
    safe_name = f"report_{report_id}_{report.log_file_id or 'unknown'}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
