"""App-wide preferences. Everything else lives in the workflow files."""

import re

import yaml

from . import paths

DEFAULTS = {"paused": False, "accent": ""}
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def _path():
    return paths.config_home() / "cronjovi" / "settings.yaml"


def load() -> dict:
    try:
        saved = yaml.safe_load(_path().read_text())
    except (OSError, yaml.YAMLError):
        saved = None
    merged = {**DEFAULTS, **{k: v for k, v in (saved or {}).items() if k in DEFAULTS}}
    merged["paused"] = bool(merged["paused"])
    if not HEX_COLOR.fullmatch(str(merged["accent"])):
        merged["accent"] = ""
    return merged


def update(**changes) -> dict:
    merged = {**load(), **{k: v for k, v in changes.items() if k in DEFAULTS}}
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(merged))
    return load()
