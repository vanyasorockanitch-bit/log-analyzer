from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import MessageSummary
from app.services.log_files import resolve_log_file
from app.services.message_summaries import summarize_messages_in_session
from app.services.nlp_storage import message_summary_hash
from app.services.report_builder import explain_unique_messages
from app.services.report_generation import generate_and_save_report
from app.services.workflow import ensure_log_file_is_parsed

router = APIRouter(prefix="/nlp", tags=["nlp"])


def _load_log_file_or_404(db: Session, file_ref: str):
    log_file = resolve_log_file(db, file_ref)
    if log_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return log_file


def summarize_messages(file_ref: str, language: str = "ru") -> None:
    """
    Explain and persist all unique messages for one uploaded log file.

    This is intentionally not limited to top messages: every distinct message
    gets a saved explanation in `message_summaries`.
    """

    db = SessionLocal()
    try:
        log_file = _load_log_file_or_404(db, file_ref)
        ensure_log_file_is_parsed(db, log_file)
        summarize_messages_in_session(db, log_file_id=log_file.id, language=language)
        db.commit()
    finally:
        db.close()


@router.post("/summarize")
async def start_summarization(
    filename: str,
    background_tasks: BackgroundTasks,
    language: str = "ru",
    db: Session = Depends(get_db),
):
    log_file = _load_log_file_or_404(db, filename)
    ensure_log_file_is_parsed(db, log_file)
    background_tasks.add_task(summarize_messages, str(log_file.id), language)
    return {
        "status": "processing",
        "log_file_id": log_file.id,
        "filename": log_file.original_filename,
        "language": language,
    }


@router.get("/summaries")
async def get_summaries(
    file: str,
    language: str = "ru",
    message_sort: str = "count_desc",
    db: Session = Depends(get_db),
):
    log_file = _load_log_file_or_404(db, file)
    ensure_log_file_is_parsed(db, log_file)
    messages = explain_unique_messages(
        db,
        log_file.id,
        language=language,
        message_sort=message_sort,
    )

    summaries = []
    for item in messages:
        message_hash = message_summary_hash(log_file.id, language, item["message"])
        record = db.query(MessageSummary).filter_by(message_hash=message_hash).first()
        summaries.append(
            {
                "message": item["message"],
                "summary": record.summary if record else None,
                "event_type": record.event_type if record else item["event_type"],
                "severity": record.severity if record else item["severity"],
                "recommendation": record.recommendation if record else item["recommendation"],
            }
        )
    return summaries


@router.post("/report")
async def generate_report(
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
