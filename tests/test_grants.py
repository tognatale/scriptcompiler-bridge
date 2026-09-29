import sys

from bridge import grants


def test_a_read_grant_does_not_allow_writing(tmp_path):
    path = tmp_path / "clip.mp4"
    grants.allow_read(str(path))
    assert grants.can_read(str(path)) is True
    assert grants.can_write(str(path)) is False


def test_a_write_grant_allows_writing(tmp_path):
    path = tmp_path / "clip.funscript"
    grants.allow_write(str(path))
    assert grants.can_write(str(path)) is True


def test_grants_match_the_real_path(tmp_path):
    (tmp_path / "sub").mkdir()
    grants.allow_read(str(tmp_path / "clip.mp4"))
    assert grants.can_read(str(tmp_path / "sub" / ".." / "clip.mp4")) is True
    assert grants.can_read(str(tmp_path / "other.mp4")) is False


def test_grants_ignore_case_only_on_windows(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x")
    grants.allow_read(str(path))
    assert grants.can_read(str(path).upper()) is (sys.platform == "win32")
