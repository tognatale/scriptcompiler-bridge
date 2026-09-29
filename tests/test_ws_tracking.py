import logging

import pytest

from bridge import server

WS_URL = "ws://127.0.0.1:9876/ws/tracking"


@pytest.fixture
def stub_tracker(monkeypatch):
    async def initialize():
        return {"success": True}

    monkeypatch.setattr(server.tracker, "initialize", initialize)


def test_disconnect_is_not_logged_as_an_error(client, stub_tracker, caplog):
    with caplog.at_level(logging.INFO, logger="bridge.server"):
        with client.websocket_connect(WS_URL) as ws:
            ws.send_json({"command": "ping", "_requestId": 1})
            ws.receive_json()
    assert "Tracking WebSocket disconnected" in caplog.text
    assert "Tracking WebSocket error" not in caplog.text
