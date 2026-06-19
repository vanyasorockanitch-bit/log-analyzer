from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import LogFile, ParsedEvent, RawLog
from app.parsers import get_parser


def parse_log_file(db: Session, log_file: LogFile) -> dict:
    """
    Parse every raw line that belongs to one uploaded log file.

    The parser result is stored in parsed_events. Re-running this function
    replaces older parsed events for the same upload, which makes manual
    re-parsing predictable after parser improvements.
    """

    parser = get_parser(log_file.detected_format)
    if parser is None:
        log_file.parse_status = "failed"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported or unknown format: {log_file.detected_format}",
        )

    raw_logs = (
        db.query(RawLog)
        .filter(RawLog.log_file_id == log_file.id)
        .order_by(RawLog.line_number)
        .all()
    )
    if not raw_logs:
        log_file.parse_status = "failed"
        db.commit()
        raise HTTPException(status_code=404, detail="Raw log lines not found")

    raw_log_ids = [raw.id for raw in raw_logs]
    db.query(ParsedEvent).filter(ParsedEvent.raw_log_id.in_(raw_log_ids)).delete(
        synchronize_session=False
    )

    parsed_count = 0
    errors = []

    for raw in raw_logs:
        parsed_line = parser.parse_line(raw.raw_text)
        if parsed_line is None:
            errors.append(f"Line {raw.line_number}: failed to parse")
            continue

        db.add(
            ParsedEvent(
                raw_log_id=raw.id,
                timestamp=parsed_line.timestamp,
                level=parsed_line.level,
                source=parsed_line.source,
                message=parsed_line.message,
                ip_address=parsed_line.ip_address,
                status_code=parsed_line.status_code,
                http_method=parsed_line.http_method,
                request_path=parsed_line.request_path,
                parsed_data=parsed_line.parsed_data or {},
            )
        )
        parsed_count += 1

    log_file.parse_status = "parsed" if parsed_count else "failed"
    log_file.last_parsed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return {
        "log_file_id": log_file.id,
        "filename": log_file.original_filename,
        "detected_format": log_file.detected_format,
        "total_lines": len(raw_logs),
        "parsed": parsed_count,
        "errors": errors,
    }
