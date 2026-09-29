import os
import shutil
import threading
import time

import pytest

from bridge import server, updater


@pytest.mark.parametrize("platform, machine, name, expected", [
    ("win32", "AMD64", "ScriptCompilerBridge-Setup-1.3.0.exe", True),
    ("win32", "AMD64", "ScriptCompilerBridge-1.3.0-macOS.dmg", False),
    ("darwin", "arm64", "ScriptCompilerBridge-1.3.0-macOS.dmg", True),
    ("darwin", "arm64", "ScriptCompilerBridge-1.3.0-x86_64.AppImage", False),
    ("linux", "x86_64", "ScriptCompilerBridge-1.3.0-x86_64.AppImage", True),
    ("linux", "aarch64", "ScriptCompilerBridge-1.3.0-x86_64.AppImage", False),
    ("linux", "x86_64", "ScriptCompilerBridge-Setup-1.3.0.exe", False),
])
def test_match_asset(monkeypatch, platform, machine, name, expected):
    monkeypatch.setattr(updater, "_platform", lambda: platform)
    monkeypatch.setattr(updater.platform_module, "machine", lambda: machine)
    assert updater._match_asset(name) is expected


def _fake_download(url, dest, progress=None):
    with open(dest, "wb") as f:
        f.write(b"new")


@pytest.fixture
def linux_update(monkeypatch, tmp_path):
    target = tmp_path / "ScriptCompilerBridge.AppImage"
    target.write_bytes(b"old")
    monkeypatch.setattr(updater, "_platform", lambda: "linux")
    monkeypatch.setenv("APPIMAGE", str(target))
    monkeypatch.setitem(updater._update_cache, "download_url", "https://x/new.AppImage")
    monkeypatch.setitem(updater._update_cache, "latest_version", "1.3.1")
    monkeypatch.setattr(updater, "_download", _fake_download)
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: launched.append((args, kw)))
    return target, launched


def test_linux_update_swaps_the_appimage_and_restarts(linux_update):
    target, launched = linux_update
    quits = []
    assert updater.download_and_run_update(lambda: quits.append(True)) == {"success": True}
    assert target.read_bytes() == b"new"
    args, kwargs = launched[0]
    assert args == [str(target), "--updated"]
    assert "APPIMAGE" not in kwargs["env"]
    assert kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert quits == [True]


def test_linux_update_needs_the_appimage(linux_update, monkeypatch):
    monkeypatch.delenv("APPIMAGE")
    result = updater.download_and_run_update(lambda: None)
    assert result["success"] is False
    assert "AppImage" in result["error"]


@pytest.fixture
def mac_update(monkeypatch, tmp_path):
    app = tmp_path / "Applications" / "ScriptCompilerBridge.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "version.txt").write_text("old")
    monkeypatch.setattr(updater, "_platform", lambda: "darwin")
    monkeypatch.setattr(updater.sys, "executable", str(app / "Contents" / "MacOS" / "ScriptCompilerBridge"))
    monkeypatch.setitem(updater._update_cache, "download_url", "https://x/new.dmg")
    monkeypatch.setitem(updater._update_cache, "latest_version", "1.3.1")
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(updater, "_download", _fake_download)
    commands = []

    def fake_run(args, **kwargs):
        commands.append(args)
        if args[:2] == ["hdiutil", "attach"]:
            source = os.path.join(args[args.index("-mountpoint") + 1], "ScriptCompilerBridge.app")
            os.makedirs(source, exist_ok=True)
            with open(os.path.join(source, "version.txt"), "w") as f:
                f.write("new")
        if args[0] == "ditto":
            shutil.copytree(args[1], args[2])

    monkeypatch.setattr(updater.subprocess, "run", fake_run)
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: launched.append(args))
    return app, commands, launched


def test_mac_update_replaces_the_app_and_restarts(mac_update):
    app, commands, launched = mac_update
    assert updater.download_and_run_update(lambda: None) == {"success": True}
    assert (app / "version.txt").read_text() == "new"
    assert launched == [["open", "-n", str(app), "--args", "--updated"]]
    assert any(c[:2] == ["hdiutil", "detach"] for c in commands)


