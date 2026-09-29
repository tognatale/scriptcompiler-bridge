import pytest

from bridge import linux_desktop


class Result:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


@pytest.fixture(autouse=True)
def tools(monkeypatch):
    state = {"available": set(), "default": "", "commands": []}
    monkeypatch.setattr(linux_desktop.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if name in state["available"] else None)

    def fake_run(args, **kwargs):
        state["commands"].append(list(args))
        if args[:3] == ["xdg-mime", "query", "default"]:
            return Result(state["default"])
        return Result()

    monkeypatch.setattr(linux_desktop.subprocess, "run", fake_run)
    return state


@pytest.fixture
def data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "data"


def test_exec_is_quoted():
    path = '/home/me/Apps/My "Bridge"$1%.AppImage'
    assert linux_desktop.desktop_exec(path) == '"/home/me/Apps/My \\"Bridge\\"\\$1%%.AppImage"'


def test_menu_entry_opens_the_app_and_funscript_files():
    entry = linux_desktop.desktop_entry("/home/me/ScriptCompilerBridge.AppImage")
    assert 'Exec="/home/me/ScriptCompilerBridge.AppImage" %f\n' in entry
    assert "MimeType=application/x-funscript;" in entry
    assert "Icon=scriptcompiler-bridge" in entry
    assert "X-GNOME-Autostart-enabled" not in entry


def test_autostart_entry_passes_the_autostart_flag():
    entry = linux_desktop.desktop_entry("/home/me/ScriptCompilerBridge.AppImage", autostart=True)
    assert 'Exec="/home/me/ScriptCompilerBridge.AppImage" --autostart\n' in entry
    assert "X-GNOME-Autostart-enabled=true" in entry
    assert "MimeType" not in entry


def test_paths_follow_the_xdg_folders(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert linux_desktop.autostart_path() == tmp_path / "config" / "autostart" / "scriptcompiler-bridge.desktop"
    assert linux_desktop.menu_entry_path() == tmp_path / "data" / "applications" / "scriptcompiler-bridge.desktop"
    assert linux_desktop.icon_path() == tmp_path / "data" / "icons" / "hicolor" / "256x256" / "apps" / "scriptcompiler-bridge.png"
    assert linux_desktop.mime_package_path() == tmp_path / "data" / "mime" / "packages" / "scriptcompiler-bridge.xml"


def test_install_menu_entry_writes_the_entry_and_icon(data_home, tmp_path):
    appdir = tmp_path / "mount"
    appdir.mkdir()
    (appdir / "scriptcompiler-bridge.png").write_bytes(b"png")
    assert linux_desktop.install_menu_entry("/apps/Bridge.AppImage", str(appdir)) is True
    assert 'Exec="/apps/Bridge.AppImage" %f' in linux_desktop.menu_entry_path().read_text(encoding="utf-8")
    assert linux_desktop.icon_path().read_bytes() == b"png"


def test_install_menu_entry_without_an_icon_still_writes_the_entry(data_home):
    assert linux_desktop.install_menu_entry("/apps/Bridge.AppImage", None) is True
    assert linux_desktop.menu_entry_path().exists()
    assert not linux_desktop.icon_path().exists()


def test_install_registers_the_funscript_type(data_home, tools):
    tools["available"].update({"update-mime-database", "update-desktop-database", "xdg-mime"})
    linux_desktop.install_menu_entry("/apps/Bridge.AppImage", None)
    xml = linux_desktop.mime_package_path().read_text(encoding="utf-8")
    assert 'type="application/x-funscript"' in xml
    assert '<glob pattern="*.funscript"/>' in xml
    assert ["update-mime-database", str(data_home / "mime")] in tools["commands"]
    assert ["update-desktop-database", str(data_home / "applications")] in tools["commands"]
    assert ["xdg-mime", "default", "scriptcompiler-bridge.desktop", "application/x-funscript"] in tools["commands"]


def test_install_keeps_another_default_app(data_home, tools):
    tools["available"].add("xdg-mime")
    tools["default"] = "openfunscripter.desktop\n"
    linux_desktop.install_menu_entry("/apps/Bridge.AppImage", None)
    assert ["xdg-mime", "default", "scriptcompiler-bridge.desktop", "application/x-funscript"] not in tools["commands"]


def test_unchanged_files_skip_the_database_updates(data_home, tools):
    tools["available"].update({"update-mime-database", "update-desktop-database"})
    linux_desktop.install_menu_entry("/apps/Bridge.AppImage", None)
    tools["commands"].clear()
    linux_desktop.install_menu_entry("/apps/Bridge.AppImage", None)
    assert tools["commands"] == []
