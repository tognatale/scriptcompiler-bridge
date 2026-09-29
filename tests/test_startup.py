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
