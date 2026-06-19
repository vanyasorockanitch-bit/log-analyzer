from sqlalchemy.orm import Session

from app.models import AnalysisResult, LogFile, MessageSummary, ParsedEvent, RawLog, Report


def clear_all_reports(db: Session) -> dict:
    """Delete saved reports while keeping uploaded logs and parsed events."""

    deleted_reports = db.query(Report).delete(synchronize_session=False)
    db.commit()
    return {"deleted_reports": deleted_reports}


def clear_all_uploaded_logs(db: Session) -> dict:
    """
    Delete uploaded logs and calculated data tied directly to them.

    Saved reports are intentionally preserved: a report is a historical
    document, while uploads/events/summaries are working data that can be
    cleared before a new demonstration or test run.
    """

    raw_log_ids = db.query(RawLog.id)
    counts = {
        "preserved_reports": db.query(Report).count(),
        "deleted_message_summaries": db.query(MessageSummary).count(),
        "deleted_analysis_results": db.query(AnalysisResult).count(),
        "deleted_parsed_events": db.query(ParsedEvent).filter(
            ParsedEvent.raw_log_id.in_(raw_log_ids)
        ).count(),
        "deleted_raw_logs": db.query(RawLog).count(),
        "deleted_log_files": db.query(LogFile).count(),
    }

    db.query(MessageSummary).delete(synchronize_session=False)
    db.query(AnalysisResult).delete(synchronize_session=False)
    db.query(ParsedEvent).filter(
        ParsedEvent.raw_log_id.in_(raw_log_ids)
    ).delete(synchronize_session=False)
    db.query(RawLog).delete(synchronize_session=False)
    db.query(LogFile).delete(synchronize_session=False)
    db.commit()

    return counts
