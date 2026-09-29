import os
import shutil

import pytest

from bridge import updater


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


def _fake_download(url, dest):
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
