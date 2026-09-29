import logging
import os
import secrets
import threading
import time

from .config import VIDEO_EXTENSIONS
from .desktop import editor_base_url, open_url
from .grants import allow_read, allow_write

logger = logging.getLogger(__name__)

AXIS_SUFFIXES = ("surge", "sway", "twist", "roll", "pitch", "vib")
CODE_TTL = 10 * 60
_EXTENSION = ".funscript"

_pending = {}
_lock = threading.Lock()


class OpenError(Exception):
    pass


def _split(path):
    folder, name = os.path.split(os.path.abspath(path))
    stem = name[:-len(_EXTENSION)]
    parts = stem.rsplit(".", 1)
    if len(parts) == 2 and parts[1].lower() in AXIS_SUFFIXES:
        return folder, parts[0]
    return folder, stem


def _find_video(folder, base):
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return None
    for name in names:
        stem, ext = os.path.splitext(name)
        if stem == base and ext.lstrip(".").lower() in VIDEO_EXTENSIONS:
            return os.path.join(folder, name)
    return None


def resolve(path):
    if not path.lower().endswith(_EXTENSION):
        raise OpenError("Only .funscript files can be opened.")
    if not os.path.isfile(path):
        raise OpenError("The file was not found.")
    folder, base = _split(path)
    script = os.path.join(folder, base + _EXTENSION)
    if not os.path.isfile(script):
        script = os.path.abspath(path)
    return {"script": script, "video": _find_video(folder, base), "folder": folder, "base": base}


def _drop_expired():
    now = time.time()
    for code in [c for c, target in _pending.items() if target["expires"] < now]:
        del _pending[code]


def create_code(path):
    target = resolve(path)
    code = secrets.token_urlsafe(24)
    with _lock:
        _drop_expired()
        _pending[code] = {**target, "expires": time.time() + CODE_TTL}
    return code


def _grant(target):
    folder, base = target["folder"], target["base"]
    scripts = [os.path.join(folder, base + _EXTENSION), target["script"]]
    scripts += [os.path.join(folder, f"{base}.{suffix}{_EXTENSION}") for suffix in AXIS_SUFFIXES]
    allow_read(*scripts)
    allow_write(*scripts)
    if target["video"]:
        allow_read(target["video"])


def claim(code):
    with _lock:
        _drop_expired()
        target = _pending.pop(code, None)
    if target is None:
        raise OpenError("This file link expired. Open the file again.")
    _grant(target)
    with open(target["script"], "r", encoding="utf-8-sig") as f:
        content = f.read()
    video = target["video"]
    return {
        "script": {"path": target["script"], "name": os.path.basename(target["script"]), "content": content},
        "video": {"path": video, "name": os.path.basename(video)} if video else None,
    }


def open_in_editor(path):
    code = create_code(path)
    logger.info("Opening %s in the editor", path)
    open_url(f"{editor_base_url()}/?bridge=open&code={code}")
