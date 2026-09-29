import asyncio

from bridge import file_handler, grants
from bridge.pickers import PickerUnavailable


def run(coro):
    return asyncio.run(coro)


def test_linux_open_video_uses_the_system_picker(monkeypatch, tmp_path):
    monkeypatch.setattr(file_handler, "_platform", lambda: "linux")
    video = str(tmp_path / "clip.mp4")
    seen = []

    def fake_pick(title, extensions, label):
        seen.append((title, label))
        return video

    monkeypatch.setattr(file_handler, "pick_file", fake_pick)
    assert run(file_handler.open_video_dialog()) == {"path": video, "name": "clip.mp4"}
    assert seen == [("Open Video", "Video files")]
    assert grants.can_read(video)


def test_windows_open_video_keeps_the_tk_dialog(monkeypatch):
    monkeypatch.setattr(file_handler, "_platform", lambda: "win32")
    monkeypatch.setattr(file_handler, "_tk_open_file", lambda title, filetypes: None)
    assert run(file_handler.open_video_dialog()) is None


def test_missing_picker_returns_the_reason(monkeypatch):
    monkeypatch.setattr(file_handler, "_platform", lambda: "linux")

    def missing(*args):
        raise PickerUnavailable("Install zenity")

    monkeypatch.setattr(file_handler, "pick_file", missing)
    assert run(file_handler.open_video_dialog()) == {"error": "Install zenity"}


def test_linux_save_funscript_writes_to_the_picked_path(monkeypatch, tmp_path):
    monkeypatch.setattr(file_handler, "_platform", lambda: "linux")
    target = tmp_path / "clip.funscript"
    monkeypatch.setattr(file_handler, "pick_save_file", lambda title, name, extensions, label: str(target))
    result = run(file_handler.save_funscript_dialog("{}", "clip.funscript"))
    assert result == {"path": str(target), "name": "clip.funscript"}
    assert target.read_text(encoding="utf-8") == "{}"
