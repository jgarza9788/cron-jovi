"""Per-compositor window control. There is no portable Wayland API for this."""

import json
import os
import shutil
import subprocess
from typing import Any

from .action_api import ActionError


def detect() -> str | None:
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    if os.environ.get("NIRI_SOCKET"):
        return "niri"
    return None


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError:
        raise ActionError(f"{argv[0]} not found", 127) from None


def _hyprland(lua: str, classic: list[str]) -> None:
    """Lua-configured Hyprland refuses the classic syntax, older ones refuse Lua."""
    done = _run(["hyprctl", "dispatch", lua])
    if done.returncode:
        done = _run(["hyprctl", "dispatch", *classic])
    if done.returncode:
        raise ActionError(done.stdout.strip() or done.stderr.strip() or "hyprctl failed",
                          done.returncode)


def focus_workspace(number: int) -> None:
    kind = detect()
    if kind == "hyprland":
        _hyprland(f'hl.dsp.focus({{ workspace = "{number}" }})', ["workspace", str(number)])
    elif kind == "niri":
        _niri("focus-workspace", str(number))
    else:
        raise ActionError("switching workspaces needs Hyprland or niri", 127)


def _json(argv: list[str]) -> Any:
    done = _run(argv)
    if done.returncode:
        raise ActionError(done.stderr.strip() or f"{argv[0]} failed", done.returncode)
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise ActionError(f"{argv[0]} gave an answer Cron Jovi can't read") from None


def _same_app(first: str | None, second: str) -> bool:
    return (first or "").lower() == second.lower()


def _hyprland_select(app: str) -> None:
    """Focus `app`. Dispatchers act on the active window, and the wrong one must never close."""
    found = [c for c in _json(["hyprctl", "clients", "-j"])
             if _same_app(c.get("class"), app) or _same_app(c.get("initialClass"), app)]
    if not found:
        raise ActionError(f"{app} isn't open")
    address = found[0]["address"]
    _hyprland(f'hl.dsp.focus({{ window = "address:{address}" }})', ["focuswindow", f"address:{address}"])
    if _json(["hyprctl", "activewindow", "-j"]).get("address") != address:
        raise ActionError(f"Couldn't bring {app} forward")


def _niri_window(app: str | None) -> int:
    windows = _json(["niri", "msg", "--json", "windows"])
    found = [w for w in windows if (_same_app(w.get("app_id"), app) if app else w.get("is_focused"))]
    if not found:
        raise ActionError(f"{app} isn't open" if app else "No window has focus")
    return found[0]["id"]


def _niri(*args: str) -> None:
    done = _run(["niri", "msg", "action", *args])
    if done.returncode:
        raise ActionError(done.stderr.strip() or "niri failed", done.returncode)


def control_window(op: str, app: str | None = None, workspace: int | None = None) -> None:
    """Focus, close or move `app`, or the focused window if no app is given."""
    kind = detect()
    if kind == "hyprland":
        if app:
            _hyprland_select(app)
        if op == "close":
            _hyprland("hl.dsp.window.close()", ["killactive"])
        elif op == "move":
            _hyprland(f'hl.dsp.window.move({{ workspace = "{workspace}", follow = false }})',
                      ["movetoworkspacesilent", str(workspace)])
    elif kind == "niri":
        window = str(_niri_window(app))
        if op == "focus":
            _niri("focus-window", "--id", window)
        elif op == "close":
            _niri("close-window", "--id", window)
        else:
            _niri("move-window-to-workspace", "--window-id", window, "--focus", "false", str(workspace))
    else:
        raise ActionError("controlling windows needs Hyprland or niri", 127)


def focus_app(window_class: str) -> None:
    """Best effort: used to bring an already-open window forward."""
    if detect() and shutil.which("hyprctl" if detect() == "hyprland" else "niri"):
        try:
            control_window("focus", window_class)
        except ActionError:
            pass
