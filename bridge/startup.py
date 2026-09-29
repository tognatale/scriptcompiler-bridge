import json
import logging
import os
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


def hand_over_file(port, path):
    body = json.dumps({"path": os.path.abspath(path)}).encode("utf-8")
    request = Request(f"http://127.0.0.1:{port}/open", data=body, method="POST",
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10):
            return True, None
    except HTTPError as e:
        if e.code == 404:
            return False, "The running ScriptCompiler Bridge is too old to open files. Quit it, then open the file again."
        try:
            return False, json.loads(e.read().decode("utf-8")).get("error") or str(e)
        except (ValueError, OSError):
            return False, str(e)
    except (URLError, OSError) as e:
        return False, f"Could not reach the running ScriptCompiler Bridge: {e}"


def wait_for_port_free(host, port, timeout=20.0, poll=0.25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe_port(host, port, timeout=1.0) == "free":
            return True
        time.sleep(poll)
    return False
