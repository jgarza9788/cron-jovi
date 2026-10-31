"""The status bar from the design doc, as a CLI report."""

import os
import shutil
import subprocess

from . import daemon, hotkeys, schedule, settings
from .action_api import load_actions


def compositor() -> str:
    session = "Wayland" if os.environ.get("WAYLAND_DISPLAY") else "no Wayland session"
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or "unknown desktop"
    return f"{session} · {desktop}"


def tool_report() -> list[tuple[str, bool, str]]:
    """(tool or tools, installed, actions that need it)."""
    needs: dict[tuple, list[str]] = {}
    for name, defn in sorted(load_actions().items()):
        for tool in defn.tools:
            key = tool if isinstance(tool, tuple) else (tool,)
            needs.setdefault(key, []).append(name)
    report = []
    for tools, actions in needs.items():
        found = [tool for tool in tools if shutil.which(tool)]
        label = found[0] if found else " or ".join(tools)
        report.append((label, bool(found), ", ".join(actions)))
    return report


def timers_active() -> int:
    timers = [path.name for path in schedule.installed_timers()]
    if not timers:
        return 0
    proc = subprocess.run(
        ["systemctl", "--user", "is-active", *timers], capture_output=True, text=True
    )
    return proc.stdout.split().count("active")


def report() -> list[str]:
    lines = [compositor(), ""]
    if settings.load()["paused"]:
        lines[1:1] = ["PAUSED: no trigger will run. `cronjovi resume` turns them back on.", ""]
    for tool, found, actions in tool_report():
        lines.append(f"{'ok' if found else 'missing':<8}{tool:<20}{actions}")
    lines.append("")
    total = len(schedule.installed_timers())
    lines.append(f"Timers: {timers_active()} of {total} active")
    lines.append(f"Engine: {daemon.engine_state()}")
    for adapter in hotkeys.active():
        state = "linked" if adapter.linked() else "not linked"
        lines.append(f"Hotkeys: {adapter.name} {state} ({adapter.config})")
    return lines
