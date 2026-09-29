import json
import logging
import os
import platform as platform_module
import shutil
import subprocess
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import BRIDGE_VERSION, GITHUB_REPO
from .desktop import system_env

logger = logging.getLogger(__name__)

_update_cache = {
    "latest_version": None,
    "download_url": None,
    "release_url": None,
    "checked": False,
}


def _platform():
    return sys.platform


def _parse_version(v):
    """Parse version string like '1.2.3' into tuple (1, 2, 3)."""
    v = v.lstrip("v")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _match_asset(name):
    platform = _platform()
    lower = name.lower()
    if platform == "win32":
        return lower.endswith(".exe") and "setup" in lower
    if platform == "darwin":
        return lower.endswith(".dmg") and "macos" in lower
    if platform.startswith("linux"):
        return lower.endswith(".appimage") and platform_module.machine().lower() in lower
    return False


def check_for_update():
    """Check GitHub Releases for a newer version. Returns update info dict."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag = data.get("tag_name", "")
        latest = tag.lstrip("v")

        if not latest:
            return {"update_available": False}

        current = _parse_version(BRIDGE_VERSION)
        remote = _parse_version(latest)

        if remote <= current:
            _update_cache["checked"] = True
            _update_cache["latest_version"] = None
            _update_cache["download_url"] = None
            _update_cache["release_url"] = None
            return {"update_available": False}

        download_url = None
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if _match_asset(name):
                download_url = asset.get("browser_download_url")
                break

        _update_cache["checked"] = True
        _update_cache["latest_version"] = latest
        _update_cache["download_url"] = download_url
        _update_cache["release_url"] = data.get("html_url")

        return {
            "update_available": True,
            "latest_version": latest,
            "current_version": BRIDGE_VERSION,
            "download_url": download_url,
            "release_url": data.get("html_url"),
        }

    except (URLError, json.JSONDecodeError, KeyError, OSError) as e:
        logger.warning("Update check failed: %s", e)
        return {"update_available": False, "error": str(e)}


def get_cached_update():
    """Return cached update info without making a network request."""
    if not _update_cache["checked"]:
        return None
    if not _update_cache["latest_version"]:
        return {"update_available": False}
    return {
        "update_available": True,
        "latest_version": _update_cache["latest_version"],
        "current_version": BRIDGE_VERSION,
        "download_url": _update_cache["download_url"],
        "release_url": _update_cache["release_url"],
    }


def _download(url, dest):
    with urlopen(Request(url), timeout=120) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f, 1024 * 1024)


def _mac_app_bundle():
    parts = os.path.abspath(sys.executable).split(os.sep)
    for i, part in enumerate(parts):
        if part.endswith(".app") and parts[i + 1:i + 3] == ["Contents", "MacOS"]:
            return os.sep.join(parts[:i + 1])
    return None


def cleanup_old_mac_app():
    app = _mac_app_bundle()
    if app:
        shutil.rmtree(app + ".old", ignore_errors=True)


def _install_mac_update(dmg_path):
    app = _mac_app_bundle()
    if not app or not os.access(os.path.dirname(app), os.W_OK):
        return False
    mount = tempfile.mkdtemp(prefix="scb-update-")
    staged = app + ".new"
    old = app + ".old"
    try:
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-quiet", "-mountpoint", mount, dmg_path], check=True, timeout=120)
        try:
            source = os.path.join(mount, os.path.basename(app))
            if not os.path.isdir(source):
                return False
            shutil.rmtree(staged, ignore_errors=True)
            subprocess.run(["ditto", source, staged], check=True, timeout=600)
        finally:
            subprocess.run(["hdiutil", "detach", "-quiet", mount], timeout=60)
        shutil.rmtree(old, ignore_errors=True)
        os.rename(app, old)
        try:
            os.rename(staged, app)
        except OSError:
            os.rename(old, app)
            raise
        subprocess.Popen(["open", "-n", app, "--args", "--updated"])
        return True
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("Mac update install failed: %s", e)
        return False


def _install_linux_update(url):
    target = os.environ.get("APPIMAGE")
    if not target:
        return {"success": False, "error": "Only the AppImage can update itself. Download the new version from the release page."}
    staged = target + ".new"
    _download(url, staged)
    os.chmod(staged, 0o755)
    os.replace(staged, target)
    env = system_env()
    for key in ("APPIMAGE", "APPDIR", "ARGV0", "OWD"):
        env.pop(key, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([target, "--updated"], env=env, start_new_session=True)
    return {"success": True}


def download_and_run_update(shutdown_callback=None):
    """Download the latest version, install it, then signal shutdown."""
    url = _update_cache.get("download_url")
    if not url:
        return {"success": False, "error": "No download URL available"}

    version = _update_cache.get("latest_version", "unknown")
    platform = _platform()
    tmp_dir = tempfile.gettempdir()

    try:
        logger.info("Downloading update v%s from %s", version, url)

        if platform == "win32":
            installer_path = os.path.join(tmp_dir, f"ScriptCompilerBridge-Setup-{version}.exe")
            _download(url, installer_path)
            logger.info("Installer saved to %s, launching...", installer_path)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            subprocess.Popen(
                [installer_path, "/SILENT", "/RESTARTAPPLICATIONS"],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                startupinfo=startupinfo,
            )
            result = {"success": True}

        elif platform == "darwin":
            dmg_path = os.path.join(tmp_dir, f"ScriptCompilerBridge-{version}-macOS.dmg")
            _download(url, dmg_path)
            if _install_mac_update(dmg_path):
                result = {"success": True}
            else:
                subprocess.Popen(["open", dmg_path])
                result = {"success": True, "manual": True}

        elif platform.startswith("linux"):
            result = _install_linux_update(url)
            if not result["success"]:
                return result

        else:
            return {"success": False, "error": f"Unsupported platform: {platform}"}

        if shutdown_callback:
            shutdown_callback()

        return result

    except Exception as e:
        logger.error("Update download/launch failed: %s", e)
        return {"success": False, "error": str(e)}
