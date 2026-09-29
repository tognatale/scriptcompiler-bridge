import pytest

from bridge import url_loader


class FakeProc:
    pid = 4321


@pytest.fixture
def download():
    url_loader._active_downloads["abc"] = {
        "process": FakeProc(), "file_path": "/tmp/x.mp4", "url": "https://x",
        "cancelled": False, "video_info": None,
    }
    url_loader._url_to_download_id["https://x"] = "abc"
    yield
    url_loader._active_downloads.clear()
    url_loader._url_to_download_id.clear()


def test_cancel_on_mac_and_linux_kills_the_whole_group(monkeypatch, download):
    killed = []
    monkeypatch.setattr(url_loader.sys, "platform", "linux")
    monkeypatch.setattr(url_loader.os, "killpg", lambda pid, sig: killed.append((pid, sig)), raising=False)
    monkeypatch.setattr(url_loader.signal, "SIGKILL", 9, raising=False)
    assert url_loader.cancel_download("abc") is True
    assert killed == [(4321, 9)]


def test_cancel_on_windows_kills_the_process_tree(monkeypatch, download):
    calls = []
    monkeypatch.setattr(url_loader.sys, "platform", "win32")
    monkeypatch.setattr(url_loader.subprocess, "call", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(url_loader.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert url_loader.cancel_download("abc") is True
    assert calls == [["taskkill", "/F", "/T", "/PID", "4321"]]


def test_downloads_start_in_their_own_group_on_mac_and_linux(monkeypatch):
    monkeypatch.setattr(url_loader.sys, "platform", "linux")
    assert url_loader._process_group_kwargs() == {"start_new_session": True}


def test_downloads_start_in_their_own_group_on_windows(monkeypatch):
    monkeypatch.setattr(url_loader.sys, "platform", "win32")
    monkeypatch.setattr(url_loader.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(url_loader.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert url_loader._process_group_kwargs() == {"creationflags": 0x200 | 0x08000000}
