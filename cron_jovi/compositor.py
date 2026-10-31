"""Per-compositor window control. There is no portable Wayland API for this."""

import os
import shutil
import subprocess

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
        done = _run(["niri", "msg", "action", "focus-workspace", str(number)])
        if done.returncode:
            raise ActionError(done.stderr.strip() or "niri failed", done.returncode)
    else:
        raise ActionError("switching workspaces needs Hyprland or niri", 127)


def focus_app(window_class: str) -> None:
    """Best effort: used to bring an already-open window forward."""
    if detect() == "hyprland" and shutil.which("hyprctl"):
        try:
            _hyprland(f'hl.dsp.focus({{ window = "class:{window_class}" }})',
                      ["focuswindow", f"class:{window_class}"])
        except ActionError:
            pass
