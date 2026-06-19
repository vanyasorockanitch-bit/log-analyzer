from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import export, nlp, parse, reports, stats, upload
from app.services.schema import initialize_database

# Creates tables and softly upgrades the demo SQLite schema when new columns
# are added during diploma development.
initialize_database()

app = FastAPI(title="Log Analyzer API", version="0.1.0")

app.include_router(upload.router)
app.include_router(parse.router)
app.include_router(stats.router)
app.include_router(nlp.router)
app.include_router(reports.router)
app.include_router(export.router)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/api/health")
def healthcheck():
    return {"message": "Log Analyzer API is running"}
