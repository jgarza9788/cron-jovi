"""The app follows the active Omarchy theme, and looks like the mockups elsewhere."""

import tomllib
from pathlib import Path

from .. import settings

DEFAULT = {
    "mode": "dark",
    "accent": "#f5a623",
    "selection": "#2a2f3a",
    "muted": "#6b7280",
    "background": "#171a21",
    "dark_background": "#12141a",
    "darker_background": "#0d0f14",
    "lighter_background": "#20242d",
    "foreground": "#e6e8ec",
    "dark_foreground": "#9aa1ad",
    "light_foreground": "#f3f4f6",
    "bright_foreground": "#ffffff",
    "red": "#f87171",
    "yellow": "#f5c451",
    "orange": "#fdba74",
    "green": "#a7e0a0",
    "cyan": "#7fd8cc",
    "blue": "#9cc3ff",
    "magenta": "#f5a9c8",
    "purple": "#c8b4fb",
    "gray": "#c4cbd8",
}


def theme_file() -> Path:
    return Path.home() / ".local/state/omarchy/current/theme/colors.toml"


def load() -> dict:
    accent = settings.load()["accent"]
    pick = {"accent": accent} if accent else {}
    path = theme_file()
    try:
        colors = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return {"source": "default", "stamp": f"0-{accent}", "colors": {**DEFAULT, **pick}}
    known = {key: str(value) for key, value in colors.items() if key in DEFAULT}
    return {
        "source": "omarchy",
        "stamp": f"{path.stat().st_mtime}-{accent}",
        "colors": {**DEFAULT, **known, **pick},
    }
