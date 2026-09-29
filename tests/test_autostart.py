from bridge import settings

EXE = "C:\\Program Files\\ScriptCompiler Bridge\\ScriptCompilerBridge.exe"
APP = "/Applications/ScriptCompilerBridge.app/Contents/MacOS/ScriptCompilerBridge"


def test_windows_login_command_has_the_autostart_flag():
    assert settings._autostart_command(EXE) == f'"{EXE}" --autostart'


def test_mac_login_item_has_the_autostart_flag():
    plist = settings._macos_plist(APP)
    assert f"<string>{APP}</string>" in plist
    assert "<string>--autostart</string>" in plist
    assert plist.index(APP) < plist.index("--autostart")


def _patch(monkeypatch, exe, enabled):
    calls = []
    monkeypatch.setattr(settings, "_get_app_executable", lambda: exe)
    monkeypatch.setattr(settings, "_get_autostart", lambda: enabled)
    monkeypatch.setattr(settings, "_set_autostart", lambda value: calls.append(value))
    return calls


def test_sync_rewrites_an_enabled_login_entry(monkeypatch):
    calls = _patch(monkeypatch, EXE, True)
    settings.sync_autostart()
    assert calls == [True]


def test_sync_leaves_a_disabled_login_entry_alone(monkeypatch):
    calls = _patch(monkeypatch, EXE, False)
    settings.sync_autostart()
    assert calls == []


def test_sync_does_nothing_when_run_from_source(monkeypatch):
    calls = _patch(monkeypatch, None, True)
    settings.sync_autostart()
    assert calls == []


def test_appimage_path_is_the_app_executable(monkeypatch):
    monkeypatch.setenv("APPIMAGE", "/home/me/ScriptCompilerBridge.AppImage")
    assert settings._get_app_executable() == "/home/me/ScriptCompilerBridge.AppImage"


def test_linux_autostart_writes_and_removes_the_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_platform", lambda: "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPIMAGE", "/home/me/ScriptCompilerBridge.AppImage")
    settings._set_autostart(True)
    entry = tmp_path / "autostart" / "scriptcompiler-bridge.desktop"
    assert "--autostart" in entry.read_text(encoding="utf-8")
    assert settings._get_autostart() is True
    settings._set_autostart(False)
    assert not entry.exists()
    assert settings._get_autostart() is False


def test_linux_autostart_needs_the_app(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_platform", lambda: "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("APPIMAGE", raising=False)
    settings._set_autostart(True)
    assert settings._get_autostart() is False
