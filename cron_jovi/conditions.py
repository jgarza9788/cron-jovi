"""Conditions usable under `if:`. Several conditions in one `if:` must all hold."""

import os
import subprocess
from datetime import datetime, time
from pathlib import Path

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
POWER_ROOT = Path("/sys/class/power_supply")


def _clock(text: str) -> time:
    return time.fromisoformat(str(text))


def time_of_day(spec: dict, now: datetime | None = None) -> bool:
    current = (now or datetime.now()).time()
    after = _clock(spec["after"]) if "after" in spec else None
    before = _clock(spec["before"]) if "before" in spec else None
    if after and before and after > before:  # window crosses midnight
        return current >= after or current < before
    return (after is None or current >= after) and (before is None or current < before)


def weekday(spec: list | str, now: datetime | None = None) -> bool:
    days = [spec] if isinstance(spec, str) else spec
    return DAYS[(now or datetime.now()).weekday()] in days


def file_exists(spec: str) -> bool:
    return Path(str(spec)).expanduser().exists()


def command(spec: str | tuple) -> bool:
    text, values = spec if isinstance(spec, tuple) else (str(spec), {})
    return subprocess.run(["bash", "-c", text], capture_output=True,
                          env={**os.environ, **values}).returncode == 0


def equals(spec: list) -> bool:
    left, right = spec
    return str(left) == str(right)


def contains(spec: list) -> bool:
    text, piece = spec
    return str(piece).lower() in str(text).lower()


def on_battery(spec: bool, root: Path = POWER_ROOT) -> bool:
    from .daemon import read_power

    return bool(read_power(root)["discharging"]) == bool(spec)


def app_running(spec: str) -> bool:
    return subprocess.run(["pgrep", "-xi", "--", str(spec)], capture_output=True).returncode == 0


def negate(spec: dict) -> bool:
    return not all(CONDITIONS[name](value) for name, value in spec.items())


CONDITIONS = {
    "time_of_day": time_of_day,
    "weekday": weekday,
    "file_exists": file_exists,
    "command": command,
    "equals": equals,
    "contains": contains,
    "on_battery": on_battery,
    "app_running": app_running,
    "not": negate,
}
