import logging
import os
import shutil
import subprocess
import sys
import webbrowser

from .config import BRIDGE_NAME, EDITOR_URL

logger = logging.getLogger(__name__)

_tray_icon = None


def _platform():
    return sys.platform


def _is_linux():
    return _platform().startswith("linux")


def _has(program):
    return shutil.which(program) is not None


def system_env():
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = original
    return env


def set_tray_icon(icon):
    global _tray_icon
    _tray_icon = icon


def stop_tray():
    if _tray_icon is not None:
        _tray_icon.stop()


def editor_url():
    base = os.environ.get("SC_EDITOR_URL") or EDITOR_URL
    return base.rstrip("/") + "/?bridge=connect"


def open_url(url):
    if _is_linux():
        try:
            subprocess.Popen(["xdg-open", url], env=system_env())
        except OSError as e:
            logger.warning("Could not open %s: %s", url, e)
    else:
        webbrowser.open(url)


def open_editor():
    open_url(editor_url())


def _applescript_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _osascript(script):
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("osascript failed: %s", e)


def _run_quiet(args):
    try:
        subprocess.run(args, capture_output=True, timeout=120, env=system_env())
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("%s failed: %s", args[0], e)


def notify(title, message):
    logger.info("%s: %s", title, message)
    platform = _platform()
    if platform == "darwin":
        _osascript(f"display notification {_applescript_string(message)} with title {_applescript_string(title)}")
    elif _is_linux():
        if _has("notify-send"):
            _run_quiet(["notify-send", "-a", BRIDGE_NAME, "-i", "scriptcompiler-bridge", title, message])
    elif _tray_icon is not None:
        try:
            _tray_icon.notify(message, title)
        except Exception as e:
            logger.warning("Tray notification failed: %s", e)


def _message_box(text, title):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 | 0x40000)


def show_error(message):
    logger.error(message)
    platform = _platform()
    if platform == "win32":
        _message_box(message, BRIDGE_NAME)
    elif platform == "darwin":
        _osascript(f"display alert {_applescript_string(BRIDGE_NAME)} message {_applescript_string(message)} as critical")
    elif _has("zenity"):
        _run_quiet(["zenity", "--error", "--no-markup", "--title", BRIDGE_NAME, "--text", message])
    elif _has("kdialog"):
        _run_quiet(["kdialog", "--title", BRIDGE_NAME, "--error", message])
    elif _has("notify-send"):
        _run_quiet(["notify-send", "-a", BRIDGE_NAME, "-u", "critical", BRIDGE_NAME, message])


def _startfile(path):
    os.startfile(path)


def open_path(path):
    platform = _platform()
    try:
        if platform == "win32":
            _startfile(path)
        elif platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path], env=system_env())
    except OSError as e:
        logger.warning("Could not open %s: %s", path, e)
