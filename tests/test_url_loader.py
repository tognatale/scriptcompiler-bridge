import asyncio
import os

import pytest

from bridge import url_loader


class FakeYtdlp:
    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self.stdout_bytes = stdout
        self.stderr_bytes = stderr
        self.returncode = returncode

    async def communicate(self):
        return self.stdout_bytes, self.stderr_bytes


@pytest.fixture
def ytdlp(monkeypatch):
    def use(proc):
        async def fake_exec(*args, **kwargs):
            return proc

        monkeypatch.setattr(url_loader, "get_ytdlp_path", lambda: "yt-dlp")
        monkeypatch.setattr(url_loader.asyncio, "create_subprocess_exec", fake_exec)

    return use


def test_downloads_into_a_drive_root_folder(ytdlp, tmp_path):
    target = str(tmp_path / "clip [abc].mp4")
    ytdlp(FakeYtdlp(stdout=target.encode()))
    result = asyncio.run(url_loader.get_output_filename("https://x", tmp_path.anchor))
    assert result == os.path.realpath(target)


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
