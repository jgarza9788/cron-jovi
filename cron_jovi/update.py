"""Updates from GitHub releases.

Automatic checks are off until someone turns them on, since asking GitHub tells
it this computer's address. Installing runs code from the internet, so the
address is fixed here, a tag must look exactly like a version and be newer than
this one, and only the repo owner can create those tags.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

from . import __version__, paths, settings

REPO = "jgarza9788/cron-jovi"
RELEASES = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
SOURCE = f"https://github.com/{REPO}/archive/refs/tags/{{tag}}.tar.gz"
TAG = re.compile(r"v(\d{1,6})\.(\d{1,6})\.(\d{1,6})")
CHECK_EVERY = 24 * 3600
INSTALL_TIMEOUT = 600


def _version(tag: str) -> tuple | None:
    match = TAG.fullmatch(str(tag))
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(tag: str, current: str = __version__) -> bool:
    version = _version(tag)
    return bool(version) and version > _version(f"v{current}")


def latest() -> dict | None:
    """The newest published release. Betas count, which GitHub's own "latest" skips."""
    answer = requests.get(RELEASES, timeout=10, headers={"Accept": "application/vnd.github+json"})
    answer.raise_for_status()
    found = [r for r in answer.json() if not r.get("draft") and _version(r.get("tag_name"))]
    if not found:
        return None
    newest = max(found, key=lambda r: _version(r["tag_name"]))
    return {"tag": newest["tag_name"], "name": str(newest.get("name") or newest["tag_name"]),
            "url": f"https://github.com/{REPO}/releases/tag/{newest['tag_name']}"}


def _cache_path() -> Path:
    return paths.state_dir() / "update-check.json"


def check(force: bool = False) -> dict | None:
    """A newer release, if any. Without force this needs the setting, and asks once a day."""
    if not force and not settings.load()["update_check"]:
        return None
    path = _cache_path()
    try:
        cached = json.loads(path.read_text())
    except (OSError, ValueError):
        cached = {}
    if force or time.time() - cached.get("at", 0) > CHECK_EVERY:
        cached = {"at": time.time(), "release": latest()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cached))
    release = cached.get("release")
    return release if release and is_newer(release.get("tag")) else None


def blocked() -> str:
    """Why this copy can't update itself, or nothing if it can."""
    if os.environ.get("APPIMAGE"):
        return f"Download the new AppImage from github.com/{REPO}/releases."
    if sys.prefix == sys.base_prefix:
        return "This copy came from a package. Update it the same way you installed it."
    if "site-packages" not in Path(__file__).parts:
        return "This copy runs from source. Use git to update it."
    return ""


def _status_path() -> Path:
    return paths.state_dir() / "update.json"


def _write_status(state: str, tag: str, message: str = "") -> None:
    path = _status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"state": state, "tag": tag, "message": message, "pid": os.getpid()}))


def status() -> dict:
    try:
        found = json.loads(_status_path().read_text())
    except (OSError, ValueError):
        return {"state": "idle"}
    if found.get("state") == "installing":
        try:
            os.kill(found.get("pid", 0), 0)
        except OSError:
            return {**found, "state": "failed", "message": "The update stopped before it finished."}
    return found


def clear_status() -> None:
    _status_path().unlink(missing_ok=True)


def _installed_version() -> str:
    # A fresh process, from a neutral folder, so this sees what's on disk now.
    done = subprocess.run([sys.executable, "-c", "import cron_jovi; print(cron_jovi.__version__)"],
                          cwd="/", capture_output=True, text=True, timeout=30)
    return done.stdout.strip()


def install(tag: str) -> bool:
    """Replace this copy with `tag`. pip keeps the old version if it fails."""
    if not is_newer(tag):
        _write_status("failed", tag, f"{tag} isn't newer than this version.")
        return False
    reason = blocked()
    if reason:
        _write_status("failed", tag, reason)
        return False
    _write_status("installing", tag)
    try:
        done = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
             "--upgrade", SOURCE.format(tag=tag)],
            capture_output=True, text=True, timeout=INSTALL_TIMEOUT)
    except subprocess.TimeoutExpired:
        _write_status("failed", tag, "The download took too long. Nothing was changed.")
        return False
    if done.returncode:
        detail = (done.stderr or "").strip().splitlines()
        _write_status("failed", tag, f"The update failed: {detail[-1] if detail else 'pip stopped'}")
        return False
    if f"v{_installed_version()}" != tag:
        _write_status("failed", tag, "The update finished, but the new version didn't appear.")
        return False
    # The new code decides what its triggers need, and anything running must pick it up.
    subprocess.run([sys.executable, "-m", "cron_jovi", "sync"], capture_output=True)
    subprocess.run(["systemctl", "--user", "try-restart", "cronjovi-engine.service"], capture_output=True)
    _write_status("done", tag)
    return True
