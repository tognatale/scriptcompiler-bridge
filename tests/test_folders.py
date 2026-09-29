import os

import pytest

from bridge import server, settings, video_library


@pytest.fixture
def folders(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    return a, b


@pytest.fixture
def broadcasts(monkeypatch):
    seen = []

    async def fake_broadcast():
        seen.append("capabilities_changed")

    monkeypatch.setattr(server, "broadcast_capabilities_changed", fake_broadcast)
    return seen


def test_add_keeps_one_entry_per_folder(folders):
    a, b = folders
    settings.add_video_folder(str(a))
    settings.add_video_folder(str(b))
    settings.add_video_folder(str(a) + os.sep)
    assert settings.get_video_folders() == [str(a), str(b)]


def test_adding_a_folder_leaves_the_defaults_alone(folders):
    a, _ = folders
    settings.add_video_folder(str(a))
    assert settings.DEFAULT_SETTINGS["video_folders"] == []


def test_remove_takes_one_folder_off_the_list(folders):
    a, b = folders
    settings.add_video_folder(str(a))
    settings.add_video_folder(str(b))
    assert settings.remove_video_folder(str(a)) == [str(b)]
    assert settings.get_video_folders() == [str(b)]


def test_remove_unknown_folder_changes_nothing(folders):
    a, b = folders
    settings.add_video_folder(str(a))
    assert settings.remove_video_folder(str(b)) == [str(a)]


def test_nested_folders_list_each_video_once(tmp_path):
    parent = tmp_path / "videos"
    child = parent / "more"
    child.mkdir(parents=True)
    (child / "clip.mp4").write_bytes(b"x")
    videos = video_library.scan_video_folders([str(parent), str(child)])
    assert [v["filename"] for v in videos] == ["clip.mp4"]


def test_capabilities_include_folders(client):
    assert "folders" in client.get("/capabilities").json()["capabilities"]


def test_pick_adds_the_chosen_folder(client, monkeypatch, folders, broadcasts):
    a, _ = folders
    monkeypatch.setattr(server, "pick_folder", lambda: str(a))
    response = client.post("/folders/pick")
    assert response.status_code == 200
    assert response.json()["folders"] == [str(a)]
    assert settings.get_video_folders() == [str(a)]
    assert broadcasts == ["capabilities_changed"]


def test_pick_cancelled_changes_nothing(client, monkeypatch, broadcasts):
    monkeypatch.setattr(server, "pick_folder", lambda: None)
    response = client.post("/folders/pick")
    assert response.json() == {"cancelled": True, "folders": []}
    assert broadcasts == []


def test_pick_of_a_missing_folder_is_refused(client, monkeypatch, tmp_path, broadcasts):
    monkeypatch.setattr(server, "pick_folder", lambda: str(tmp_path / "gone"))
    assert client.post("/folders/pick").status_code == 400
    assert settings.get_video_folders() == []
    assert broadcasts == []


def test_remove_endpoint_updates_the_list(client, folders, broadcasts):
    a, b = folders
    settings.add_video_folder(str(a))
    settings.add_video_folder(str(b))
    response = client.post("/folders/remove", json={"path": str(a)})
    assert response.json() == {"folders": [str(b)]}
    assert broadcasts == ["capabilities_changed"]


def test_open_logs_opens_the_log_folder(client, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(server, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(server, "open_path", lambda path: opened.append(path))
    assert client.post("/logs/open").json() == {"success": True}
    assert opened == [str(tmp_path)]


def test_shutdown_schedules_the_quit(client, monkeypatch):
    scheduled = []
    monkeypatch.setattr(server, "_shutdown_server", lambda: None)
    monkeypatch.setattr(server, "_schedule_shutdown", lambda: scheduled.append(True))
    assert client.post("/shutdown").json() == {"success": True}
    assert scheduled == [True]


def test_shutdown_without_a_quit_callback_is_refused(client, monkeypatch):
    monkeypatch.setattr(server, "_shutdown_server", None)
    assert client.post("/shutdown").status_code == 503


def test_live_refresh_from_another_thread_without_a_loop_does_nothing(monkeypatch):
    monkeypatch.setattr(server, "_loop", None)
    server.notify_capabilities_changed()
