import logging
import os
import shutil
import subprocess
import sys
import tempfile

from .desktop import _applescript_string, system_env

logger = logging.getLogger(__name__)

PICK_TIMEOUT = 300
LINUX_PICKER_MISSING = "No file picker found. Install zenity, for example: sudo apt install zenity"

_WINDOWS_FOLDER_SCRIPT = """
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = "Select a video folder"
$d.ShowNewFolderButton = $true
if ($d.ShowDialog($owner) -eq "OK") { Write-Output $d.SelectedPath }
$owner.Dispose()
"""


class PickerUnavailable(Exception):
    pass


def _platform():
    return sys.platform


def _run(args, **kwargs):
    return subprocess.run(args, capture_output=True, timeout=PICK_TIMEOUT, **kwargs)


def _output_path(stdout):
    path = stdout.decode("utf-8", errors="replace").strip()
    return path or None


def _pick_folder_windows():
    script_path = os.path.join(tempfile.gettempdir(), "sc_folder_pick.ps1")
    with open(script_path, "w", encoding="utf-8-sig") as f:
        f.write(_WINDOWS_FOLDER_SCRIPT)
    result = _run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-STA", "-File", script_path],
        creationflags=0x08000000,
    )
    return _output_path(result.stdout)


def _mac_choose(expression):
    result = _run(["osascript", "-e", "tell me to activate", "-e", f"POSIX path of ({expression})"])
    if result.returncode != 0:
        return None
    return _output_path(result.stdout)


def _linux_tool():
    for tool in ("zenity", "kdialog"):
        if shutil.which(tool):
            return tool
    raise PickerUnavailable(LINUX_PICKER_MISSING)


def _linux_run(args):
    result = _run(args, env=system_env())
    if result.returncode != 0:
        return None
    return _output_path(result.stdout)


def _zenity_filters(extensions, label):
    if not extensions:
        return []
    patterns = " ".join(f"*.{ext}" for ext in extensions)
    return [f"--file-filter={label} | {patterns}", "--file-filter=All files | *"]


def _kdialog_filter(extensions, label):
    if not extensions:
        return "*"
    return " ".join(f"*.{ext}" for ext in extensions) + f"|{label}"


def pick_folder():
    platform = _platform()
    try:
        if platform == "win32":
            return _pick_folder_windows()
        if platform == "darwin":
            return _mac_choose('choose folder with prompt "Select a video folder"')
        if platform.startswith("linux"):
            if _linux_tool() == "zenity":
                return _linux_run(["zenity", "--file-selection", "--directory", "--title=Select a video folder"])
            return _linux_run(["kdialog", "--title", "Select a video folder", "--getexistingdirectory", os.path.expanduser("~")])
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("Folder picker failed: %s", e)
        return None
    logger.warning("No folder picker on %s", platform)
    return None


def pick_file(title, extensions=None, label="Supported files"):
    platform = _platform()
    try:
        if platform == "darwin":
            return _mac_choose(f"choose file with prompt {_applescript_string(title)}")
        if platform.startswith("linux"):
            if _linux_tool() == "zenity":
                return _linux_run(["zenity", "--file-selection", f"--title={title}", *_zenity_filters(extensions, label)])
            return _linux_run(["kdialog", "--title", title, "--getopenfilename", os.path.expanduser("~"), _kdialog_filter(extensions, label)])
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("File picker failed: %s", e)
        return None
    logger.warning("No file picker on %s", platform)
    return None


def pick_save_file(title, default_name, extensions=None, label="Supported files"):
    platform = _platform()
    try:
        if platform == "darwin":
            return _mac_choose(
                f"choose file name with prompt {_applescript_string(title)} default name {_applescript_string(default_name)}"
            )
        if platform.startswith("linux"):
            start = os.path.join(os.path.expanduser("~"), default_name)
            if _linux_tool() == "zenity":
                return _linux_run(["zenity", "--file-selection", "--save", f"--title={title}", f"--filename={start}", *_zenity_filters(extensions, label)])
            return _linux_run(["kdialog", "--title", title, "--getsavefilename", start, _kdialog_filter(extensions, label)])
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("Save picker failed: %s", e)
        return None
    logger.warning("No save picker on %s", platform)
    return None
