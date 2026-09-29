import argparse
import logging
import os
import sys
import threading

# PyInstaller console=False sets sys.stdout/stderr to None which breaks uvicorn logging
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

import uvicorn

from bridge.config import DEFAULT_PORT, DEFAULT_HOST, BRIDGE_NAME, BRIDGE_VERSION
from bridge.desktop import notify, open_editor, show_error, stop_tray
from bridge.logs import log_dir, setup_logging
from bridge.request_guard import allow_bind_host
from bridge.server import set_shutdown_callback
from bridge.settings import sync_autostart
from bridge.startup import is_first_run, mark_first_run_done, probe_port, startup_actions, wait_for_server

logger = logging.getLogger(__name__)

# Suppress harmless ConnectionResetError from asyncio (browser cancels video range requests on seek)
class _ConnectionResetFilter(logging.Filter):
    def filter(self, record):
        return "ConnectionResetError" not in record.getMessage()

logging.getLogger("asyncio").addFilter(_ConnectionResetFilter())


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=BRIDGE_NAME)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind to (default: {DEFAULT_HOST})")
    parser.add_argument("--no-tray", action="store_true", help="Disable system tray icon")
    parser.add_argument("--autostart", action="store_true", help="Started at login, start quietly")
    parser.add_argument("--updated", action="store_true", help="Started by the installer after an update")
    return parser.parse_args(argv)


def _where():
    return "menu bar" if sys.platform == "darwin" else "system tray"


def announce(actions):
    for action in actions:
        if action == "notify_running":
            notify(BRIDGE_NAME, f"ScriptCompiler Bridge is running. You can find it in the {_where()}.")
        elif action == "notify_updated":
            notify(BRIDGE_NAME, f"ScriptCompiler Bridge was updated to version {BRIDGE_VERSION} and is running.")
        elif action == "open_editor":
            open_editor()
            mark_first_run_done()


def main(argv=None):
    args = parse_args(argv)
    setup_logging()
    allow_bind_host(args.host)

    logger.info("Starting %s v%s on %s:%d", BRIDGE_NAME, BRIDGE_VERSION, args.host, args.port)

    state = probe_port(args.host, args.port)
    if state == "bridge":
        logger.info("The bridge is already running, opening the editor")
        open_editor()
        return 0
    if state == "other":
        show_error(f"Port {args.port} is used by another program. Close that program, then start ScriptCompiler Bridge again.")
        return 1

    actions = startup_actions(args.autostart, args.updated, is_first_run())
    sync_autostart()

    server_config = uvicorn.Config(
        "bridge.server:app",
        host=args.host,
        port=args.port,
        log_level="info",
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(server_config)

    def quit_app():
        logger.info("Quitting")
        server.should_exit = True
        stop_tray()
        watchdog = threading.Timer(5.0, os._exit, args=(0,))
        watchdog.daemon = True
        watchdog.start()

    set_shutdown_callback(quit_app)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    if not wait_for_server(server, server_thread):
        show_error(f"ScriptCompiler Bridge could not start. The log file in {log_dir()} has the details.")
        return 1

    if args.no_tray:
        announce(actions)
    else:
        try:
            from bridge.tray import run_tray
            run_tray(port=args.port, quit_callback=quit_app, on_ready=lambda: announce(actions))
        except KeyboardInterrupt:
            quit_app()
        except Exception as e:
            logger.error("Tray icon failed: %s", e)
            announce(actions)

    try:
        while server_thread.is_alive():
            server_thread.join(0.5)
    except KeyboardInterrupt:
        quit_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
