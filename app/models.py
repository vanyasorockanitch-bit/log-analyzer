from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base


class LogFile(Base):
    """
    One uploaded log file.

    This is the navigation anchor for the whole system: raw lines, parsed
    events, statistics, NLP summaries and reports are all tied back to this id.
    """

    __tablename__ = "log_files"

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String(255), nullable=False, index=True)
    detected_format = Column(String(50), nullable=False, default="unknown")
    line_count = Column(Integer, nullable=False, default=0)
    parse_status = Column(String(20), nullable=False, default="uploaded")
    uploaded_at = Column(TIMESTAMP, server_default=func.now())
    last_parsed_at = Column(TIMESTAMP)


class RawLog(Base):
    """
    One original line from an uploaded file.

    Raw lines are kept so the same upload can be parsed again after parser
    improvements without asking the user to upload the file twice.
    """

    __tablename__ = "raw_logs"

    id = Column(Integer, primary_key=True, index=True)
    log_file_id = Column(Integer, ForeignKey("log_files.id", ondelete="CASCADE"))
    filename = Column(String(255), nullable=False)
    line_number = Column(Integer, nullable=False)
    raw_text = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())


class ParsedEvent(Base):
    """
    Normalized event produced by a parser from one raw log line.

    Common fields make Apache/Nginx and future formats comparable. Format-
    specific details stay in parsed_data so new parsers do not require schema
    changes for every extra attribute.
    """

    __tablename__ = "parsed_events"

    id = Column(Integer, primary_key=True, index=True)
    raw_log_id = Column(Integer, ForeignKey("raw_logs.id", ondelete="CASCADE"))
    timestamp = Column(TIMESTAMP)
    level = Column(String(20))
    source = Column(String(100))
    message = Column(Text)
    ip_address = Column(String(45))
    status_code = Column(Integer)
    http_method = Column(String(16))
    request_path = Column(String(1024))
    parsed_data = Column(JSON)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Report(Base):
    """
    Saved analytical report.

    The report stores both human-readable text and machine-readable statistics
    so history/PDF views can open an existing result instead of regenerating it.
    """

    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    log_file_id = Column(Integer, ForeignKey("log_files.id", ondelete="SET NULL"))
    name = Column(String(255))
    description = Column(Text)
    source_type = Column(String(50))
    language = Column(String(10), nullable=False, default="ru")
    log_ids = Column(JSON)
    summary_text = Column(Text)
    report_text = Column(Text)
    statistics = Column(JSON)
    anomalies = Column(JSON)
    recommendations = Column(JSON)
    created_at = Column(TIMESTAMP, server_default=func.now())


class MessageSummary(Base):
    """
    Saved NLP/rule-based explanation for one unique message in one upload.

    The hash includes log_file_id and language, so identical text from different
    files still remains traceable to the exact upload shown in a report.
    """

    __tablename__ = "message_summaries"

    id = Column(Integer, primary_key=True, index=True)
    log_file_id = Column(Integer, ForeignKey("log_files.id", ondelete="CASCADE"))
    message_hash = Column(String(32), unique=True, index=True)
    message_text = Column(Text)
    summary = Column(Text)
    event_type = Column(String(80))
    severity = Column(String(20))
    recommendation = Column(Text)
    language = Column(String(10), nullable=False, default="ru")


class AnalysisResult(Base):
    """
    Audit/cache table for calculated statistics, anomalies and exports.

    It records what was calculated, for which file, with which filters. This is
    useful for report traceability and for explaining the data flow on defense.
    """

    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    log_file_id = Column(Integer, ForeignKey("log_files.id", ondelete="CASCADE"), index=True)
    calculation_type = Column(String(40), nullable=False, index=True)
    level_filter = Column(String(20))
    group_by = Column(String(20))
    message_sort = Column(String(40))
    result_data = Column(JSON)
    created_at = Column(TIMESTAMP, server_default=func.now())
