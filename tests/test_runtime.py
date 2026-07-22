"""Integration tests for engine runtime start, stop, get_status, and run_once."""

import pytest
from archangel.engine import runtime
from archangel.storage import StorageBackend
from archangel.events import EventBus


@pytest.fixture(autouse=True)
def clean_singletons():
    StorageBackend.reset_instance()
    EventBus.reset_instance()
    yield
    StorageBackend.reset_instance()
    EventBus.reset_instance()


def test_engine_start_stop():
    runtime.start(debug=True)
    status = runtime.get_status()
    assert status["Engine"] == "running"

    runtime.stop()
    status = runtime.get_status()
    assert status["Engine"] == "stopped"


def test_run_once_execution(monkeypatch, tmp_path):
    # Mock StorageBackend to use a temporary DB
    test_storage = StorageBackend(db_path=tmp_path / "test.db")
    monkeypatch.setattr(StorageBackend, "get_instance", lambda: test_storage)

    result = runtime.run_once()
    assert "posts_collected" in result
    assert "leads_identified" in result
    assert "duration_ms" in result
    assert result["duration_ms"] >= 0
