import logging
import os
import shutil
import subprocess
from pathlib import Path

from .desktop import system_env

logger = logging.getLogger(__name__)

APP_ID = "scriptcompiler-bridge"
MIME_TYPE = "application/x-funscript"
MIME_XML = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-funscript">
    <comment>Funscript</comment>
    <sub-class-of type="application/json"/>
    <glob pattern="*.funscript"/>
  </mime-type>
</mime-info>
"""


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


def mime_package_path():
    return _data_home() / "mime" / "packages" / f"{APP_ID}.xml"


def desktop_exec(path):
    escaped = path.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return '"' + escaped.replace("%", "%%") + '"'


def desktop_entry(exe_path, autostart=False):
    command = desktop_exec(exe_path) + (" --autostart" if autostart else " %f")
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
    else:
        lines.append(f"MimeType={MIME_TYPE};")
    return "\n".join(lines) + "\n"


def _write_if_changed(path, text):
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _run(*args):
    if not shutil.which(args[0]):
        return None
    try:
        return subprocess.run(list(args), capture_output=True, text=True, timeout=30, env=system_env())
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("%s failed: %s", args[0], e)
        return None


def _become_default_if_free():
    result = _run("xdg-mime", "query", "default", MIME_TYPE)
    if result is not None and not (result.stdout or "").strip():
        _run("xdg-mime", "default", f"{APP_ID}.desktop", MIME_TYPE)


def install_menu_entry(appimage, appdir):
    try:
        if _write_if_changed(menu_entry_path(), desktop_entry(appimage)):
            _run("update-desktop-database", str(menu_entry_path().parent))
        if _write_if_changed(mime_package_path(), MIME_XML):
            _run("update-mime-database", str(mime_package_path().parent.parent))
        source = Path(appdir) / f"{APP_ID}.png" if appdir else None
        if source and source.is_file():
            target = icon_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        _become_default_if_free()
        return True
    except OSError as e:
        logger.warning("Could not add the menu entry: %s", e)
        return False
