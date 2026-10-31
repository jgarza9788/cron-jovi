"""Galleries: a folder or git repo of shared workflows.

A gallery is other people's commands, so this module only ever reads. Nothing
here runs a workflow, and everything a gallery offers goes through the review
screen and arrives switched off.
"""

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from . import paths, store
from .workflow import WorkflowError, parse

CONFIG = "galleries.yaml"
MAX_FILE_BYTES = 256 * 1024
GIT_URL = re.compile(r"^(https://[\w.-]+/\S+|ssh://[\w@.-]+/\S+|[\w-]+@[\w.-]+:\S+)$")


def _config_path() -> Path:
    return paths.config_home() / "cronjovi" / CONFIG


def sources() -> list[dict]:
    try:
        data = yaml.safe_load(_config_path().read_text())
    except (OSError, yaml.YAMLError):
        return []
    return data if isinstance(data, list) else []


def _write(items: list[dict]) -> None:
    store.write_text(_config_path(), yaml.safe_dump(items, sort_keys=False))


def _id(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()[:12]


def _cache(gallery_id: str) -> Path:
    return paths.state_dir() / "galleries" / gallery_id


def _git(*args: str, cwd: Path | None = None) -> None:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        subprocess.run(
            # Hooks and submodules would let a repo run code on clone or pull.
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=user", *args],
            cwd=cwd, env=env, check=True, capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError:
        raise WorkflowError("git isn't installed") from None
    except subprocess.TimeoutExpired:
        raise WorkflowError("git took too long, check your connection") from None
    except subprocess.CalledProcessError as err:
        detail = (err.stderr or "").strip().splitlines()
        raise WorkflowError(f"git failed: {detail[-1] if detail else err}") from None


def _clone(source: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git("clone", "--depth", "1", "--no-recurse-submodules", "--", source, str(dest))


def add(source: str) -> dict:
    source = source.strip()
    if not source:
        raise WorkflowError("Enter a folder or a git address")
    folder = Path(source).expanduser()
    if folder.is_dir():
        entry = {"id": _id(str(folder.resolve())), "kind": "folder", "source": str(folder.resolve())}
    elif GIT_URL.match(source):
        entry = {"id": _id(source), "kind": "git", "source": source}
    else:
        raise WorkflowError("That isn't a folder here, or an https:// or SSH git address")
    known = sources()
    if any(item["id"] == entry["id"] for item in known):
        raise WorkflowError("That gallery is already added")
    if entry["kind"] == "git":
        _clone(source, _cache(entry["id"]))
    _write([*known, entry])
    return entry


def get(gallery_id: str) -> dict:
    for item in sources():
        if item["id"] == gallery_id:
            return item
    raise WorkflowError("No such gallery")


def remove(gallery_id: str) -> None:
    get(gallery_id)
    _write([item for item in sources() if item["id"] != gallery_id])
    shutil.rmtree(_cache(gallery_id), ignore_errors=True)


def update(gallery_id: str) -> None:
    item = get(gallery_id)
    if item["kind"] != "git":
        return
    cache = _cache(gallery_id)
    if cache.is_dir():
        # The cache is disposable, so a rewritten or force-pushed repo still updates.
        _git("fetch", "--depth", "1", "--no-recurse-submodules", "origin", "HEAD", cwd=cache)
        _git("reset", "--hard", "FETCH_HEAD", cwd=cache)
    else:
        _clone(item["source"], cache)


def _root(item: dict) -> Path:
    return Path(item["source"]) if item["kind"] == "folder" else _cache(item["id"])


def _files(root: Path) -> list[Path]:
    found = []
    for folder in (root, root / "workflows"):
        if folder.is_dir() and not folder.is_symlink():
            found += sorted([*folder.glob("*.yaml"), *folder.glob("*.yml")])
    return found


def _safe_path(root: Path, path: Path) -> bool:
    """A repo could ship a symlink to ~/.ssh/id_rsa named nice.yaml."""
    if path.is_symlink() or not path.is_file():
        return False
    return path.resolve().is_relative_to(root.resolve()) and path.stat().st_size <= MAX_FILE_BYTES


def read_item(gallery_id: str, name: str) -> str:
    root = _root(get(gallery_id))
    for path in _files(root):
        if path.relative_to(root).as_posix() == name and _safe_path(root, path):
            return path.read_text(errors="replace")
    raise WorkflowError(f"No file '{name}' in that gallery")


def items(gallery_id: str) -> list[dict]:
    root = _root(get(gallery_id))
    found = []
    for path in _files(root):
        name = path.relative_to(root).as_posix()
        if not _safe_path(root, path):
            continue
        entry = {"file": name, "name": path.stem, "ok": False}
        try:
            data = yaml.safe_load(path.read_text(errors="replace"))
            workflow = parse(data, path)
            entry.update(
                name=workflow.name, description=workflow.description, ok=True,
                actions=workflow.action_count(),
                trigger=workflow.trigger.describe(), icon=workflow.icon, color=workflow.color,
                runs_commands=bool(store.shell_commands(workflow.steps + workflow.on_failure)),
            )
        except (WorkflowError, yaml.YAMLError) as err:
            entry["error"] = str(err)
        found.append(entry)
    return found


def install(gallery_id: str, name: str) -> str:
    """Add a workflow, switched off. Callers must show it for review first."""
    data = store.parse_shared(read_item(gallery_id, name))
    data["enabled"] = False
    return store.create(data).slug
