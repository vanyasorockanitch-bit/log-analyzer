from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import LogFile


def resolve_log_file(db: Session, file_ref: str) -> LogFile | None:
    """
    Resolve either a numeric upload id or a legacy filename.

    For duplicate filenames we pick the most recent upload. This keeps the old
    API shape working while the UI is being migrated to explicit ids.
    """

    if file_ref.isdigit():
        return db.query(LogFile).filter(LogFile.id == int(file_ref)).first()

    return (
        db.query(LogFile)
        .filter(LogFile.original_filename == file_ref)
        .order_by(desc(LogFile.id))
        .first()
    )
