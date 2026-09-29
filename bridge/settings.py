import copy
import json
import os
import logging
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from .config import SETTINGS_DIR_NAME, SETTINGS_FILE_NAME
from . import linux_desktop

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "video_folders": [],
    "yt_dlp_quality": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "yt_dlp_impersonate": "chrome",
    "autostart": False,
}


def get_settings_path():
    return Path.home() / SETTINGS_DIR_NAME / SETTINGS_FILE_NAME


def load_settings():
    path = get_settings_path()
    if not path.exists():
        return copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    except Exception as e:
        logger.warning("Failed to load settings from %s: %s", path, e)
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings):
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        logger.error("Failed to save settings to %s: %s", path, e)


def get_video_folders():
    return load_settings().get("video_folders", [])


def _same_folder(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def add_video_folder(folder):
    folder = os.path.normpath(folder)
    settings = load_settings()
    folders = list(settings.get("video_folders", []))
    if not any(_same_folder(folder, f) for f in folders):
        folders.append(folder)
        settings["video_folders"] = folders
        save_settings(settings)
    return folders


def remove_video_folder(folder):
    settings = load_settings()
    current = list(settings.get("video_folders", []))
    folders = [f for f in current if not _same_folder(folder, f)]
    if len(folders) != len(current):
        settings["video_folders"] = folders
        save_settings(settings)
    return folders


def set_video_folder(folder):
    folder = os.path.normpath(folder)
    settings = load_settings()
    settings["video_folders"] = [folder]
    save_settings(settings)
    return [folder]


def get_settings():
    settings = load_settings()
    # Always read autostart from OS to stay in sync
    settings["autostart"] = _get_autostart()
    return settings


def update_settings(updates: dict):
    allowed_keys = set(DEFAULT_SETTINGS.keys())
    filtered = {k: v for k, v in updates.items() if k in allowed_keys}

    # Handle autostart toggle separately
    if "autostart" in filtered:
        enabled = bool(filtered["autostart"])
        _set_autostart(enabled)
        filtered["autostart"] = enabled

    settings = load_settings()
    settings.update(filtered)
    save_settings(settings)

    # Sync autostart state from OS (in case it was set externally)
    settings["autostart"] = _get_autostart()
    return settings


def _get_app_executable():
    """Get the path to the bridge executable."""
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return appimage
    if getattr(sys, 'frozen', False):
        return sys.executable
    return None


def _autostart_command(exe_path):
    return f'"{exe_path}" --autostart'


def _macos_plist(exe_path):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.scriptcompiler.bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>{xml_escape(exe_path)}</string>
        <string>--autostart</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""


def sync_autostart():
    if _get_app_executable() and _get_autostart():
        _set_autostart(True)


def _platform():
    return sys.platform


def _get_autostart():
    """Check if autostart is currently enabled in the OS."""
    platform = _platform()
    if platform == 'win32':
        return _get_autostart_windows()
    elif platform == 'darwin':
        return _get_autostart_macos()
    elif platform.startswith('linux'):
        return linux_desktop.autostart_path().exists()
    return False


def _set_autostart(enabled):
    """Enable or disable autostart in the OS."""
    platform = _platform()
    if platform == 'win32':
        _set_autostart_windows(enabled)
    elif platform == 'darwin':
        _set_autostart_macos(enabled)
    elif platform.startswith('linux'):
        _set_autostart_linux(enabled)


def _set_autostart_linux(enabled):
    path = linux_desktop.autostart_path()
    if not enabled:
        path.unlink(missing_ok=True)
        logger.info("Autostart disabled (Linux)")
        return
    exe_path = _get_app_executable()
    if not exe_path:
        logger.warning("Cannot enable autostart: not running as frozen executable")
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(linux_desktop.desktop_entry(exe_path, autostart=True), encoding="utf-8")
        logger.info("Autostart enabled (Linux): %s", path)
    except OSError as e:
        logger.error("Failed to write the autostart entry: %s", e)


def _get_autostart_windows():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        try:
            winreg.QueryValueEx(key, "ScriptCompilerBridge")
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def _set_autostart_windows(enabled):
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        try:
            if enabled:
                exe_path = _get_app_executable()
                if exe_path:
                    winreg.SetValueEx(key, "ScriptCompilerBridge", 0, winreg.REG_SZ, _autostart_command(exe_path))
                    logger.info("Autostart enabled: %s", exe_path)
                else:
                    logger.warning("Cannot enable autostart: not running as frozen executable")
            else:
                try:
                    winreg.DeleteValue(key, "ScriptCompilerBridge")
                    logger.info("Autostart disabled")
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.error("Failed to set autostart: %s", e)


def _get_autostart_macos():
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.scriptcompiler.bridge.plist"
    return plist_path.exists()


def _set_autostart_macos(enabled):
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.scriptcompiler.bridge.plist"
    if enabled:
        exe_path = _get_app_executable()
        if not exe_path:
            logger.warning("Cannot enable autostart: not running as frozen executable")
            return
        try:
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            plist_path.write_text(_macos_plist(exe_path))
            logger.info("Autostart enabled (macOS): %s", plist_path)
        except Exception as e:
            logger.error("Failed to create launch agent: %s", e)
    else:
        try:
            plist_path.unlink(missing_ok=True)
            logger.info("Autostart disabled (macOS)")
        except Exception as e:
            logger.error("Failed to remove launch agent: %s", e)


