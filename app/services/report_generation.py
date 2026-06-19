from typing import Optional

from sqlalchemy.orm import Session

from app.models import ParsedEvent, Report
from app.services.analysis_storage import save_analysis_result
from app.services.analytics import build_base_query, collect_statistics, detect_anomalies
from app.services.message_summaries import summarize_messages_in_session
from app.services.report_builder import build_human_report, explain_unique_messages
from app.services.workflow import ensure_log_file_is_parsed


def generate_and_save_report(
    db: Session,
    *,
    file_ref: str,
    level: Optional[str] = None,
    language: str = "ru",
    message_sort: str = "count_desc",
) -> dict:
    """
    Generate, persist and return one analytical report.

    The function is shared by both `/nlp/report` and `/reports/generate` so the
    project has a single source of truth for report creation.
    """

    log_file, base_query = build_base_query(db, file_ref)
    ensure_log_file_is_parsed(db, log_file)
    if level:
        base_query = base_query.filter(ParsedEvent.level == level)

    stats = collect_statistics(
        base_query,
        group_by="hour",
        page=1,
        limit=10,
        message_sort=message_sort,
    )
    anomalies = detect_anomalies(stats)
    saved_summaries = summarize_messages_in_session(
        db,
        log_file_id=log_file.id,
        language=language,
    )
    explanations = explain_unique_messages(
        db,
        log_file.id,
        language=language,
        message_sort=message_sort,
    )
    report_payload = build_human_report(
        log_file=log_file,
        stats=stats,
        anomalies=anomalies,
        explanations=explanations,
        language=language,
        message_sort=message_sort,
    )

    report = Report(
        log_file_id=log_file.id,
        name=f"Отчёт по {log_file.original_filename}",
        description="Автоматически сформированный аналитический отчёт.",
        source_type=log_file.detected_format,
        language=language,
        log_ids=[log_file.id],
        summary_text=report_payload["summary_text"],
        report_text=report_payload["report_text"],
        statistics=stats,
        anomalies=anomalies,
        recommendations=report_payload["recommendations"],
    )
    db.add(report)
    save_analysis_result(
        db,
        log_file_id=log_file.id,
        calculation_type="statistics",
        level_filter=level,
        group_by="hour",
        message_sort=message_sort,
        result_data=stats,
    )
    save_analysis_result(
        db,
        log_file_id=log_file.id,
        calculation_type="anomalies",
        level_filter=level,
        group_by="hour",
        message_sort=message_sort,
        result_data=anomalies,
    )
    db.commit()
    db.refresh(report)

    return {
        "report_id": report.id,
        "log_file_id": log_file.id,
        "filename": log_file.original_filename,
        "detected_format": log_file.detected_format,
        "language": language,
        "summary": report.summary_text,
        "report": report.report_text,
        "statistics": stats,
        "anomalies": anomalies,
        "recommendations": report.recommendations,
        "explained_messages_total": len(explanations),
        "saved_summaries_total": saved_summaries,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
