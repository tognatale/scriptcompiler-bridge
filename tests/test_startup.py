import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bridge import startup


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_server(name):
    body = json.dumps({"name": name}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_probe_finds_a_free_port():
    assert startup.probe_port("127.0.0.1", _free_port(), timeout=0.5) == "free"


def test_probe_finds_a_running_bridge():
    server = _http_server("ScriptCompiler Bridge")
    try:
        assert startup.probe_port("127.0.0.1", server.server_port, timeout=2) == "bridge"
    finally:
        server.shutdown()


def test_probe_finds_another_web_app():
    server = _http_server("Something Else")
    try:
        assert startup.probe_port("127.0.0.1", server.server_port, timeout=2) == "other"
    finally:
        server.shutdown()


def test_probe_finds_another_program():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert startup.probe_port("127.0.0.1", s.getsockname()[1], timeout=0.2) == "other"


def test_first_run_until_settings_are_saved(settings_file):
    assert startup.is_first_run() is True
    startup.mark_first_run_done()
    assert settings_file.exists()
    assert startup.is_first_run() is False


@pytest.mark.parametrize("autostart, updated, first_run, expected", [
    (True, False, True, []),
    (True, False, False, []),
    (False, True, True, ["notify_updated"]),
    (False, False, False, ["notify_running"]),
    (False, False, True, ["notify_running", "open_editor"]),
])
def test_startup_actions(autostart, updated, first_run, expected):
    assert startup.startup_actions(autostart, updated, first_run) == expected


class FakeServer:
    def __init__(self, started):
        self.started = started


class FakeThread:
    def __init__(self, alive):
        self.alive = alive

    def is_alive(self):
        return self.alive


def test_wait_for_server_sees_a_started_server():
    assert startup.wait_for_server(FakeServer(True), FakeThread(True), timeout=1) is True


def test_wait_for_server_sees_a_dead_server_thread():
    assert startup.wait_for_server(FakeServer(False), FakeThread(False), timeout=1) is False


def test_wait_for_server_gives_up_after_the_timeout():
    assert startup.wait_for_server(FakeServer(False), FakeThread(True), timeout=0.3, poll=0.05) is False


def test_wait_for_port_free_returns_once_the_port_is_free(monkeypatch):
    states = iter(["bridge", "bridge", "free"])
    monkeypatch.setattr(startup, "probe_port", lambda host, port, timeout=1.0: next(states))
    assert startup.wait_for_port_free("127.0.0.1", 9876, timeout=2, poll=0.01) is True


def test_wait_for_port_free_gives_up(monkeypatch):
    monkeypatch.setattr(startup, "probe_port", lambda host, port, timeout=1.0: "bridge")
    assert startup.wait_for_port_free("127.0.0.1", 9876, timeout=0.1, poll=0.02) is False


def _open_server(status, reply):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            received.append((self.path, json.loads(self.rfile.read(length)), self.headers.get("Origin")))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(reply).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, received


def test_hand_over_sends_the_file_to_the_running_bridge(tmp_path):
    server, received = _open_server(200, {"success": True})
    try:
        path = str(tmp_path / "clip.funscript")
        assert startup.hand_over_file(server.server_port, path) == (True, None)
        assert received == [("/open", {"path": path}, None)]
    finally:
        server.shutdown()


def test_hand_over_passes_on_the_bridge_error(tmp_path):
    server, _ = _open_server(400, {"success": False, "error": "Only .funscript files can be opened."})
    try:
        result = startup.hand_over_file(server.server_port, str(tmp_path / "notes.txt"))
        assert result == (False, "Only .funscript files can be opened.")
    finally:
        server.shutdown()


def test_hand_over_to_nothing_fails_cleanly(tmp_path):
    ok, error = startup.hand_over_file(_free_port(), str(tmp_path / "clip.funscript"))
    assert ok is False
    assert error


def test_hand_over_to_an_old_bridge_says_to_quit_it(tmp_path):
    server, _ = _open_server(404, {"detail": "Not Found"})
    try:
        ok, error = startup.hand_over_file(server.server_port, str(tmp_path / "clip.funscript"))
        assert ok is False
        assert "too old" in error
    finally:
        server.shutdown()
