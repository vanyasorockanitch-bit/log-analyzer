import math

from fastapi import HTTPException
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.database import engine
from app.models import ParsedEvent, RawLog
from app.services.log_files import resolve_log_file


def is_sqlite() -> bool:
    return "sqlite" in str(engine.url)


def time_bucket_expression(column, group_by: str):
    """Build a DB-specific expression for time aggregation."""

    if is_sqlite():
        if group_by == "day":
            return func.strftime("%Y-%m-%d", column).label("bucket")
        if group_by == "hour":
            return func.strftime("%Y-%m-%d %H:00", column).label("bucket")
        if group_by == "minute":
            return func.strftime("%Y-%m-%d %H:%M", column).label("bucket")
    else:
        if group_by == "day":
            return func.date(column).label("bucket")
        if group_by == "hour":
            return func.date_trunc("hour", column).label("bucket")
        if group_by == "minute":
            return func.date_trunc("minute", column).label("bucket")
    raise HTTPException(400, "Invalid group_by")


def build_base_query(db: Session, file_ref: str):
    """Resolve a log file and return the shared query for its parsed events."""

    log_file = resolve_log_file(db, file_ref)
    if log_file is None:
        raise HTTPException(status_code=404, detail="File not found")

    base_query = (
        db.query(ParsedEvent)
        .join(RawLog, ParsedEvent.raw_log_id == RawLog.id)
        .filter(RawLog.log_file_id == log_file.id)
    )
    return log_file, base_query


MESSAGE_SORT_LABELS = {
    "count_desc": "по количеству, сначала самые частые",
    "count_asc": "по количеству, сначала редкие",
    "first_seen_asc": "по времени первого появления, сначала ранние",
    "first_seen_desc": "по времени первого появления, сначала поздние",
    "last_seen_desc": "по времени последнего появления, сначала свежие",
    "level_asc": "по уровню события",
    "message_asc": "по тексту сообщения",
}


def collect_statistics(
    base_query,
    group_by: str,
    page: int,
    limit: int,
    message_sort: str = "count_desc",
) -> dict:
    """Collect shared statistics used by API routes, reports and anomalies."""

    total_events = base_query.count()

    level_counts = (
        base_query.with_entities(ParsedEvent.level, func.count(ParsedEvent.id))
        .group_by(ParsedEvent.level)
        .all()
    )
    by_level = {lvl or "unknown": cnt for lvl, cnt in level_counts}

    status_counts = (
        base_query.with_entities(ParsedEvent.status_code, func.count(ParsedEvent.id))
        .filter(ParsedEvent.status_code.isnot(None))
        .group_by(ParsedEvent.status_code)
        .order_by(ParsedEvent.status_code)
        .all()
    )
    by_status = {str(code): cnt for code, cnt in status_counts}

    top_ips = (
        base_query.with_entities(ParsedEvent.ip_address, func.count(ParsedEvent.id))
        .filter(ParsedEvent.ip_address.isnot(None))
        .group_by(ParsedEvent.ip_address)
        .order_by(desc(func.count(ParsedEvent.id)))
        .limit(10)
        .all()
    )

    top_paths = (
        base_query.with_entities(ParsedEvent.request_path, func.count(ParsedEvent.id))
        .filter(ParsedEvent.request_path.isnot(None))
        .group_by(ParsedEvent.request_path)
        .order_by(desc(func.count(ParsedEvent.id)))
        .limit(10)
        .all()
    )

    total_unique_messages = base_query.with_entities(ParsedEvent.message).distinct().count()
    pages = math.ceil(total_unique_messages / limit) if total_unique_messages > 0 else 1
    offset = (page - 1) * limit

    top_messages = message_groups(base_query, message_sort).offset(offset).limit(limit).all()
    top_messages_list = [
        {
            "message": row.message,
            "count": row.count,
            "level": row.level or "unknown",
            "first_seen": _format_dt(row.first_seen),
            "last_seen": _format_dt(row.last_seen),
        }
        for row in top_messages
    ]

    time_range = base_query.with_entities(
        func.min(ParsedEvent.timestamp).label("min_ts"),
        func.max(ParsedEvent.timestamp).label("max_ts"),
    ).first()
    start_ts = (
        time_range.min_ts.isoformat()
        if hasattr(time_range.min_ts, "isoformat")
        else str(time_range.min_ts)
        if time_range.min_ts
        else None
    )
    end_ts = (
        time_range.max_ts.isoformat()
        if hasattr(time_range.max_ts, "isoformat")
        else str(time_range.max_ts)
        if time_range.max_ts
        else None
    )

    time_bucket = time_bucket_expression(ParsedEvent.timestamp, group_by)
    time_series = (
        base_query.with_entities(time_bucket, func.count(ParsedEvent.id))
        .group_by(time_bucket)
        .order_by(time_bucket)
        .all()
    )

    time_series_list = []
    for bucket, count in time_series:
        if bucket is None:
            bucket_str = ""
        elif hasattr(bucket, "isoformat"):
            bucket_str = bucket.isoformat()
        else:
            bucket_str = str(bucket)
        time_series_list.append({"bucket": bucket_str, "count": count})

    error_events = by_level.get("error", 0)
    warning_events = by_level.get("warning", 0)
    error_ratio = round(error_events / total_events, 4) if total_events else 0.0
    warning_ratio = round(warning_events / total_events, 4) if total_events else 0.0

    status_4xx = sum(count for code, count in by_status.items() if code.startswith("4"))
    status_5xx = sum(count for code, count in by_status.items() if code.startswith("5"))
    status_4xx_ratio = round(status_4xx / total_events, 4) if total_events else 0.0
    status_5xx_ratio = round(status_5xx / total_events, 4) if total_events else 0.0

    return {
        "total_events": total_events,
        "by_level": by_level,
        "by_status": by_status,
        "top_ips": [{"ip_address": ip, "count": cnt} for ip, cnt in top_ips],
        "top_paths": [{"request_path": path, "count": cnt} for path, cnt in top_paths],
        "top_messages": top_messages_list,
        "top_messages_meta": {
            "total": total_unique_messages,
            "page": page,
            "limit": limit,
            "pages": pages,
            "sort": message_sort,
            "sort_label": MESSAGE_SORT_LABELS.get(message_sort, MESSAGE_SORT_LABELS["count_desc"]),
        },
        "time_series": time_series_list,
        "time_range": {
            "start": start_ts,
            "end": end_ts,
        },
        "error_events": error_events,
        "warning_events": warning_events,
        "error_ratio": error_ratio,
        "warning_ratio": warning_ratio,
        "status_4xx": status_4xx,
        "status_5xx": status_5xx,
        "status_4xx_ratio": status_4xx_ratio,
        "status_5xx_ratio": status_5xx_ratio,
    }


