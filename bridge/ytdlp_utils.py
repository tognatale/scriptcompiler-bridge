import logging
import os
import shutil
import subprocess
import sys
import threading
import time

from . import settings

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 24 * 60 * 60
_refresh_lock = threading.Lock()


def _binary_name():
    return 'yt-dlp.exe' if sys.platform == 'win32' else 'yt-dlp'


def _bundle_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _hidden():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}


def bundled_ytdlp_path():
    path = os.path.join(_bundle_dir(), 'yt-dlp', _binary_name())
    return path if os.path.isfile(path) else None


def user_ytdlp_path():
    return settings.get_settings_path().parent / "bin" / _binary_name()


def _stamp_path():
    return user_ytdlp_path().parent / "yt-dlp.checked"


def get_ytdlp_path():
    user = user_ytdlp_path()
    if user.is_file():
        return str(user)
    return bundled_ytdlp_path() or shutil.which('yt-dlp')


def _version(path):
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60, **_hidden())
    except (OSError, subprocess.SubprocessError):
        return None
    version = result.stdout.strip()
    return version if result.returncode == 0 and version else None


def _version_key(version):
    return tuple(int(part) if part.isdigit() else 0 for part in version.split("."))


def _install_copy(source, target):
    staged = target.with_name(target.name + ".new")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, staged)
    os.chmod(staged, 0o755)
    os.replace(staged, target)


def refresh_ytdlp():
    with _refresh_lock:
        bundled = bundled_ytdlp_path()
        if not bundled:
            return
        user = user_ytdlp_path()
        user_version = _version(str(user)) if user.is_file() else None
        bundled_version = _version(bundled)
        if user_version is None or (bundled_version and _version_key(bundled_version) > _version_key(user_version)):
            try:
                _install_copy(bundled, user)
            except OSError as e:
                logger.warning("Could not copy yt-dlp: %s", e)
                return
        try:
            result = subprocess.run([str(user), "-U"], capture_output=True, text=True, timeout=300, **_hidden())
            lines = (result.stdout or result.stderr or "").strip().splitlines()
            logger.info("yt-dlp update: %s", lines[-1] if lines else result.returncode)
            updated = result.returncode == 0
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning("yt-dlp update failed: %s", e)
            updated = False
        if _version(str(user)) is None:
            logger.warning("The updated yt-dlp does not run, using the bundled one")
            user.unlink(missing_ok=True)
            return
        if updated:
            _stamp_path().write_text(str(time.time()))


def refresh_if_due():
    try:
        last = float(_stamp_path().read_text())
    except (OSError, ValueError):
        last = 0.0
    if time.time() - last < CHECK_INTERVAL:
        return False
    refresh_ytdlp()
    return True


def _update_loop():
    while True:
        try:
            refresh_if_due()
        except Exception as e:
            logger.warning("yt-dlp update check failed: %s", e)
        time.sleep(60 * 60)


def start_ytdlp_updates():
    threading.Thread(target=_update_loop, name="ytdlp-updates", daemon=True).start()
