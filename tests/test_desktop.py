import pytest

from bridge import desktop


class FakeIcon:
    def __init__(self):
        self.notes = []
        self.stopped = False

    def notify(self, message, title=None):
        self.notes.append((title, message))

    def stop(self):
        self.stopped = True


@pytest.fixture
def calls(monkeypatch):
    seen = {"run": [], "popen": [], "startfile": [], "browser": [], "box": []}
    monkeypatch.setattr(desktop.subprocess, "run", lambda args, **kw: seen["run"].append(args))
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda args, **kw: seen["popen"].append(args))
    monkeypatch.setattr(desktop, "_startfile", lambda path: seen["startfile"].append(path))
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: seen["browser"].append(url))
    monkeypatch.setattr(desktop, "_message_box", lambda text, title: seen["box"].append((title, text)))
    monkeypatch.setattr(desktop, "_tray_icon", None)
    return seen


def _on(monkeypatch, platform):
    monkeypatch.setattr(desktop, "_platform", lambda: platform)


def test_editor_url_points_at_the_connect_flow(monkeypatch):
    monkeypatch.delenv("SC_EDITOR_URL", raising=False)
    assert desktop.editor_url() == "https://scriptcompiler.com/?bridge=connect"


def test_editor_url_can_point_at_a_dev_editor(monkeypatch):
    monkeypatch.setenv("SC_EDITOR_URL", "http://localhost:3000/")
    assert desktop.editor_url() == "http://localhost:3000/?bridge=connect"


def test_open_editor_opens_the_browser(monkeypatch, calls):
    monkeypatch.delenv("SC_EDITOR_URL", raising=False)
    desktop.open_editor()
    assert calls["browser"] == ["https://scriptcompiler.com/?bridge=connect"]


def test_notify_on_windows_uses_the_tray_icon(monkeypatch, calls):
    _on(monkeypatch, "win32")
    icon = FakeIcon()
    desktop.set_tray_icon(icon)
    desktop.notify("ScriptCompiler Bridge", "The bridge is running")
    assert icon.notes == [("ScriptCompiler Bridge", "The bridge is running")]


def test_notify_on_windows_without_tray_does_not_fail(monkeypatch, calls):
    _on(monkeypatch, "win32")
    desktop.notify("ScriptCompiler Bridge", "The bridge is running")
    assert calls["run"] == []


def test_notify_on_mac_uses_osascript(monkeypatch, calls):
    _on(monkeypatch, "darwin")
    desktop.notify("ScriptCompiler Bridge", "The bridge is running")
    assert calls["run"] == [[
        "osascript", "-e",
        'display notification "The bridge is running" with title "ScriptCompiler Bridge"',
    ]]


def test_applescript_text_is_escaped():
    assert desktop._applescript_string('say "hi" \\ now') == '"say \\"hi\\" \\\\ now"'


def test_show_error_on_windows_uses_a_message_box(monkeypatch, calls):
    _on(monkeypatch, "win32")
    desktop.show_error("Port 9876 is used by another program.")
    assert calls["box"] == [("ScriptCompiler Bridge", "Port 9876 is used by another program.")]


def test_show_error_on_mac_uses_an_alert(monkeypatch, calls):
    _on(monkeypatch, "darwin")
    desktop.show_error("Port 9876 is used by another program.")
    assert calls["run"] == [[
        "osascript", "-e",
        'display alert "ScriptCompiler Bridge" message "Port 9876 is used by another program." as critical',
    ]]


@pytest.mark.parametrize("platform, key, expected", [
    ("win32", "startfile", "C:\\logs"),
    ("darwin", "popen", ["open", "C:\\logs"]),
    ("linux", "popen", ["xdg-open", "C:\\logs"]),
])
def test_open_path_uses_the_system_opener(monkeypatch, calls, platform, key, expected):
    _on(monkeypatch, platform)
    desktop.open_path("C:\\logs")
    assert calls[key] == [expected]


def test_stop_tray_stops_the_icon(calls):
    icon = FakeIcon()
    desktop.set_tray_icon(icon)
    desktop.stop_tray()
    assert icon.stopped is True


def test_stop_tray_without_icon_does_nothing(calls):
    desktop.stop_tray()
