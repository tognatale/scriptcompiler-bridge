import logging
from logging.handlers import RotatingFileHandler

import pytest

from bridge import logs


@pytest.fixture
def root_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield root
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)


def _flush(root):
    for handler in root.handlers:
        handler.flush()


def test_bridge_logs_go_to_the_log_file(tmp_path, root_logging):
    path = logs.setup_logging(tmp_path)
    logging.getLogger("bridge.server").info("hello from the test")
    _flush(root_logging)
    assert path == tmp_path / "bridge.log"
    assert "hello from the test" in path.read_text(encoding="utf-8")


def test_server_logs_go_to_the_log_file(tmp_path, root_logging):
    path = logs.setup_logging(tmp_path)
    logging.getLogger("uvicorn.error").error("address already in use")
    _flush(root_logging)
    assert "address already in use" in path.read_text(encoding="utf-8")


def test_log_file_keeps_three_files_of_one_mb(tmp_path, root_logging):
    logs.setup_logging(tmp_path)
    handler = next(h for h in root_logging.handlers if isinstance(h, RotatingFileHandler))
    assert handler.maxBytes == 1_000_000
    assert handler.backupCount == 2


def test_default_log_folder_is_in_the_settings_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(logs.Path, "home", lambda: tmp_path)
    assert logs.log_dir() == tmp_path / ".scriptcompiler-bridge" / "logs"
