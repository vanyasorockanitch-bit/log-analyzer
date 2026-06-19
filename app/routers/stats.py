from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MessageSummary, ParsedEvent
from app.services.analysis_storage import save_analysis_result
from app.services.analytics import build_base_query, collect_statistics, detect_anomalies
from app.services.nlp_storage import message_summary_hash
from app.services.workflow import ensure_log_file_is_parsed

router = APIRouter(tags=["statistics"])


@router.get("/stats/file/{file_ref}")
def get_file_statistics(
    file_ref: str,
    level: Optional[str] = Query(None),
    group_by: Optional[str] = Query("hour"),
    message_sort: str = Query("count_desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    log_file, base_query = build_base_query(db, file_ref)
    ensure_log_file_is_parsed(db, log_file)
    if level:
        base_query = base_query.filter(ParsedEvent.level == level)

    stats = collect_statistics(
        base_query,
        group_by=group_by,
        page=page,
        limit=limit,
        message_sort=message_sort,
    )
    anomalies = detect_anomalies(stats)
    response = {
        "log_file_id": log_file.id,
        "filename": log_file.original_filename,
        "detected_format": log_file.detected_format,
        "log_file": {
            "id": log_file.id,
            "filename": log_file.original_filename,
            "detected_format": log_file.detected_format,
            "parse_status": log_file.parse_status,
            "line_count": log_file.line_count,
            "uploaded_at": (
                log_file.uploaded_at.isoformat() if log_file.uploaded_at else None
            ),
            "last_parsed_at": (
                log_file.last_parsed_at.isoformat() if log_file.last_parsed_at else None
            ),
        },
        "level_filter": level,
        "group_by": group_by,
        **stats,
        "anomalies": anomalies,
    }

    save_analysis_result(
        db,
        log_file_id=log_file.id,
        calculation_type="statistics",
        level_filter=level,
        group_by=group_by,
        message_sort=message_sort,
        result_data=response,
    )
    save_analysis_result(
        db,
        log_file_id=log_file.id,
        calculation_type="anomalies",
        level_filter=level,
        group_by=group_by,
        message_sort=message_sort,
        result_data=anomalies,
    )
    db.commit()

    return response


@router.get("/stats/file/{file_ref}/messages")
def get_file_messages(
    file_ref: str,
    level: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    message_sort: str = Query("count_desc"),
    db: Session = Depends(get_db),
):
    log_file, base_query = build_base_query(db, file_ref)
    ensure_log_file_is_parsed(db, log_file)
    if level:
        base_query = base_query.filter(ParsedEvent.level == level)

    total_unique = base_query.with_entities(ParsedEvent.message).distinct().count()

    stats = collect_statistics(
        base_query,
        group_by="hour",
        page=page,
        limit=limit,
        message_sort=message_sort,
    )

    messages = []
    for item in stats["top_messages"]:
        msg_hash = message_summary_hash(log_file.id, "ru", item["message"])
        summary_record = db.query(MessageSummary).filter_by(message_hash=msg_hash).first()
        item["summary"] = summary_record.summary if summary_record else None
        messages.append(item)

    return {
        "page": page,
        "pages": stats["top_messages_meta"]["pages"],
        "total": total_unique,
        "sort": stats["top_messages_meta"]["sort"],
        "sort_label": stats["top_messages_meta"]["sort_label"],
        "messages": messages,
    }


@router.get("/anomalies/file/{file_ref}")
def get_file_anomalies(
    file_ref: str,
    level: Optional[str] = Query(None),
    group_by: Optional[str] = Query("hour"),
    db: Session = Depends(get_db),
):
    """Return explainable anomaly findings for the selected uploaded log."""

    log_file, base_query = build_base_query(db, file_ref)
    ensure_log_file_is_parsed(db, log_file)
    if level:
        base_query = base_query.filter(ParsedEvent.level == level)

    stats = collect_statistics(base_query, group_by=group_by, page=1, limit=10)
    anomalies = detect_anomalies(stats)
    response = {
        "log_file_id": log_file.id,
        "filename": log_file.original_filename,
        "detected_format": log_file.detected_format,
        "group_by": group_by,
        "total_events": stats["total_events"],
        "anomalies": anomalies,
    }

    save_analysis_result(
        db,
        log_file_id=log_file.id,
        calculation_type="anomalies",
        level_filter=level,
        group_by=group_by,
        result_data=response,
    )
    db.commit()

    return response
