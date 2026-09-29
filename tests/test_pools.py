import asyncio
import threading

from bridge import audio_analyzer, file_handler, scene_detector, server, thumbnail_cache, video_stitcher


def _recorder(names, result=None):
    def work(*args, **kwargs):
        names.append(threading.current_thread().name)
        return result
    return work


async def _drain(generator):
    return [item async for item in generator]


def test_file_dialogs_run_on_the_dialog_pool(monkeypatch):
    names = []
    monkeypatch.setattr(file_handler, "_platform", lambda: "linux")
    monkeypatch.setattr(file_handler, "pick_file", _recorder(names))
    asyncio.run(file_handler.open_video_dialog())
    assert names[0].startswith("dialog")


def test_the_folder_picker_runs_on_the_dialog_pool(client, monkeypatch):
    names = []
    monkeypatch.setattr(server, "pick_folder", _recorder(names))
    client.post("/folders/pick")
    assert names[0].startswith("dialog")


def test_scene_detection_runs_on_the_heavy_pool(monkeypatch):
    names = []
    monkeypatch.setattr(scene_detector, "_detect_scenes_sync", _recorder(names, {"success": True}))
    asyncio.run(scene_detector.detect_scenes("clip.mp4"))
    asyncio.run(_drain(scene_detector.detect_scenes_with_progress("clip.mp4")))
    assert [name.split("_")[0] for name in names] == ["heavy", "heavy"]


def test_audio_analysis_runs_on_the_heavy_pool(monkeypatch):
    names = []
    monkeypatch.setattr(audio_analyzer, "_analyze_audio_sync", _recorder(names, {"success": True}))
    asyncio.run(_drain(audio_analyzer.analyze_audio_with_progress("clip.mp4")))
    assert names[0].startswith("heavy")


def test_thumbnail_prep_runs_on_the_heavy_pool(monkeypatch):
    names = []
    monkeypatch.setattr(thumbnail_cache, "pregenerate_frames", _recorder(names, {"success": True}))
    asyncio.run(_drain(thumbnail_cache.pregenerate_with_progress("clip.mp4", [0, 1000])))
    assert names[0].startswith("heavy")


def test_stitching_runs_on_the_heavy_pool(monkeypatch):
    names = []
    monkeypatch.setattr(video_stitcher, "_stitch_videos_sync", _recorder(names, {"success": True}))

    async def stitch():
        return await video_stitcher.start_stitch_background("clip.mp4", [], "out.mp4")

    asyncio.run(stitch())
    assert names[0].startswith("heavy")
