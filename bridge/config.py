from concurrent.futures import ThreadPoolExecutor

BRIDGE_VERSION = "1.2.2"
BRIDGE_NAME = "ScriptCompiler Bridge"
GITHUB_REPO = "telemacy/scriptcompiler-bridge"

DEFAULT_PORT = 9876
DEFAULT_HOST = "127.0.0.1"

EDITOR_URL = "https://scriptcompiler.com"

CORS_ALLOW_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://(.*\.)?scriptcompiler\.com$"

VIDEO_EXTENSIONS = ["mp4", "webm", "mkv", "avi", "mov", "wmv", "flv", "m4v"]
AUDIO_EXTENSIONS = ["mp3", "wav", "ogg", "flac", "aac", "m4a", "wma", "opus"]
FUNSCRIPT_EXTENSIONS = ["funscript", "json"]

TRACKING_COMMAND_TIMEOUT = 5.0
SCENE_DETECT_TIMEOUT = 120.0
AUDIO_ANALYSIS_TIMEOUT = 120.0

SETTINGS_DIR_NAME = ".scriptcompiler-bridge"
SETTINGS_FILE_NAME = "settings.json"

EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="quick")
HEAVY_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="heavy")
DIALOG_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dialog")

