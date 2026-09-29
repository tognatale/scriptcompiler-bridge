import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

NAME = "ScriptCompiler Bridge"


class SmokeFailure(Exception):
    pass


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def check(condition, message):
    if not condition:
        raise SmokeFailure(message)
    print(f"ok: {message}", flush=True)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(port, method, path, body=None, timeout=60):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_until(test, timeout, pause=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = test()
            if result:
                return result
        except Exception:
            pass
        time.sleep(pause)
    return None


def find_ffmpeg(bundle):
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    for path in sorted(Path(bundle).rglob(name)):
        if path.is_file():
            return str(path)
    raise SmokeFailure(f"no {name} in {bundle}")


def make_clip(ffmpeg, folder):
    clip = folder / "clip.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x90:rate=10",
         "-pix_fmt", "yuv420p", str(clip)],
        check=True, timeout=120,
    )
    return clip


def serve(folder):
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run(bundle, command):
    work = Path(tempfile.mkdtemp(prefix="bridge-smoke-"))
    home, media, videos = work / "home", work / "media", work / "videos"
    for folder in (home / ".scriptcompiler-bridge", media, videos):
        folder.mkdir(parents=True)
    (home / ".scriptcompiler-bridge" / "settings.json").write_text(json.dumps({"video_folders": [str(videos)]}))

    ffmpeg = find_ffmpeg(bundle)
    version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=60)
    check(version.returncode == 0 and version.stdout.startswith("ffmpeg version"), f"bundled ffmpeg runs: {ffmpeg}")
    make_clip(ffmpeg, media)
    http = serve(media)
    url = f"http://127.0.0.1:{http.server_address[1]}/clip.mp4"

    port = free_port()
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    log = open(work / "app-output.txt", "w")
    app = subprocess.Popen([*command, "--port", str(port)], env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        health = wait_until(lambda: call(port, "GET", "/health", timeout=2), 180)
        check(health and health.get("name") == NAME, f"the app answers /health: {health}")
        check("folders" in call(port, "GET", "/capabilities")["capabilities"], "the app lists folders")
        info = call(port, "POST", "/videos/fetch-info", {"url": url})
        check(info.get("title") == "clip", f"yt-dlp reads link info: {info.get('title')}")
        started = call(port, "POST", "/videos/load-url", {"url": url})
        check("download_id" in started, "a download starts")
        done = wait_until(lambda: not call(port, "GET", "/videos/active-downloads")["downloads"], 120)
        files = [p for p in videos.iterdir() if p.suffix == ".mp4" and p.stat().st_size > 0]
        check(done and files, f"the download finished: {[p.name for p in files]}")
        check(call(port, "GET", "/update/status").get("state") == "idle", "the update status answers")
        user_copy = home / ".scriptcompiler-bridge" / "bin" / ("yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")
        check(wait_until(user_copy.is_file, 120), "yt-dlp has its own updatable copy")
        call(port, "POST", "/shutdown")
        check(wait_until(lambda: app.poll() is not None, 30), "the app stops")
    except Exception:
        app.kill()
        print("--- app output", (work / "app-output.txt").read_text(errors="replace")[-4000:], sep="\n")
        bridge_log = home / ".scriptcompiler-bridge" / "logs" / "bridge.log"
        if bridge_log.is_file():
            print("--- bridge.log", bridge_log.read_text(errors="replace")[-4000:], sep="\n")
        raise
    finally:
        http.shutdown()
        log.close()
    shutil.rmtree(work, ignore_errors=True)


def main(argv):
    if len(argv) < 4 or argv[0] != "--bundle" or argv[2] != "--":
        print("usage: smoke_test.py --bundle DIR -- COMMAND...")
        return 2
    try:
        run(argv[1], argv[3:])
    except SmokeFailure as e:
        print(f"FAIL: {e}")
        return 1
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
