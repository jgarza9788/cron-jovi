"""Starts the local server and opens the window onto it."""

import fcntl
import logging
import secrets
import threading
import webbrowser

from werkzeug.serving import make_server

from .. import compositor, paths
from .server import create_app


def _single_instance():
    """Two windows would autosave over each other. Holds until the process exits."""
    path = paths.state_dir() / "gui.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def launch(browser: bool = False, no_open: bool = False) -> int:
    lock = _single_instance()
    if lock is None:
        print("Cron Jovi is already open.")
        compositor.focus_app("cronjovi")
        return 0
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    token = secrets.token_urlsafe(32)
    holder: dict = {}
    app = create_app(token, holder)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    holder["port"] = server.server_port
    url = f"http://127.0.0.1:{server.server_port}/#token={token}"

    if no_open:
        print(url, flush=True)
        server.serve_forever()
        return 0

    threading.Thread(target=server.serve_forever, daemon=True).start()
    if browser or not _open_window(url):
        if not browser:
            print("No app window available; opening your browser instead.")
        webbrowser.open(url)
        print(f"Cron Jovi is running at {url}\nPress Ctrl+C to quit.")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    server.shutdown()
    return 0


def _open_window(url: str) -> bool:
    try:
        import webview
    except ImportError:
        return False
    try:
        webview.create_window("Cron Jovi", url, width=1280, height=820, min_size=(960, 620))
        storage = paths.state_dir() / "webview"
        storage.mkdir(parents=True, exist_ok=True)
        webview.start(gui="gtk", private_mode=False, storage_path=str(storage))
    except Exception as err:  # pywebview raises bare exceptions for a missing backend
        print(f"Could not open the app window: {err}")
        return False
    return True

