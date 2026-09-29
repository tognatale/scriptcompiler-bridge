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
