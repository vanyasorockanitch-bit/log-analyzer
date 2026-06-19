from __future__ import annotations

from sqlalchemy import inspect

from app.database import Base, engine


SQLITE_COLUMN_PATCHES = {
    "raw_logs": [
        ("log_file_id", "INTEGER"),
    ],
    "parsed_events": [
        ("http_method", "VARCHAR(16)"),
        ("request_path", "VARCHAR(1024)"),
    ],
    "reports": [
        ("log_file_id", "INTEGER"),
        ("source_type", "VARCHAR(50)"),
        ("language", "VARCHAR(10) DEFAULT 'ru'"),
        ("report_text", "TEXT"),
        ("anomalies", "JSON"),
        ("recommendations", "JSON"),
    ],
    "message_summaries": [
        ("log_file_id", "INTEGER"),
        ("event_type", "VARCHAR(80)"),
        ("severity", "VARCHAR(20)"),
        ("recommendation", "TEXT"),
        ("language", "VARCHAR(10) DEFAULT 'ru'"),
    ],
}


def initialize_database() -> None:
    """
    Create missing tables and patch the demo SQLite schema in place.

    The project started without Alembic, so existing local SQLite databases may
    miss newer columns. The helper keeps the diploma demo database usable
    without asking the user to recreate it manually.
    """

    Base.metadata.create_all(bind=engine)

    if engine.dialect.name == "sqlite":
        _patch_sqlite_columns()
        _backfill_log_files_for_legacy_rows()


def _patch_sqlite_columns() -> None:
    inspector = inspect(engine)

    with engine.begin() as connection:
        for table_name, columns in SQLITE_COLUMN_PATCHES.items():
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, sql_type in columns:
                if column_name not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"
                    )


def _backfill_log_files_for_legacy_rows() -> None:
    """
    Link old raw log rows to synthetic uploads created from distinct filenames.

    This keeps pre-existing demo data visible after introducing the log_files
    table and allows the new file-centric APIs to work immediately.
    """

    with engine.begin() as connection:
        legacy_rows = connection.exec_driver_sql(
            """
            SELECT filename, COUNT(*) AS line_count
            FROM raw_logs
            GROUP BY filename
            """
        ).fetchall()

        for filename, line_count in legacy_rows:
            existing_log_file = connection.exec_driver_sql(
                """
                SELECT id
                FROM log_files
                WHERE original_filename = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (filename,),
            ).fetchone()

            if existing_log_file is None:
                detected_format = "apache_error"
                connection.exec_driver_sql(
                    """
                    INSERT INTO log_files (
                        original_filename,
                        detected_format,
                        line_count,
                        parse_status
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (filename, detected_format, line_count, "parsed"),
                )
                existing_log_file = connection.exec_driver_sql(
                    "SELECT last_insert_rowid()"
                ).fetchone()

            connection.exec_driver_sql(
                """
                UPDATE raw_logs
                SET log_file_id = ?
                WHERE filename = ?
                  AND log_file_id IS NULL
                """,
                (existing_log_file[0], filename),
            )
