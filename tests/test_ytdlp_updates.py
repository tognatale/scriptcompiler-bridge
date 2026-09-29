import os
import time

import pytest

from bridge import ytdlp_utils


class Result:
    def __init__(self, stdout, returncode):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


@pytest.fixture
def fake_ytdlp(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "yt-dlp").mkdir(parents=True)
    bundled = bundle / "yt-dlp" / ytdlp_utils._binary_name()
    bundled.write_text("bundled")
    monkeypatch.setattr(ytdlp_utils, "_bundle_dir", lambda: str(bundle))
    state = {
        "versions": {"bundled": "2026.03.01", "updated": "2026.09.20", "old": "2026.01.01"},
        "update_to": "updated",
        "commands": [],
    }

    def fake_run(args, **kwargs):
        path, flag = args[0], args[1]
        state["commands"].append(flag)
        with open(path) as f:
            content = f.read()
        if flag == "--version":
            version = state["versions"].get(content)
            return Result(f"{version}\n" if version else "", 0 if version else 1)
        with open(path, "w") as f:
            f.write(state["update_to"])
        return Result("Updated yt-dlp\n", 0)

    monkeypatch.setattr(ytdlp_utils.subprocess, "run", fake_run)
    return bundled, state


def _user_copy():
    return ytdlp_utils.user_ytdlp_path()


def test_the_bundled_copy_is_used_until_a_user_copy_exists(fake_ytdlp):
    bundled, _ = fake_ytdlp
    assert ytdlp_utils.get_ytdlp_path() == str(bundled)
    _user_copy().parent.mkdir(parents=True)
    _user_copy().write_text("updated")
    assert ytdlp_utils.get_ytdlp_path() == str(_user_copy())


def test_refresh_copies_and_updates_yt_dlp(fake_ytdlp):
    _, state = fake_ytdlp
    ytdlp_utils.refresh_ytdlp()
    assert _user_copy().read_text() == "updated"
    assert "-U" in state["commands"]
    assert ytdlp_utils.get_ytdlp_path() == str(_user_copy())


def test_a_newer_bundled_copy_replaces_an_older_user_copy(fake_ytdlp):
    _, state = fake_ytdlp
    state["update_to"] = "bundled"
    _user_copy().parent.mkdir(parents=True)
    _user_copy().write_text("old")
    ytdlp_utils.refresh_ytdlp()
    assert _user_copy().read_text() == "bundled"


def test_a_broken_update_falls_back_to_the_bundled_copy(fake_ytdlp):
    bundled, state = fake_ytdlp
    state["update_to"] = "broken"
    ytdlp_utils.refresh_ytdlp()
    assert not _user_copy().exists()
    assert ytdlp_utils.get_ytdlp_path() == str(bundled)


def test_updates_run_once_a_day(fake_ytdlp):
    _, state = fake_ytdlp
    assert ytdlp_utils.refresh_if_due() is True
    assert ytdlp_utils.refresh_if_due() is False
    stamp = _user_copy().parent / "yt-dlp.checked"
    stamp.write_text(str(time.time() - 25 * 60 * 60))
    assert ytdlp_utils.refresh_if_due() is True
    assert state["commands"].count("-U") == 2


def test_without_a_bundled_yt_dlp_nothing_is_copied(monkeypatch, tmp_path):
    monkeypatch.setattr(ytdlp_utils, "_bundle_dir", lambda: str(tmp_path / "empty"))
    monkeypatch.setattr(ytdlp_utils.shutil, "which", lambda name: "/usr/bin/yt-dlp")
    ytdlp_utils.refresh_ytdlp()
    assert not _user_copy().exists()
    assert ytdlp_utils.get_ytdlp_path() == "/usr/bin/yt-dlp"
    assert os.path.basename(str(_user_copy())).startswith("yt-dlp")
