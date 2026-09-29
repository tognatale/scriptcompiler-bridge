import pytest

import main
from bridge.config import BRIDGE_NAME, BRIDGE_VERSION


@pytest.fixture
def calls(monkeypatch):
    seen = {"editor": 0, "errors": [], "notes": [], "marked": 0}
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main, "open_editor", lambda: seen.__setitem__("editor", seen["editor"] + 1))
    monkeypatch.setattr(main, "show_error", lambda message: seen["errors"].append(message))
    monkeypatch.setattr(main, "notify", lambda title, message: seen["notes"].append((title, message)))
    monkeypatch.setattr(main, "mark_first_run_done", lambda: seen.__setitem__("marked", seen["marked"] + 1))
    return seen


def test_flags_default_to_off():
    args = main.parse_args([])
    assert args.autostart is False
    assert args.updated is False


def test_flags_can_be_set():
    args = main.parse_args(["--autostart", "--updated"])
    assert args.autostart is True
    assert args.updated is True


def test_second_copy_opens_the_editor_and_quits(monkeypatch, calls):
    monkeypatch.setattr(main, "probe_port", lambda host, port: "bridge")
    assert main.main(["--port", "9899"]) == 0
    assert calls["editor"] == 1
    assert calls["errors"] == []


def test_taken_port_shows_an_error_and_quits(monkeypatch, calls):
    monkeypatch.setattr(main, "probe_port", lambda host, port: "other")
    assert main.main(["--port", "9899"]) == 1
    assert len(calls["errors"]) == 1
    assert "9899" in calls["errors"][0]
    assert calls["editor"] == 0


def test_announce_running(calls):
    main.announce(["notify_running"])
    assert calls["notes"][0][0] == BRIDGE_NAME
    assert "is running" in calls["notes"][0][1]


def test_announce_update(calls):
    main.announce(["notify_updated"])
    assert BRIDGE_VERSION in calls["notes"][0][1]


def test_announce_first_run_opens_the_editor_once(calls):
    main.announce(["notify_running", "open_editor"])
    assert calls["editor"] == 1
    assert calls["marked"] == 1


def test_linux_runs_without_a_tray(monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "linux")
    assert main.use_tray(main.parse_args([])) is False


def test_windows_uses_the_tray_unless_turned_off(monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "win32")
    assert main.use_tray(main.parse_args([])) is True
    assert main.use_tray(main.parse_args(["--no-tray"])) is False


@pytest.mark.parametrize("platform, text", [
    ("win32", "system tray"),
    ("darwin", "menu bar"),
    ("linux", "in the background"),
])
def test_running_message_matches_the_system(monkeypatch, platform, text):
    monkeypatch.setattr(main.sys, "platform", platform)
    assert text in main.running_message()


def test_start_after_an_update_waits_for_the_old_bridge(monkeypatch, calls):
    waited = []
    monkeypatch.setattr(main, "wait_for_port_free", lambda host, port: waited.append(port))
    monkeypatch.setattr(main, "probe_port", lambda host, port: "bridge")
    main.main(["--updated", "--port", "9899"])
    assert waited == [9899]


class FakeServer:
    def __init__(self, config):
        self.started = True
        self.should_exit = False

    def run(self):
        pass


def test_a_started_bridge_keeps_yt_dlp_up_to_date(monkeypatch, calls):
    started = []
    monkeypatch.setattr(main, "probe_port", lambda host, port: "free")
    monkeypatch.setattr(main, "is_first_run", lambda: False)
    monkeypatch.setattr(main, "sync_autostart", lambda: None)
    monkeypatch.setattr(main, "set_shutdown_callback", lambda callback: None)
    monkeypatch.setattr(main, "wait_for_server", lambda server, thread: True)
    monkeypatch.setattr(main.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(main, "start_ytdlp_updates", lambda: started.append(True))
    assert main.main(["--no-tray", "--port", "9899"]) == 0
    assert started == [True]


def test_mac_removes_the_old_app_after_the_old_bridge_is_gone(monkeypatch, calls):
    steps = []
    monkeypatch.setattr(main.sys, "platform", "darwin")
    monkeypatch.setattr(main, "wait_for_port_free", lambda host, port: steps.append("wait"))
    monkeypatch.setattr(main, "cleanup_old_mac_app", lambda: steps.append("cleanup"))
    monkeypatch.setattr(main, "probe_port", lambda host, port: "bridge")
    main.main(["--updated", "--port", "9899"])
    assert steps == ["wait", "cleanup"]
