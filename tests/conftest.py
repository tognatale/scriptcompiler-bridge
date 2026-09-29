import pytest
from fastapi.testclient import TestClient

from bridge import server, settings


@pytest.fixture(autouse=True)
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "get_settings_path", lambda: path)
    return path


@pytest.fixture
def client():
    return TestClient(server.app, base_url="http://127.0.0.1:9876")
