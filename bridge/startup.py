import json
import logging
import os
import socket
import time
from urllib.request import urlopen

from . import settings
from .config import BRIDGE_NAME

logger = logging.getLogger(__name__)


def probe_port(host, port, timeout=2.0):
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as resp:
            if json.loads(resp.read().decode("utf-8")).get("name") == BRIDGE_NAME:
                return "bridge"
    except Exception:
        pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name != "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return "other"
    return "free"


def is_first_run():
    return not settings.get_settings_path().exists()


def mark_first_run_done():
    if is_first_run():
        settings.save_settings(settings.load_settings())


def startup_actions(autostart, updated, first_run):
    if autostart:
        return []
    if updated:
        return ["notify_updated"]
    if first_run:
        return ["notify_running", "open_editor"]
    return ["notify_running"]


def wait_for_server(server, thread, timeout=30.0, poll=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.started:
            return True
        if not thread.is_alive():
            return False
        time.sleep(poll)
    return bool(server.started)