def message_groups(base_query, message_sort: str):
    count_expr = func.count(ParsedEvent.id).label("count")
    first_seen_expr = func.min(ParsedEvent.timestamp).label("first_seen")
    last_seen_expr = func.max(ParsedEvent.timestamp).label("last_seen")
    level_expr = func.min(ParsedEvent.level).label("level")

    query = (
        base_query.with_entities(
            ParsedEvent.message.label("message"),
            count_expr,
            first_seen_expr,
            last_seen_expr,
            level_expr,
        )
        .group_by(ParsedEvent.message)
    )

    sort_map = {
        "count_desc": [desc(count_expr), ParsedEvent.message],
        "count_asc": [asc(count_expr), ParsedEvent.message],
        "first_seen_asc": [asc(first_seen_expr), ParsedEvent.message],
        "first_seen_desc": [desc(first_seen_expr), ParsedEvent.message],
        "last_seen_desc": [desc(last_seen_expr), ParsedEvent.message],
        "level_asc": [asc(level_expr), desc(count_expr), ParsedEvent.message],
        "message_asc": [asc(ParsedEvent.message)],
    }
    return query.order_by(*sort_map.get(message_sort, sort_map["count_desc"]))


def _format_dt(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def detect_anomalies(stats: dict) -> list[dict]:
    """Apply simple, explainable anomaly rules over aggregated statistics."""

    anomalies = []
    total_events = stats["total_events"]
    time_series = stats["time_series"]
    top_messages = stats["top_messages"]
    top_ips = stats["top_ips"]

    if total_events == 0:
        return anomalies

    if stats["error_ratio"] >= 0.30 and stats["error_events"] >= 5:
        anomalies.append(
            {
                "type": "high_error_ratio",
                "severity": "high",
                "title": "Высокая доля ошибок",
                "description": (
                    f"Ошибки составляют {round(stats['error_ratio'] * 100, 1)}% всех событий "
                    f"({stats['error_events']} из {total_events})."
                ),
            }
        )

    if stats["status_5xx_ratio"] >= 0.10 and stats["status_5xx"] >= 3:
        anomalies.append(
            {
                "type": "many_http_5xx",
                "severity": "high",
                "title": "Много HTTP 5xx",
                "description": (
                    f"Серверные ошибки 5xx встречаются {stats['status_5xx']} раз "
                    f"({round(stats['status_5xx_ratio'] * 100, 1)}% событий)."
                ),
            }
        )

    if stats["status_4xx_ratio"] >= 0.15 and stats["status_4xx"] >= 5:
        anomalies.append(
            {
                "type": "many_http_4xx",
                "severity": "medium",
                "title": "Высокая доля HTTP 4xx",
                "description": (
                    f"Клиентские ошибки 4xx встречаются {stats['status_4xx']} раз "
                    f"({round(stats['status_4xx_ratio'] * 100, 1)}% событий)."
                ),
            }
        )

    if time_series:
        average_bucket = sum(item["count"] for item in time_series) / len(time_series)
        spike = max(time_series, key=lambda item: item["count"])
        if spike["count"] >= max(average_bucket * 2, average_bucket + 5):
            anomalies.append(
                {
                    "type": "activity_spike",
                    "severity": "medium",
                    "title": "Всплеск активности",
                    "description": (
                        f"В интервале {spike['bucket']} зарегистрирован всплеск: "
                        f"{spike['count']} событий при среднем значении {round(average_bucket, 1)}."
                    ),
                }
            )

    repeated_critical = next(
        (
            item
            for item in top_messages
            if item["count"] >= 10
            and any(word in item["message"].lower() for word in ["error", "fail", "denied", "500"])
        ),
        None,
    )
    if repeated_critical:
        anomalies.append(
            {
                "type": "repeated_critical_message",
                "severity": "high",
                "title": "Повторяющееся критическое сообщение",
                "description": (
                    f"Сообщение '{repeated_critical['message'][:90]}' повторилось "
                    f"{repeated_critical['count']} раз."
                ),
            }
        )

    if top_ips:
        top_ip = top_ips[0]
        ip_ratio = top_ip["count"] / total_events
        if top_ip["count"] >= 10 and ip_ratio >= 0.40:
            anomalies.append(
                {
                    "type": "dominant_ip",
                    "severity": "medium",
                    "title": "Подозрительно активный IP",
                    "description": (
                        f"IP {top_ip['ip_address']} сгенерировал {top_ip['count']} событий "
                        f"({round(ip_ratio * 100, 1)}% от общего объёма)."
                    ),
                }
            )

    return anomalies
