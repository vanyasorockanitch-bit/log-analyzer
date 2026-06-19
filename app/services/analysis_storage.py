from sqlalchemy.orm import Session

from app.models import AnalysisResult


def save_analysis_result(
    db: Session,
    *,
    log_file_id: int,
    calculation_type: str,
    result_data: dict | list,
    level_filter: str | None = None,
    group_by: str | None = None,
    message_sort: str | None = None,
) -> AnalysisResult:
    """
    Persist an analytical calculation in the database.

    Statistics and anomalies are still recomputed when requested so the UI
    always sees current data, but every produced result is stored for audit,
    report history and diploma demonstration.
    """

    record = AnalysisResult(
        log_file_id=log_file_id,
        calculation_type=calculation_type,
        level_filter=level_filter,
        group_by=group_by,
        message_sort=message_sort,
        result_data=result_data,
    )
    db.add(record)
    db.flush()
    return record
