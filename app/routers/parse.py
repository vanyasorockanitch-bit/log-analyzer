from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogFile
from app.services.log_files import resolve_log_file
from app.services.parsing import parse_log_file

router = APIRouter(prefix="/parse", tags=["parse"])


def _load_log_file_or_404(db: Session, file_ref: str) -> LogFile:
    log_file = resolve_log_file(db, file_ref)
    if log_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return log_file


@router.post("/file/{file_ref}")
def parse_file(file_ref: str, db: Session = Depends(get_db)):
    log_file = _load_log_file_or_404(db, file_ref)
    return parse_log_file(db, log_file)


@router.post("/all")
def parse_all_unprocessed(db: Session = Depends(get_db)):
    log_files = (
        db.query(LogFile)
        .filter(LogFile.parse_status.in_(["uploaded", "failed"]))
        .order_by(LogFile.id)
        .all()
    )

    results = []
    for log_file in log_files:
        results.append(parse_log_file(db, log_file))

    return {
        "processed_files": len(results),
        "results": results,
    }
