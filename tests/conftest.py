"""Pytest configuration ensuring complete SQLite & checkpoint isolation per test session."""

import atexit
import os
import shutil
import tempfile
import pytest

_TEST_TEMP_DIR = tempfile.mkdtemp(prefix="nexus_pytest_")
_TEST_DB_PATH = os.path.join(_TEST_TEMP_DIR, "test_voice_assistant.db")
_TEST_CHECKPOINTS_PATH = os.path.join(_TEST_TEMP_DIR, "test_checkpoints.sqlite")

# Bind test DB paths BEFORE any application/db modules are imported during test collection.
os.environ["NEXUS_TEST_DB_PATH"] = _TEST_DB_PATH
os.environ["DB_PATH"] = _TEST_DB_PATH
os.environ["SQLITE_DB_PATH"] = _TEST_DB_PATH
os.environ["NEXUS_TEST_CHECKPOINTS_DB_PATH"] = _TEST_CHECKPOINTS_PATH
os.environ["CHECKPOINTS_DB_PATH"] = _TEST_CHECKPOINTS_PATH
os.environ.setdefault("DEFAULT_TIMEZONE", "Asia/Kolkata")


def _cleanup_test_tempdir() -> None:
    try:
        from agent.persistence import reset_checkpointer
        reset_checkpointer()
    except Exception:
        pass
    shutil.rmtree(_TEST_TEMP_DIR, ignore_errors=True)


atexit.register(_cleanup_test_tempdir)


@pytest.fixture(scope="session", autouse=True)
def isolated_test_databases():
    """Initialize isolated schema before tests and tear down connections afterward."""
    from db import models as db_models
    from agent import persistence

    db_models.DB_PATH = _TEST_DB_PATH
    persistence.CHECKPOINTS_DB_PATH = _TEST_CHECKPOINTS_PATH
    db_models.init_db()
    yield _TEST_DB_PATH
    persistence.reset_checkpointer()
