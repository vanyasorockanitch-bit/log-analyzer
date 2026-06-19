import importlib
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


def load_isolated_app():
    """
    Load the application against a temporary SQLite database.

    The production app resolves the database engine at import time, so tests
    reload `app.*` modules after setting `DATABASE_URL`. This keeps the test
    suite isolated from the developer's real demo database.
    """

    temp_root = Path(tempfile.gettempdir()) / "log_analyzer_test_dbs"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_root / uuid.uuid4().hex
    temp_dir.mkdir(parents=True, exist_ok=True)
    database_path = temp_dir / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main_module = importlib.import_module("app.main")
    database_module = importlib.import_module("app.database")
    models_module = importlib.import_module("app.models")
    report_builder = importlib.import_module("app.services.report_builder")
    report_builder.generate_local_text = lambda *args, **kwargs: None

    client = TestClient(main_module.app)
    return temp_dir, main_module, database_module, models_module, client


def cleanup_isolated_app(temp_dir: Path) -> None:
    shutil.rmtree(temp_dir, ignore_errors=True)
