import logging
import os
import sys

from .config import BRIDGE_VERSION
from .desktop import open_editor, open_path, set_tray_icon
from .logs import log_dir
from .pickers import pick_folder
from .server import notify_capabilities_changed
from .settings import add_video_folder, get_video_folders
from .video_library import invalidate_cache

logger = logging.getLogger(__name__)


def _load_icon_image():
    from PIL import Image

    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(__file__))

    icon_path = os.path.join(base, "favicon.png")
    if os.path.exists(icon_path):
        return Image.open(icon_path)

    return Image.new("RGBA", (64, 64), (46, 125, 246, 255))


def folder_label(folders):
    if not folders:
        return "Video folders: none"
    if len(folders) == 1:
        return f"Video folder: {folders[0]}"
    return f"Video folders: {len(folders)}"


def add_folder_from_tray():
    folder = pick_folder()
    if not folder or not os.path.isdir(folder):
        return False
    add_video_folder(folder)
    invalidate_cache()
    notify_capabilities_changed()
    logger.info("Video folder added from the tray: %s", folder)
    return True


def run_tray(port, quit_callback, on_ready=None):
    import pystray
    from pystray import MenuItem as Item

    def on_add_folder(icon, item):
        if add_folder_from_tray():
            icon.update_menu()

    def on_refresh(icon, item):
        invalidate_cache()
        logger.info("Video library cache cleared, will rescan on next request")

    def on_quit(icon, item):
        logger.info("Quit requested from tray")
        quit_callback()

    menu = pystray.Menu(
        Item("Open ScriptCompiler", lambda icon, item: open_editor(), default=True),
        Item(f"ScriptCompiler Bridge v{BRIDGE_VERSION}", lambda: None, enabled=False),
        Item(f"Port: {port}", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        Item(lambda item: folder_label(get_video_folders()), lambda: None, enabled=False),
        Item("Add Video Folder...", on_add_folder),
        Item("Refresh Library", on_refresh),
        pystray.Menu.SEPARATOR,
        Item("Open Log Folder", lambda icon, item: open_path(str(log_dir()))),
        Item("Quit", on_quit),
    )

    icon = pystray.Icon(
        name="scriptcompiler-bridge",
        icon=_load_icon_image(),
        title=f"ScriptCompiler Bridge (:{port})",
        menu=menu,
    )

    def setup(icon):
        icon.visible = True
        set_tray_icon(icon)
        if on_ready:
            on_ready()

    icon.run(setup=setup)
