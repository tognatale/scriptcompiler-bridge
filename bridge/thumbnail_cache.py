import os
import json
import hashlib
import threading
import logging
import time as _time
from pathlib import Path

from .config import SETTINGS_DIR_NAME, HEAVY_EXECUTOR

logger = logging.getLogger(__name__)

THUMB_CACHE_DIR_NAME = "thumb-cache"
JPEG_QUALITY = 85
THUMB_MAX_WIDTH = 320
MAX_CACHE_SIZE_BYTES = 2 * 1024 * 1024 * 1024

_cancel_event = threading.Event()


def cancel_pregeneration():
    _cancel_event.set()


def _get_cache_base_dir():
    d = Path.home() / SETTINGS_DIR_NAME / THUMB_CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def compute_video_hash(video_path):
    real = os.path.realpath(video_path)
    try:
        stat = os.stat(real)
    except OSError:
        return None
    key = f"{real}:{stat.st_size}:{stat.st_mtime}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def get_video_cache_dir(video_path):
    h = compute_video_hash(video_path)
    if h is None:
        return None
    d = _get_cache_base_dir() / h
    d.mkdir(parents=True, exist_ok=True)
    return d


def _metadata_path(cache_dir):
    return cache_dir / "metadata.json"


def load_metadata(cache_dir):
    mp = _metadata_path(cache_dir)
    if mp.is_file():
        try:
            with open(mp, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_metadata(cache_dir, metadata):
    mp = _metadata_path(cache_dir)
    try:
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(metadata, f)
    except OSError as e:
        logger.warning("Failed to save metadata: %s", e)


def _frame_path(cache_dir, time_ms):
    return cache_dir / f"{int(time_ms)}.jpg"


def get_cached_frame(video_path, time_ms):
    cache_dir = get_video_cache_dir(video_path)
    if cache_dir is None:
        return None
    fp = _frame_path(cache_dir, time_ms)
    if fp.is_file():
        try:
            return fp.read_bytes()
        except OSError:
            pass
    return None


def get_cached_frames_batch(video_path, times_ms):
    cache_dir = get_video_cache_dir(video_path)
    if cache_dir is None:
        return {}

    results = {}
    for t in times_ms:
        fp = _frame_path(cache_dir, t)
        if fp.is_file():
            try:
                results[t] = fp.read_bytes()
            except OSError:
                pass

    if results:
        meta = load_metadata(cache_dir)
        meta["last_accessed"] = _time.time()
        save_metadata(cache_dir, meta)

    return results


def save_frames_batch(video_path, frames):
    cache_dir = get_video_cache_dir(video_path)
    if cache_dir is None:
        return

    for t, data in frames.items():
        fp = _frame_path(cache_dir, t)
        try:
            fp.write_bytes(data)
        except OSError as e:
            logger.warning("Failed to write frame %s: %s", t, e)

    meta = load_metadata(cache_dir)
    existing = set(meta.get("cached_times", []))
    existing.update(int(t) for t in frames.keys())
    meta["cached_times"] = sorted(existing)
    meta["video_path"] = os.path.realpath(video_path)
    meta["last_accessed"] = _time.time()
    if "created_at" not in meta:
        meta["created_at"] = _time.time()
    try:
        stat = os.stat(video_path)
        meta["file_size"] = stat.st_size
        meta["mtime"] = stat.st_mtime
    except OSError:
        pass
    save_metadata(cache_dir, meta)


def pregenerate_frames(video_path, times_ms, progress_state, cancel_event):
    from .video_library import _frame_capture

    cache_dir = get_video_cache_dir(video_path)
    if cache_dir is None:
        progress_state["done"] = True
        return {"success": False, "error": "Cannot create cache directory"}

    cancel_event.clear()

    uncached = []
    for t in sorted(times_ms):
        fp = _frame_path(cache_dir, t)
        if not fp.is_file():
            uncached.append(t)

    total = len(times_ms)
    already_cached = total - len(uncached)
    progress_state["total"] = total
    progress_state["cached"] = already_cached

    if not uncached:
        progress_state["done"] = True
        meta = load_metadata(cache_dir)
        meta["last_accessed"] = _time.time()
        save_metadata(cache_dir, meta)
        return {"success": True, "cached": total, "total": total}

    BATCH_SIZE = 50
    cached_count = already_cached

    try:
        for i in range(0, len(uncached), BATCH_SIZE):
            if cancel_event.is_set():
                logger.info("Thumbnail pregeneration cancelled at %d/%d", cached_count, total)
                progress_state["done"] = True
                return {"success": False, "cancelled": True, "cached": cached_count, "total": total}

            batch = uncached[i:i + BATCH_SIZE]

            frames = _frame_capture.extract_frames_batch(video_path, batch)

            if not frames:
                continue

            for t, data in frames.items():
                fp = _frame_path(cache_dir, t)
                try:
                    fp.write_bytes(data)
                except OSError as e:
                    logger.warning("Failed to write frame %s: %s", t, e)

            cached_count += len(frames)
            progress_state["cached"] = cached_count

        meta = load_metadata(cache_dir)
        existing = set(meta.get("cached_times", []))
        existing.update(int(t) for t in times_ms)
        meta["cached_times"] = sorted(existing)
        meta["video_path"] = os.path.realpath(video_path)
        meta["last_accessed"] = _time.time()
        if "created_at" not in meta:
            meta["created_at"] = _time.time()
        try:
            stat = os.stat(video_path)
            meta["file_size"] = stat.st_size
            meta["mtime"] = stat.st_mtime
        except OSError:
            pass
        save_metadata(cache_dir, meta)

        progress_state["done"] = True
        return {"success": True, "cached": cached_count, "total": total}

    except Exception as e:
        logger.error("Thumbnail pregeneration failed: %s", e)
        progress_state["done"] = True
        return {"success": False, "error": str(e), "cached": cached_count, "total": total}


async def pregenerate_with_progress(video_path, times_ms):
    import asyncio

    if not video_path:
        yield {"type": "result", "success": False, "error": "No video path provided"}
        return

    if not times_ms:
        yield {"type": "result", "success": True, "cached": 0, "total": 0}
        return

    loop = asyncio.get_event_loop()

    progress_state = {"cached": 0, "total": len(times_ms), "done": False}

    future = loop.run_in_executor(
        HEAVY_EXECUTOR, pregenerate_frames, video_path, times_ms, progress_state, _cancel_event
    )

    last_percent = -1

    while not future.done():
        await asyncio.sleep(0.3)

        total = progress_state.get("total", 0)
        cached = progress_state.get("cached", 0)

        if total > 0 and not progress_state.get("done"):
            percent = min(round((cached / total) * 100), 99)
            if percent != last_percent:
                last_percent = percent
                yield {
                    "type": "progress",
                    "percent": percent,
                    "cached": cached,
                    "total": total,
                }

    result = await future
    result["type"] = "result"
    yield result


def cleanup_old_caches(max_size_bytes=MAX_CACHE_SIZE_BYTES):
    base = _get_cache_base_dir()
    if not base.is_dir():
        return

    entries = []
    total_size = 0

    for d in base.iterdir():
        if not d.is_dir():
            continue
        meta = load_metadata(d)
        last_accessed = meta.get("last_accessed", 0)

        dir_size = 0
        for f in d.iterdir():
            if f.is_file():
                try:
                    dir_size += f.stat().st_size
                except OSError:
                    pass

        entries.append({"dir": d, "last_accessed": last_accessed, "size": dir_size})
        total_size += dir_size

    if total_size <= max_size_bytes:
        return

    entries.sort(key=lambda e: e["last_accessed"])

    for entry in entries:
        if total_size <= max_size_bytes:
            break
        d = entry["dir"]
        logger.info("Evicting thumbnail cache: %s (%.1fMB)", d.name, entry["size"] / 1024 / 1024)
        try:
            for f in d.iterdir():
                f.unlink(missing_ok=True)
            d.rmdir()
        except OSError as e:
            logger.warning("Failed to remove cache dir %s: %s", d, e)
        total_size -= entry["size"]
