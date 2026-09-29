import asyncio
import os
import logging
import sys

from .config import VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, FUNSCRIPT_EXTENSIONS, EXECUTOR
from .pickers import PickerUnavailable, pick_file, pick_save_file

logger = logging.getLogger(__name__)

# Paths returned by file dialogs are added here so /files/stream can serve them
_dialog_allowed_paths = set()


def _platform():
    return sys.platform


def is_dialog_allowed_path(path):
    """Check if a path was returned by a file dialog."""
    real = os.path.realpath(path)
    return real in _dialog_allowed_paths


def _tk_open_file(title, filetypes):
    """Open a native file dialog using tkinter (must run in a thread)."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()

    path = filedialog.askopenfilename(title=title, filetypes=filetypes)

    root.destroy()
    return path if path else None


def _tk_save_file(title, filetypes, default_name):
    """Open a native save dialog using tkinter (must run in a thread)."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()

    path = filedialog.asksaveasfilename(
        title=title,
        filetypes=filetypes,
        defaultextension=filetypes[0][1] if filetypes else ".funscript",
        initialfile=default_name,
    )

    root.destroy()
    return path if path else None


def _open_file(title, filetypes, extensions, label):
    if _platform() == "win32":
        return _tk_open_file(title, filetypes)
    return pick_file(title, extensions, label)


def _save_file(title, filetypes, default_name, extensions, label):
    if _platform() == "win32":
        return _tk_save_file(title, filetypes, default_name)
    return pick_save_file(title, default_name, extensions, label)


async def _run_dialog(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(EXECUTOR, func, *args)


async def open_video_dialog():
    """Open a native file dialog for video files."""
    ext_pattern = " ".join(f"*.{ext}" for ext in VIDEO_EXTENSIONS)
    filetypes = [("Video Files", ext_pattern), ("All Files", "*.*")]

    try:
        path = await _run_dialog(_open_file, "Open Video", filetypes, VIDEO_EXTENSIONS, "Video files")
    except PickerUnavailable as e:
        return {"error": str(e)}

    if not path:
        return None

    _dialog_allowed_paths.add(os.path.realpath(path))
    return {
        "path": path,
        "name": os.path.basename(path),
    }


async def open_audio_dialog():
    """Open a native file dialog for audio files."""
    audio_pattern = " ".join(f"*.{ext}" for ext in AUDIO_EXTENSIONS)
    video_pattern = " ".join(f"*.{ext}" for ext in VIDEO_EXTENSIONS)
    all_pattern = audio_pattern + " " + video_pattern
    filetypes = [
        ("Audio & Video Files", all_pattern),
        ("Audio Files", audio_pattern),
        ("Video Files", video_pattern),
        ("All Files", "*.*"),
    ]

    try:
        path = await _run_dialog(
            _open_file, "Open Audio", filetypes, AUDIO_EXTENSIONS + VIDEO_EXTENSIONS, "Audio and video files"
        )
    except PickerUnavailable as e:
        return {"error": str(e)}

    if not path:
        return None

    _dialog_allowed_paths.add(os.path.realpath(path))
    return {
        "path": path,
        "name": os.path.basename(path),
    }


async def open_funscript_dialog():
    """Open a native file dialog for funscript/JSON files."""
    ext_pattern = " ".join(f"*.{ext}" for ext in FUNSCRIPT_EXTENSIONS)
    filetypes = [("Funscript Files", ext_pattern), ("All Files", "*.*")]

    try:
        path = await _run_dialog(_open_file, "Open Funscript", filetypes, FUNSCRIPT_EXTENSIONS, "Funscript files")
    except PickerUnavailable as e:
        return {"error": str(e)}

    if not path:
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error("Failed to read funscript file: %s", e)
        return {"path": path, "name": os.path.basename(path), "error": str(e)}

    return {
        "path": path,
        "name": os.path.basename(path),
        "content": content,
    }


async def save_funscript_dialog(data, default_name="script.funscript"):
    """Save funscript data via native save dialog."""
    filetypes = [("Funscript Files", "*.funscript"), ("JSON Files", "*.json"), ("All Files", "*.*")]

    try:
        path = await _run_dialog(
            _save_file, "Save Funscript", filetypes, default_name, FUNSCRIPT_EXTENSIONS, "Funscript files"
        )
    except PickerUnavailable as e:
        return {"error": str(e)}

    if not path:
        return None

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
    except Exception as e:
        logger.error("Failed to save funscript file: %s", e)
        return {"path": path, "name": os.path.basename(path), "error": str(e)}

    return {
        "path": path,
        "name": os.path.basename(path),
    }


async def write_funscript(data, path):
    """Write funscript data directly to a given path (no dialog)."""
    try:
        dir_part = os.path.dirname(path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
    except Exception as e:
        logger.error("Failed to write funscript file: %s", e)
        return {"success": False, "path": path, "error": str(e)}

    return {
        "success": True,
        "path": path,
        "name": os.path.basename(path),
    }