def test_mac_update_falls_back_to_the_disk_image(mac_update, monkeypatch):
    app, commands, launched = mac_update
    monkeypatch.setattr(updater.os, "access", lambda path, mode: False)
    assert updater.download_and_run_update(lambda: None) == {"success": True, "manual": True}
    assert launched[0][0] == "open"
    assert launched[0][1].endswith(".dmg")


def test_cleanup_removes_the_old_mac_app(mac_update):
    app, _, _ = mac_update
    old = app.parent / "ScriptCompilerBridge.app.old"
    old.mkdir()
    updater.cleanup_old_mac_app()
    assert not old.exists()


class FakeResponse:
    def __init__(self, chunks, length):
        self.chunks = list(chunks)
        self.headers = {"Content-Length": str(length)}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.chunks.pop(0) if self.chunks else b""


def test_download_reports_the_percent(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "urlopen", lambda request, timeout: FakeResponse([b"ab", b"cd"], 4))
    seen = []
    target = tmp_path / "setup.exe"
    updater._download("https://x/setup.exe", str(target), seen.append)
    assert target.read_bytes() == b"abcd"
    assert seen == [50, 99]


@pytest.fixture
def background(monkeypatch):
    monkeypatch.setattr(updater, "_status", {"state": "idle", "percent": 0, "error": None})
    monkeypatch.setattr(updater, "SHUTDOWN_DELAY", 0)
    monkeypatch.setitem(updater._update_cache, "download_url", "https://x/new")


def _wait_for(check, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.01)
    return False


def test_an_update_downloads_in_the_background_with_progress(monkeypatch, background):
    release = threading.Event()
    quits = []

    def fake_update(shutdown_callback=None, progress=None):
        progress(40)
        release.wait(2)
        return {"success": True}

    monkeypatch.setattr(updater, "download_and_run_update", fake_update)
    assert updater.start_update(lambda: quits.append(True)) == {"success": True, "started": True}
    assert _wait_for(lambda: updater.get_update_status()["percent"] == 40)
    assert updater.get_update_status()["state"] == "downloading"
    release.set()
    assert _wait_for(lambda: quits == [True])
    assert updater.get_update_status()["state"] == "installing"


def test_a_second_start_does_not_download_twice(monkeypatch, background):
    release = threading.Event()
    calls = []

    def fake_update(shutdown_callback=None, progress=None):
        calls.append(True)
        release.wait(2)
        return {"success": True}

    monkeypatch.setattr(updater, "download_and_run_update", fake_update)
    updater.start_update(None)
    assert updater.start_update(None) == {"success": True, "started": True}
    release.set()
    assert _wait_for(lambda: updater.get_update_status()["state"] == "installing")
    assert calls == [True]


def test_a_failed_update_says_why_and_keeps_running(monkeypatch, background):
    quits = []
    monkeypatch.setattr(updater, "download_and_run_update", lambda shutdown_callback=None, progress=None: {
        "success": False, "error": "Disk full",
    })
    updater.start_update(lambda: quits.append(True))
    assert _wait_for(lambda: updater.get_update_status()["state"] == "failed")
    assert updater.get_update_status()["error"] == "Disk full"
    assert quits == []


def test_a_manual_mac_update_is_reported_before_the_bridge_quits(monkeypatch, background):
    states = []
    monkeypatch.setattr(updater, "download_and_run_update", lambda shutdown_callback=None, progress=None: {
        "success": True, "manual": True,
    })
    updater.start_update(lambda: states.append(updater.get_update_status()["state"]))
    assert _wait_for(lambda: states == ["manual"])


def test_an_update_needs_a_download_url(background, monkeypatch):
    monkeypatch.setitem(updater._update_cache, "download_url", None)
    assert updater.start_update(None) == {"success": False, "error": "No download URL available"}


def test_the_update_endpoints(client, monkeypatch, background):
    monkeypatch.setattr(server, "start_update", lambda shutdown_callback=None: {"success": True, "started": True})
    assert client.post("/update/apply").json() == {"success": True, "started": True}
    assert client.get("/update/status").json() == {"state": "idle", "percent": 0, "error": None}
