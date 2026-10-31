"""Reading and writing workflow files, shared by the CLI and the GUI."""

import hashlib
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import daemon, hotkeys, paths, schedule, settings
from .history import History
from .workflow import Workflow, WorkflowError, discover, parse, slugify

KEY_ORDER = ("name", "description", "enabled", "favorite", "icon", "color", "folder", "trigger", "steps",
             "on_failure")


class _Dumper(yaml.SafeDumper):
    """Writes several-line text as a readable block instead of one escaped line."""


def _text(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _text)


@dataclass
class SyncReport:
    timers: int = 0
    hotkeys: int = 0
    errors: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    messages: list = field(default_factory=list)


def sync(link_config: bool = False) -> SyncReport:
    """Make systemd and the compositor match the workflow files."""
    workflows, errors = discover()
    # Paused means no triggers at all. Time away isn't "missed", so nothing replays on resume.
    live = [] if settings.load()["paused"] else workflows
    history = History()
    problems = schedule.sync_timers(live, history)
    problems += daemon.sync_engine(live)
    messages = hotkeys.sync_hotkeys(live, link_config)
    history.close()
    return SyncReport(
        timers=sum(1 for w in live if w.enabled and w.trigger.schedule),
        hotkeys=sum(1 for w in live if w.enabled and w.trigger.hotkey),
        errors=errors,
        problems=problems,
        messages=messages,
    )


