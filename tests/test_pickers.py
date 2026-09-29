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


def test_unknown_platforms_have_no_picker(monkeypatch, runs):
    _on(monkeypatch, "freebsd")
    seen = runs(Result(b"/home/me/videos\n"))
    assert pickers.pick_folder() is None
    assert seen == []


@pytest.fixture
def tools(monkeypatch):
    available = set()
    monkeypatch.setattr(pickers.shutil, "which", lambda name: f"/usr/bin/{name}" if name in available else None)
    return available


def test_linux_folder_picker_uses_zenity(monkeypatch, runs, tools):
    _on(monkeypatch, "linux")
    tools.update({"zenity", "kdialog"})
    seen = runs(Result("/home/me/Vidéos\n".encode("utf-8")))
    assert pickers.pick_folder() == "/home/me/Vidéos"
    args, kwargs = seen[0]
    assert args[:3] == ["zenity", "--file-selection", "--directory"]
    assert "env" in kwargs


def test_linux_folder_picker_falls_back_to_kdialog(monkeypatch, runs, tools):
    _on(monkeypatch, "linux")
    tools.add("kdialog")
    seen = runs(Result(b"/home/me/videos\n"))
    assert pickers.pick_folder() == "/home/me/videos"
    args, _ = seen[0]
    assert args[0] == "kdialog"
    assert "--getexistingdirectory" in args


def test_linux_without_a_picker_says_what_to_install(monkeypatch, runs, tools):
    _on(monkeypatch, "linux")
    runs(Result(b""))
    with pytest.raises(pickers.PickerUnavailable, match="zenity"):
        pickers.pick_folder()


def test_linux_cancel_returns_none(monkeypatch, runs, tools):
    _on(monkeypatch, "linux")
    tools.add("zenity")
    runs(Result(b"", returncode=1))
    assert pickers.pick_folder() is None


def test_linux_open_file_filters_by_extension(monkeypatch, runs, tools):
    _on(monkeypatch, "linux")
    tools.add("zenity")
    seen = runs(Result(b"/home/me/a.mp4\n"))
    assert pickers.pick_file("Open Video", ["mp4", "mkv"], "Video files") == "/home/me/a.mp4"
    args, _ = seen[0]
    assert "--title=Open Video" in args
    assert "--file-filter=Video files | *.mp4 *.mkv" in args


def test_linux_open_file_with_kdialog(monkeypatch, runs, tools):
    _on(monkeypatch, "linux")
    tools.add("kdialog")
    seen = runs(Result(b"/home/me/a.mp4\n"))
    assert pickers.pick_file("Open Video", ["mp4"], "Video files") == "/home/me/a.mp4"
    args, _ = seen[0]
    assert args[args.index("--getopenfilename") + 2] == "*.mp4|Video files"


def test_linux_save_file_starts_with_the_default_name(monkeypatch, runs, tools):
    _on(monkeypatch, "linux")
    tools.add("zenity")
    seen = runs(Result(b"/home/me/clip.funscript\n"))
    result = pickers.pick_save_file("Save Funscript", "clip.funscript", ["funscript"], "Funscript files")
    assert result == "/home/me/clip.funscript"
    args, _ = seen[0]
    assert "--save" in args
    assert any(a.startswith("--filename=") and a.endswith("clip.funscript") for a in args)


def test_mac_open_file_uses_choose_file(monkeypatch, runs):
    _on(monkeypatch, "darwin")
    seen = runs(Result(b"/Users/me/a.mp4\n"))
    assert pickers.pick_file("Open Video", ["mp4"]) == "/Users/me/a.mp4"
    assert any('choose file with prompt "Open Video"' in part for part in seen[0][0])


def test_mac_save_file_uses_choose_file_name(monkeypatch, runs):
    _on(monkeypatch, "darwin")
    seen = runs(Result(b"/Users/me/clip.funscript\n"))
    assert pickers.pick_save_file("Save Funscript", "clip.funscript") == "/Users/me/clip.funscript"
    expected = 'choose file name with prompt "Save Funscript" default name "clip.funscript"'
    assert any(expected in part for part in seen[0][0])
