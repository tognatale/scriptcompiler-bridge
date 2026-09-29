import subprocess

import pytest

from bridge import pickers


class Result:
    def __init__(self, stdout=b"", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


@pytest.fixture
def runs(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(pickers.tempfile, "gettempdir", lambda: str(tmp_path))

    def use(result):
        def fake_run(args, **kwargs):
            seen.append((args, kwargs))
            if isinstance(result, Exception):
                raise result
            return result
        monkeypatch.setattr(pickers, "_run", fake_run)
        return seen

    return use


def _on(monkeypatch, platform):
    monkeypatch.setattr(pickers, "_platform", lambda: platform)


def test_windows_picker_returns_the_chosen_folder(monkeypatch, runs, tmp_path):
    _on(monkeypatch, "win32")
    seen = runs(Result("D:\\Vidéos\r\n".encode("utf-8")))
    assert pickers.pick_folder() == "D:\\Vidéos"
    args, kwargs = seen[0]
    assert args[0] == "powershell"
    assert args[-2] == "-File"
    assert kwargs["creationflags"] == 0x08000000
    script = (tmp_path / "sc_folder_pick.ps1").read_text(encoding="utf-8-sig")
    assert "TopMost" in script
    assert "OutputEncoding" in script


def test_windows_picker_cancel_returns_none(monkeypatch, runs):
    _on(monkeypatch, "win32")
    runs(Result(b"\r\n"))
    assert pickers.pick_folder() is None


def test_mac_picker_returns_the_chosen_folder(monkeypatch, runs):
    _on(monkeypatch, "darwin")
    seen = runs(Result("/Users/me/Vidéos/\n".encode("utf-8")))
    assert pickers.pick_folder() == "/Users/me/Vidéos/"
    args, _ = seen[0]
    assert args[0] == "osascript"
    assert any("choose folder" in part for part in args)


def test_mac_picker_cancel_returns_none(monkeypatch, runs):
    _on(monkeypatch, "darwin")
    runs(Result(b"", returncode=1))
    assert pickers.pick_folder() is None


def test_picker_failure_returns_none(monkeypatch, runs):
    _on(monkeypatch, "win32")
    runs(subprocess.TimeoutExpired("powershell", 300))
    assert pickers.pick_folder() is None


def test_other_platforms_have_no_picker_yet(monkeypatch, runs):
    _on(monkeypatch, "linux")
    seen = runs(Result(b"/home/me/videos\n"))
    assert pickers.pick_folder() is None
    assert seen == []
