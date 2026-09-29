import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

APP_ID = "scriptcompiler-bridge"


def _config_home():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _data_home():
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def autostart_path():
    return _config_home() / "autostart" / f"{APP_ID}.desktop"


def menu_entry_path():
    return _data_home() / "applications" / f"{APP_ID}.desktop"


def icon_path():
    return _data_home() / "icons" / "hicolor" / "256x256" / "apps" / f"{APP_ID}.png"


def desktop_exec(path):
    escaped = path.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return '"' + escaped.replace("%", "%%") + '"'


def desktop_entry(exe_path, autostart=False):
    command = desktop_exec(exe_path) + (" --autostart" if autostart else "")
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=ScriptCompiler Bridge",
        "Comment=Connects ScriptCompiler to the videos on this computer",
        f"Exec={command}",
        f"Icon={APP_ID}",
        "Terminal=false",
        "Categories=AudioVideo;Video;",
    ]
    if autostart:
        lines.append("X-GNOME-Autostart-enabled=true")
    return "\n".join(lines) + "\n"


def install_menu_entry(appimage, appdir):
    try:
        entry = menu_entry_path()
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(desktop_entry(appimage), encoding="utf-8")
        source = Path(appdir) / f"{APP_ID}.png" if appdir else None
        if source and source.is_file():
            target = icon_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return True
    except OSError as e:
        logger.warning("Could not add the menu entry: %s", e)
        return False
