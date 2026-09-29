from bridge import linux_desktop


def test_exec_is_quoted():
    path = '/home/me/Apps/My "Bridge"$1%.AppImage'
    assert linux_desktop.desktop_exec(path) == '"/home/me/Apps/My \\"Bridge\\"\\$1%%.AppImage"'


def test_menu_entry_opens_the_app():
    entry = linux_desktop.desktop_entry("/home/me/ScriptCompilerBridge.AppImage")
    assert 'Exec="/home/me/ScriptCompilerBridge.AppImage"\n' in entry
    assert "Icon=scriptcompiler-bridge" in entry
    assert "X-GNOME-Autostart-enabled" not in entry


def test_autostart_entry_passes_the_autostart_flag():
    entry = linux_desktop.desktop_entry("/home/me/ScriptCompilerBridge.AppImage", autostart=True)
    assert 'Exec="/home/me/ScriptCompilerBridge.AppImage" --autostart\n' in entry
    assert "X-GNOME-Autostart-enabled=true" in entry


def test_paths_follow_the_xdg_folders(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert linux_desktop.autostart_path() == tmp_path / "config" / "autostart" / "scriptcompiler-bridge.desktop"
    assert linux_desktop.menu_entry_path() == tmp_path / "data" / "applications" / "scriptcompiler-bridge.desktop"
    assert linux_desktop.icon_path() == tmp_path / "data" / "icons" / "hicolor" / "256x256" / "apps" / "scriptcompiler-bridge.png"


def test_install_menu_entry_writes_the_entry_and_icon(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    appdir = tmp_path / "mount"
    appdir.mkdir()
    (appdir / "scriptcompiler-bridge.png").write_bytes(b"png")
    assert linux_desktop.install_menu_entry("/apps/Bridge.AppImage", str(appdir)) is True
    assert 'Exec="/apps/Bridge.AppImage"' in linux_desktop.menu_entry_path().read_text(encoding="utf-8")
    assert linux_desktop.icon_path().read_bytes() == b"png"


def test_install_menu_entry_without_an_icon_still_writes_the_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert linux_desktop.install_menu_entry("/apps/Bridge.AppImage", None) is True
    assert linux_desktop.menu_entry_path().exists()
    assert not linux_desktop.icon_path().exists()
