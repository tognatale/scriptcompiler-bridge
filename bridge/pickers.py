import logging
import os
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)

PICK_TIMEOUT = 300

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

_MAC_FOLDER_SCRIPT = [
    "tell me to activate",
    'POSIX path of (choose folder with prompt "Select a video folder")',
]


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


def _pick_folder_mac():
    args = ["osascript"]
    for line in _MAC_FOLDER_SCRIPT:
        args += ["-e", line]
    result = _run(args)
    if result.returncode != 0:
        return None
    return _output_path(result.stdout)


def pick_folder():
    platform = _platform()
    try:
        if platform == "win32":
            return _pick_folder_windows()
        if platform == "darwin":
            return _pick_folder_mac()
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("Folder picker failed: %s", e)
        return None
    logger.warning("No folder picker on %s yet", platform)
    return None
