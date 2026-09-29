import pytest

from bridge import grants, settings

EDITOR = {"Origin": "https://scriptcompiler.com"}


@pytest.fixture
def video_folder(tmp_path):
    folder = tmp_path / "videos"
    folder.mkdir()
    settings.set_video_folder(str(folder))
    return folder


def _write(client, path, data="{}"):
    return client.post("/files/write-funscript", json={"data": data, "path": str(path)}, headers=EDITOR)


@pytest.mark.parametrize("name", ["clip.funscript", "clip.twist.funscript", "clip.FUNSCRIPT", "clip.json"])
def test_writes_script_files(client, video_folder, name):
    target = video_folder / name
    response = _write(client, target)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert target.read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("name", ["run.bat", "tool.exe", "clip.funscript.exe", "script.ps1", "noext"])
def test_refuses_other_file_types(client, video_folder, name):
    target = video_folder / name
    response = _write(client, target, data="x")
    assert response.status_code == 400
    assert not target.exists()


def test_refuses_paths_outside_the_video_folder(client, video_folder, tmp_path):
    target = tmp_path / "outside.funscript"
    response = _write(client, target, data="x")
    assert response.status_code == 403
    assert not target.exists()


def test_writes_a_granted_script_outside_the_video_folders(client, video_folder, tmp_path):
    target = tmp_path / "opened.funscript"
    grants.allow_write(str(target))
    response = _write(client, target, data="{}")
    assert response.status_code == 200
    assert target.read_text(encoding="utf-8") == "{}"


def test_writes_a_granted_script_without_any_video_folder(client, tmp_path):
    target = tmp_path / "opened.funscript"
    grants.allow_write(str(target))
    assert _write(client, target, data="{}").status_code == 200
