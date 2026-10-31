"""Where CronJovi keeps things on disk. Every path honours XDG overrides."""

import os
import sys
from pathlib import Path


def self_command() -> list[str]:
    """How to start this copy. An AppImage's own path changes on every launch, so timers use the file."""
    image = os.environ.get("APPIMAGE")
    return [image] if image else [sys.executable, "-m", "cron_jovi"]


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


def config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def workflows_dir() -> Path:
    return config_home() / "cronjovi" / "workflows"


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state") / "cronjovi"


def history_db() -> Path:
    return state_dir() / "history.db"


def lock_file(slug: str) -> Path:
    return state_dir() / "locks" / f"{slug}.lock"


def progress_file(slug: str) -> Path:
    return state_dir() / "progress" / f"{slug}.json"


def systemd_user_dir() -> Path:
    return config_home() / "systemd" / "user"


def timer_stamp_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "systemd" / "timers"
