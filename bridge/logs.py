import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import SETTINGS_DIR_NAME

LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


def log_dir():
    return Path.home() / SETTINGS_DIR_NAME / "logs"


def setup_logging(directory=None):
    directory = Path(directory) if directory else log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "bridge.log"

    file_handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    return path
