from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import LogFile, ParsedEvent, RawLog


def ensure_log_file_is_parsed(db: Session, log_file: LogFile) -> None:
    """
    Guard endpoints that depend on parsed events.

    The UI also disables unavailable actions, but this backend check is the
    real safety rule: NLP, statistics, reports and export cannot run until the
    selected upload has successfully passed parsing and has events in the DB.
    """

    if log_file.parse_status != "parsed":
        raise HTTPException(
            status_code=409,
            detail=(
                "Log file must be parsed before analysis. "
                "Run parsing first or upload a file that can be parsed automatically."
            ),
        )

    event_count = (
        db.query(ParsedEvent)
        .join(RawLog, ParsedEvent.raw_log_id == RawLog.id)
        .filter(RawLog.log_file_id == log_file.id)
        .count()
    )
    if event_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Log file is marked as parsed, but parsed events were not found.",
        )
