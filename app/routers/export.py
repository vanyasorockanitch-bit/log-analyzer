import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import matplotlib
from fpdf import FPDF
import matplotlib.pyplot as plt
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import ParsedEvent, RawLog
from app.services.analysis_storage import save_analysis_result
from app.services.log_files import resolve_log_file
from app.services.workflow import ensure_log_file_is_parsed

matplotlib.use("Agg")

router = APIRouter(prefix="/export", tags=["export"])


def _is_sqlite() -> bool:
    return "sqlite" in str(engine.url)


def _time_bucket_expression(column, group_by: str):
    if _is_sqlite():
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


@router.get("/pdf/{file_ref}")
def export_pdf(
    file_ref: str,
    level: Optional[str] = Query(None),
    group_by: Optional[str] = Query("hour"),
    top_limit: int = Query(50),
    db: Session = Depends(get_db),
):
    log_file = resolve_log_file(db, file_ref)
    if log_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    ensure_log_file_is_parsed(db, log_file)

    base_query = (
        db.query(ParsedEvent)
        .join(RawLog, ParsedEvent.raw_log_id == RawLog.id)
        .filter(RawLog.log_file_id == log_file.id)
    )
    if level:
        base_query = base_query.filter(ParsedEvent.level == level)

    total_events = base_query.count()

    level_counts = (
        base_query.with_entities(ParsedEvent.level, func.count(ParsedEvent.id))
        .group_by(ParsedEvent.level)
        .all()
    )
    by_level = {lvl: cnt for lvl, cnt in level_counts}

    top_messages = (
        base_query.with_entities(ParsedEvent.message, func.count(ParsedEvent.id))
        .group_by(ParsedEvent.message)
        .order_by(desc(func.count(ParsedEvent.id)))
        .limit(top_limit)
        .all()
    )
    top_messages_list = [{"message": msg, "count": cnt} for msg, cnt in top_messages]

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

    time_bucket = _time_bucket_expression(ParsedEvent.timestamp, group_by)
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

    save_analysis_result(
        db,
        log_file_id=log_file.id,
        calculation_type="pdf_export",
        level_filter=level,
        group_by=group_by,
        result_data={
            "total_events": total_events,
            "by_level": by_level,
            "top_messages": top_messages_list,
            "time_range": {"start": start_ts, "end": end_ts},
            "time_series": time_series_list,
        },
    )
    db.commit()

    plt.figure(figsize=(8, 4))
    buckets = [item["bucket"] for item in time_series_list]
    counts = [item["count"] for item in time_series_list]
    plt.plot(buckets, counts, marker="o", linestyle="-", color="teal")
    plt.title(f"Temporal series ({group_by})")
    plt.xlabel("Time bucket")
    plt.ylabel("Events")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    chart_buffer = io.BytesIO()
    plt.savefig(chart_buffer, format="png", dpi=100)
    plt.close()
    chart_buffer.seek(0)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Log Analysis Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 8, f"Upload ID: {log_file.id}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"File: {log_file.original_filename}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Format: {log_file.detected_format}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Total events: {total_events}", new_x="LMARGIN", new_y="NEXT")
    levels_str = ", ".join(f"{lvl}: {cnt}" for lvl, cnt in by_level.items())
    pdf.cell(0, 8, f"Levels: {levels_str}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Period: {start_ts} - {end_ts}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    pdf.image(chart_buffer, w=pdf.w - 20, x=10)
    chart_buffer.close()

    pdf.ln(5)
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.cell(0, 8, "Top Messages", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", size=9)
    col_widths = [pdf.w - 50, 30]
    pdf.cell(col_widths[0], 7, "Message", border=1)
    pdf.cell(col_widths[1], 7, "Count", border=1, new_x="LMARGIN", new_y="NEXT")
    for msg in top_messages_list:
        pdf.cell(col_widths[0], 7, msg["message"][:100], border=1)
        pdf.cell(col_widths[1], 7, str(msg["count"]), border=1, new_x="LMARGIN", new_y="NEXT")

    pdf_bytes = bytes(pdf.output())
    pdf_buffer = io.BytesIO(pdf_bytes)

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=report_{log_file.id}_{log_file.original_filename}.pdf"
            )
        },
    )