def path_for(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", slug):
        raise WorkflowError(f"bad workflow id '{slug}'")
    folder = paths.workflows_dir()
    for suffix in (".yaml", ".yml"):
        path = folder / f"{slug}{suffix}"
        if path.exists():
            return path
    return folder / f"{slug}.yaml"


def check(data: dict, path: Path) -> Workflow:
    """Validate everything, including what only systemd can judge."""
    workflow = parse(data, path)
    if workflow.trigger.schedule:
        schedule.next_ticks(workflow.trigger.schedule, time.time())
    if workflow.trigger.hotkey:
        hotkeys.parse(workflow.trigger.hotkey)
    return workflow


def dump(data: dict) -> str:
    # description always appears, blank by default, so it's there to fill in by hand.
    ordered = {"name": data.get("name"), "description": data.get("description") or ""}
    ordered.update({key: data[key] for key in KEY_ORDER[2:] if data.get(key) not in (None, "", [], {})})
    if "enabled" in data:
        ordered["enabled"] = bool(data["enabled"])
    ordered["steps"] = data.get("steps") or []
    ordered.update({key: value for key, value in data.items()
                    if key not in KEY_ORDER and key not in ordered})
    return yaml.dump(ordered, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def write_text(path: Path, text: str) -> None:
    """Atomic, so a crash can't leave half a workflow on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    os.replace(temp, path)


def stamp(slug: str) -> str:
    """Identifies a file's content, to notice edits made outside the app."""
    return hashlib.sha256(path_for(slug).read_bytes()).hexdigest()[:16]


def set_enabled(slug: str, enabled: bool) -> None:
    """Edits one line, so a hand-written file keeps its comments."""
    path = path_for(slug)
    text = path.read_text()
    check(yaml.safe_load(text), path)
    line = f"enabled: {str(enabled).lower()}"
    if re.search(r"^enabled:.*$", text, re.M):
        text = re.sub(r"^enabled:.*$", line, text, count=1, flags=re.M)
    else:
        text = re.sub(r"^(name:.*)$", rf"\1\n{line}", text, count=1, flags=re.M)
    write_text(path, text)


SECRET_WORDS = re.compile(r"authorization|bearer\s|api[_-]?key|token|passw(or)?d|secret", re.I)


def secrets_in(value, where: str = "") -> list[str]:
    """Places that look like a password or key, to warn about before sharing."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            label = f"{where} {key}".strip()
            if SECRET_WORDS.search(str(key)) and item:
                found.append(label)
            found += secrets_in(item, label)
    elif isinstance(value, list):
        for item in value:
            found += secrets_in(item, where)
    elif isinstance(value, str) and "{{" not in value and SECRET_WORDS.search(value):
        found.append(where)
    return list(dict.fromkeys(found))


def export(slug: str, folder: Path) -> Path:
    """A clean copy to share: no personal switches, and never a webhook secret."""
    data = {key: value for key, value in read_raw(slug).items()
            if key not in ("enabled", "favorite", "folder")}
    folder.mkdir(parents=True, exist_ok=True)
    target, count = folder / f"{slug}.yaml", 1
    while target.exists():
        count += 1
        target = folder / f"{slug}-{count}.yaml"
    target.write_text(dump(data))
    return target


def parse_shared(text: str) -> dict:
    """A workflow someone else wrote, which can't be assumed to be well formed."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise WorkflowError(f"That file isn't valid YAML: {err}") from None
    if not isinstance(data, dict):
        raise WorkflowError("That file isn't a workflow")
    return data


def read_raw(slug: str) -> dict:
    path = path_for(slug)
    if not path.exists():
        raise WorkflowError(f"no workflow '{slug}'")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as err:
        raise WorkflowError(f"{path.name}: invalid YAML: {err}") from None
    if not isinstance(data, dict):
        raise WorkflowError(f"{path.name}: must be a mapping")
    return data


def save(slug: str, data: dict) -> Workflow:
    path = path_for(slug)
    workflow = check(data, path)
    write_text(path, dump(data))
    return workflow


def save_yaml(slug: str, text: str) -> Workflow:
    """Keep the user's exact text, comments included."""
    path = path_for(slug)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise WorkflowError(f"invalid YAML: {err}") from None
    workflow = check(data, path)
    write_text(path, text)
    return workflow


def free_slug(name: str) -> str:
    base = slugify(name) or "workflow"
    slug, count = base, 1
    while path_for(slug).exists():
        count += 1
        slug = f"{base}-{count}"
    return slug


def create(data: dict) -> Workflow:
    slug = free_slug(str(data.get("name", "")))
    return save(slug, data)


def delete(slug: str) -> None:
    path = path_for(slug)
    if not path.exists():
        raise WorkflowError(f"no workflow '{slug}'")
    path.unlink()


def _conditions(spec) -> list[dict]:
    """A condition set and any `not` nested in it, so nothing hides from review."""
    if not isinstance(spec, dict):
        return []
    return [spec, *_conditions(spec.get("not"))]


def effects(steps: list) -> list[str]:
    """What a workflow touches beyond running commands, for the review screen."""
    found = []
    describe = {
        "http": lambda s: f"Sends a {str(s.get('method', 'GET')).upper()} request to {s.get('url')}",
        "file": lambda s: f"{str(s.get('op')).title()}s {s.get('src')} to {s.get('dest')}",
        "open": lambda s: f"Opens {s.get('target')}",
        "type": lambda s: "Types into whichever app has focus",
        "run": lambda s: f"Runs your workflow {s.get('workflow')}",
        "clipboard": lambda s: "Replaces your clipboard" if s.get("op") == "set" else "Reads your clipboard",
        "screenshot": lambda s: "Takes a screenshot",
        "window": lambda s: f"{str(s.get('op', 'focus')).title()}s {s.get('app') or 'the focused window'}",
    }
    for step in steps or []:
        if step.get("action") in describe:
            found.append(describe[step["action"]](step))
        for key in ("then", "else", "steps"):
            found += effects(step.get(key))
        for condition in _conditions(step.get("if")):
            if "file_exists" in condition:
                found.append(f"Checks whether {condition['file_exists']} exists")
    return list(dict.fromkeys(found))


def shell_commands(steps: list) -> list[str]:
    """Every command a workflow would run, for the review before import."""
    commands = []
    for step in steps or []:
        if step.get("action") == "shell":
            program = step.get("shell")
            # A custom shell can be any program, so it must show up here too.
            commands.append(f"{program} -c {step.get('run', '')}" if program else str(step.get("run", "")))
        for key in ("then", "else", "steps"):
            commands += shell_commands(step.get(key))
        commands += [str(c["command"]) for c in _conditions(step.get("if")) if "command" in c]
    return commands
