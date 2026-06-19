from sqlalchemy.orm import Session

from app.models import MessageSummary, ParsedEvent, RawLog
from app.services.event_explanations import explain_event
from app.services.nlp_storage import message_summary_hash


def summarize_messages_in_session(
    db: Session,
    *,
    log_file_id: int,
    language: str = "ru",
) -> int:
    """
    Persist explanations for every unique message in one parsed upload.

    The function works entirely inside the current DB session so callers can use
    it both in background tasks and inside larger transactions such as report
    generation.
    """

    events = (
        db.query(ParsedEvent)
        .join(RawLog, ParsedEvent.raw_log_id == RawLog.id)
        .filter(RawLog.log_file_id == log_file_id)
        .order_by(ParsedEvent.id)
        .all()
    )

    seen_messages = set()
    saved_count = 0
    for event in events:
        if event.message in seen_messages:
            continue
        seen_messages.add(event.message)

        msg_hash = message_summary_hash(log_file_id, language, event.message)
        explanation = explain_event(event, language=language)
        existing = db.query(MessageSummary).filter_by(message_hash=msg_hash).first()

        if existing is None:
            existing = MessageSummary(
                log_file_id=log_file_id,
                message_hash=msg_hash,
                message_text=event.message,
            )
            db.add(existing)

        existing.log_file_id = log_file_id
        existing.summary = explanation.summary
        existing.event_type = explanation.event_type
        existing.severity = explanation.severity
        existing.recommendation = explanation.recommendation
        existing.language = language
        saved_count += 1

    return saved_count
