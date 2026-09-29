import os
import time

import pytest

from bridge import grants, open_files


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(open_files, "_pending", {})
    return tmp_path


def _make(folder, *names):
    for name in names:
        (folder / name).write_text('{"actions": []}', encoding="utf-8")
    return [str(folder / name) for name in names]


def test_a_script_opens_with_its_video(folder):
    script, video, _ = _make(folder, "clip.funscript", "clip.mkv", "clip.txt")
    target = open_files.resolve(script)
    assert target["script"] == script
    assert target["video"] == video


def test_an_axis_file_opens_its_whole_set(folder):
    stroke, roll = _make(folder, "clip.funscript", "clip.roll.funscript")
    assert open_files.resolve(roll)["script"] == stroke


def test_an_axis_file_without_a_main_script_opens_alone(folder):
    (roll,) = _make(folder, "clip.roll.funscript")
    target = open_files.resolve(roll)
    assert target["script"] == roll
    assert target["video"] is None


def test_the_video_must_have_the_same_name(folder):
    script, _ = _make(folder, "clip.funscript", "clip2.mp4")
    assert open_files.resolve(script)["video"] is None


@pytest.mark.parametrize("name, create", [("notes.txt", True), ("gone.funscript", False)])
def test_only_existing_funscripts_can_be_opened(folder, name, create):
    path = folder / name
    if create:
        path.write_text("x")
    with pytest.raises(open_files.OpenError):
        open_files.resolve(str(path))


def test_a_code_can_be_claimed_once(folder):
    script, video = _make(folder, "clip.funscript", "clip.mp4")
    code = open_files.create_code(script)
    result = open_files.claim(code)
    assert result == {
        "script": {"path": script, "name": "clip.funscript", "content": '{"actions": []}'},
        "video": {"path": video, "name": "clip.mp4"},
    }
    with pytest.raises(open_files.OpenError, match="expired"):
        open_files.claim(code)


def test_a_code_expires(folder, monkeypatch):
    (script,) = _make(folder, "clip.funscript")
    code = open_files.create_code(script)
    later = time.time() + open_files.CODE_TTL + 1
    monkeypatch.setattr(open_files.time, "time", lambda: later)
    with pytest.raises(open_files.OpenError, match="expired"):
        open_files.claim(code)


def test_claiming_grants_the_set_and_nothing_before(folder):
    script, video = _make(folder, "clip.funscript", "clip.mp4")
    twist = os.path.join(str(folder), "clip.twist.funscript")
    code = open_files.create_code(script)
    assert not grants.can_read(script)
    open_files.claim(code)
    assert grants.can_read(script) and grants.can_write(script)
    assert grants.can_write(twist)
    assert grants.can_read(video) and not grants.can_write(video)
    assert not grants.can_read(os.path.join(str(folder), "other.funscript"))


def test_open_in_editor_sends_a_code_the_editor_can_claim(folder, monkeypatch):
    (script,) = _make(folder, "clip.funscript")
    opened = []
    monkeypatch.setattr(open_files, "open_url", opened.append)
    monkeypatch.delenv("SC_EDITOR_URL", raising=False)
    open_files.open_in_editor(script)
    assert opened[0].startswith("https://scriptcompiler.com/?bridge=open&code=")
    code = opened[0].split("code=", 1)[1]
    assert open_files.claim(code)["script"]["path"] == script


EDITOR = {"Origin": "https://scriptcompiler.com"}


def test_a_local_program_can_open_a_file(client, folder, monkeypatch):
    (script,) = _make(folder, "clip.funscript")
    opened = []
    monkeypatch.setattr(open_files, "open_url", opened.append)
    response = client.post("/open", json={"path": script})
    assert response.json() == {"success": True}
    assert "bridge=open&code=" in opened[0]


def test_a_web_page_cannot_open_a_file(client, folder, monkeypatch):
    (script,) = _make(folder, "clip.funscript")
    opened = []
    monkeypatch.setattr(open_files, "open_url", opened.append)
    response = client.post("/open", json={"path": script}, headers=EDITOR)
    assert response.status_code == 403
    assert opened == []


def test_opening_a_wrong_file_says_why(client, folder):
    (notes,) = _make(folder, "notes.txt")
    response = client.post("/open", json={"path": notes})
    assert response.status_code == 400
    assert "funscript" in response.json()["error"]


def test_the_editor_claims_the_file_once(client, folder):
    (script,) = _make(folder, "clip.funscript")
    code = open_files.create_code(script)
    first = client.post("/open/claim", json={"code": code}, headers=EDITOR)
    assert first.json()["script"]["path"] == script
    second = client.post("/open/claim", json={"code": code}, headers=EDITOR)
    assert second.status_code == 404
    assert "expired" in second.json()["error"]
