import pytest
from starlette.websockets import WebSocketDisconnect

from bridge import request_guard, server

EDITOR_ORIGIN = "https://scriptcompiler.com"
OTHER_ORIGIN = "https://evil.example.com"
WS_URL = "ws://127.0.0.1:9876/ws/tracking"


@pytest.fixture
def stub_tracker(monkeypatch):
    async def initialize():
        return {"success": True}

    monkeypatch.setattr(server.tracker, "initialize", initialize)


@pytest.fixture
def default_hosts(monkeypatch):
    monkeypatch.setattr(request_guard, "_allowed_hosts", {"127.0.0.1", "localhost"})


def test_request_without_origin_passes(client):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("origin", [
    EDITOR_ORIGIN,
    "https://app.scriptcompiler.com",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
])
def test_editor_origins_pass(client, origin):
    assert client.get("/health", headers={"Origin": origin}).status_code == 200


@pytest.mark.parametrize("origin", [
    OTHER_ORIGIN,
    "https://scriptcompiler.com.evil.example.com",
    "https://evilscriptcompiler.com",
    "http://scriptcompiler.com",
    "null",
])
def test_other_origins_are_blocked(client, origin):
    assert client.get("/health", headers={"Origin": origin}).status_code == 403


def test_blocked_origin_cannot_trigger_actions(client, monkeypatch):
    calls = []
    monkeypatch.setattr(server, "scan_and_cache", lambda: calls.append(True) or [])
    response = client.post(
        "/videos/refresh",
        headers={"Origin": OTHER_ORIGIN, "Content-Type": "text/plain"},
    )
    assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize("host", ["127.0.0.1:9876", "localhost:9876", "LOCALHOST", "127.0.0.1"])
def test_loopback_hosts_pass(client, host):
    assert client.get("/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example.com:9876", "evil.example.com", "192.168.1.20:9876"])
def test_other_hosts_are_blocked(client, host):
    assert client.get("/health", headers={"Host": host}).status_code == 403


def test_bind_host_is_allowed(client, default_hosts):
    request_guard.allow_bind_host("192.168.1.20")
    assert client.get("/health", headers={"Host": "192.168.1.20:9876"}).status_code == 200
    assert client.get("/health", headers={"Host": "evil.example.com"}).status_code == 403


def test_wildcard_bind_allows_any_host(client, default_hosts):
    request_guard.allow_bind_host("0.0.0.0")
    assert client.get("/health", headers={"Host": "192.168.1.20:9876"}).status_code == 200


def test_websocket_from_other_origin_is_rejected(client, stub_tracker):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(WS_URL, headers={"Origin": OTHER_ORIGIN}):
            pass


def test_websocket_from_editor_works(client, stub_tracker):
    with client.websocket_connect(WS_URL, headers={"Origin": EDITOR_ORIGIN}) as ws:
        ws.send_json({"command": "ping", "_requestId": 1})
        assert ws.receive_json() == {"success": True, "pong": True, "command": "ping", "_requestId": 1}
