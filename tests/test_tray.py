import pytest

from bridge import settings, tray


@pytest.mark.parametrize("folders, label", [
    ([], "Video folders: none"),
    (["D:\\Videos"], "Video folder: D:\\Videos"),
    (["D:\\A", "E:\\B", "F:\\C"], "Video folders: 3"),
])
def test_folder_label(folders, label):
    assert tray.folder_label(folders) == label


@pytest.fixture
def refreshes(monkeypatch):
    seen = []
    monkeypatch.setattr(tray, "notify_capabilities_changed", lambda: seen.append(True))
    return seen


def test_add_folder_from_the_tray(monkeypatch, tmp_path, refreshes):
    monkeypatch.setattr(tray, "pick_folder", lambda: str(tmp_path))
    assert tray.add_folder_from_tray() is True
    assert settings.get_video_folders() == [str(tmp_path)]
    assert refreshes == [True]


def test_tray_menu_builds_and_announces(monkeypatch):
    pystray = pytest.importorskip("pystray")
    built = {}

    class FakeIcon:
        def __init__(self, name, icon, title, menu):
            built["menu"] = menu
            self.visible = False

        def run(self, setup):
            setup(self)

    ready = []
    monkeypatch.setattr(pystray, "Icon", FakeIcon)
    monkeypatch.setattr(tray, "set_tray_icon", lambda icon: built.setdefault("icon", icon))
    tray.run_tray(port=9876, quit_callback=lambda: None, on_ready=lambda: ready.append(True))

    texts = [item.text for item in built["menu"].items if item is not pystray.Menu.SEPARATOR]
    assert texts[0] == "Open ScriptCompiler"
    assert "Add Video Folder..." in texts
    assert "Open Log Folder" in texts
    assert texts[-1] == "Quit"
    assert built["icon"].visible is True
    assert ready == [True]


def test_cancelled_tray_pick_changes_nothing(monkeypatch, refreshes):
    monkeypatch.setattr(tray, "pick_folder", lambda: None)
    assert tray.add_folder_from_tray() is False
    assert settings.get_video_folders() == []
    assert refreshes == []
