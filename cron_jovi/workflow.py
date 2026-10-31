"""Load and validate workflow YAML. The file's stem is the workflow's slug."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import paths
from .action_api import check_params, load_actions
from .conditions import CONDITIONS

STEP_KEYS = {"action", "save_as", "stop_on_error", "skip"}
IF_MISSED = ("run_once", "skip")
IF_RUNNING = ("skip", "restart")
TRIGGER_KEYS = {"hotkey", "schedule", "if_missed", "if_running", "file", "device", "battery",
                "power", "webhook", "login", "wake"}
FILE_EVENTS = ("created", "modified", "deleted", "moved")
POWER_STATES = ("plugged", "unplugged")
MAX_STEPS = 1000  # YAML aliases let 2 KB expand to billions of steps
MAX_DEPTH = 16
SAFE_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]*")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class WorkflowError(Exception):
    pass


@dataclass
class Trigger:
    hotkey: str | None = None
    schedule: str | None = None
    if_missed: str = "run_once"
    if_running: str = "skip"
    file: dict | None = None
    device: dict | None = None
    battery: dict | None = None
    power: str | None = None
    webhook: bool = False
    login: bool = False
    wake: bool = False

    def has_events(self) -> bool:
        return bool(self.file or self.device or self.battery or self.power or self.webhook
                    or self.login or self.wake)

    def describe(self) -> str:
        parts = []
        if self.hotkey:
            parts.append(self.hotkey)
        if self.schedule:
            parts.append(self.schedule)
        if self.file:
            parts.append(f"file in {self.file['path']}")
        if self.device:
            parts.append(f"{self.device.get('match') or 'any'} device plugged in")
        if self.battery:
            parts.append(f"battery below {self.battery['below']}%")
        if self.power:
            parts.append(f"power {self.power}")
        if self.webhook:
            parts.append("webhook")
        if self.login:
            parts.append("at login")
        if self.wake:
            parts.append("after sleep")
        return " · ".join(parts) or "manual"


@dataclass
class Workflow:
    slug: str
    name: str
    path: Path
    description: str = ""
    enabled: bool = True
    trigger: Trigger = field(default_factory=Trigger)
    steps: list = field(default_factory=list)
    on_failure: list = field(default_factory=list)
    icon: str = "zap"
    color: str = "yellow"
    folder: str = ""
    favorite: bool = False

    def action_count(self) -> int:
        return _count(self.steps)


def _count(steps: list) -> int:
    total = 0
    for step in steps:
        total += "action" in step
        for key in ("then", "else", "steps"):
            total += _count(step.get(key) or [])
    return total


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _file_trigger(spec: Any) -> dict | None:
    if not spec:
        return None
    if isinstance(spec, str):
        spec = {"path": spec}
    if not isinstance(spec, dict) or not spec.get("path"):
        raise WorkflowError("trigger file needs a path")
    unknown = set(spec) - {"path", "pattern", "events", "recursive"}
    if unknown:
        raise WorkflowError(f"unknown file option: {', '.join(sorted(unknown))}")
    events = spec.get("events", ["created"])
    if isinstance(events, str):
        events = [events]
    if not events or set(events) - set(FILE_EVENTS):
        raise WorkflowError(f"file events must be from {', '.join(FILE_EVENTS)}")
    return {
        "path": str(spec["path"]),
        "pattern": str(spec.get("pattern") or "*"),
        "events": list(events),
        "recursive": bool(spec.get("recursive", False)),
    }


def _device_trigger(spec: Any) -> dict | None:
    if not spec:
        return None
    if spec is True:
        spec = {}
    if isinstance(spec, str):
        spec = {"match": spec}
    if not isinstance(spec, dict):
        raise WorkflowError("trigger device must be a mapping")
    unknown = set(spec) - {"match", "event"}
    if unknown:
        raise WorkflowError(f"unknown device option: {', '.join(sorted(unknown))}")
    event = spec.get("event", "added")
    if event not in ("added", "removed"):
        raise WorkflowError("device event must be added or removed")
    return {"match": str(spec.get("match") or ""), "event": event}


def _battery_trigger(spec: Any) -> dict | None:
    if spec is None or spec is False:
        return None
    below = spec.get("below") if isinstance(spec, dict) else spec
    if isinstance(below, bool) or not isinstance(below, int) or not 1 <= below <= 99:
        raise WorkflowError("battery below must be a percentage from 1 to 99")
    return {"below": below}


def _trigger(data: Any) -> Trigger:
    if data is None:
        return Trigger()
    if not isinstance(data, dict):
        raise WorkflowError("trigger must be a mapping")
    unknown = set(data) - TRIGGER_KEYS
    if unknown:
        raise WorkflowError(f"unknown trigger option: {', '.join(sorted(unknown))}")
    trigger = Trigger(
        hotkey=plain(data.get("hotkey"), "hotkey"),
        schedule=plain(data.get("schedule"), "schedule"),
        if_missed=data.get("if_missed", "run_once"),
        if_running=data.get("if_running", "skip"),
        file=_file_trigger(data.get("file")),
        device=_device_trigger(data.get("device")),
        battery=_battery_trigger(data.get("battery")),
        power=data.get("power"),
        webhook=bool(data.get("webhook", False)),
        login=bool(data.get("login", False)),
        wake=bool(data.get("wake", False)),
    )
    if trigger.power and trigger.power not in POWER_STATES:
        raise WorkflowError(f"power must be one of {', '.join(POWER_STATES)}")
    if trigger.if_missed not in IF_MISSED:
        raise WorkflowError(f"if_missed must be one of {', '.join(IF_MISSED)}")
    if trigger.if_running not in IF_RUNNING:
        raise WorkflowError(f"if_running must be one of {', '.join(IF_RUNNING)}")
    return trigger


def _check_conditions(spec: dict, at: str) -> None:
    unknown = set(spec) - set(CONDITIONS)
    if unknown:
        raise WorkflowError(f"{at}: unknown condition: {', '.join(sorted(unknown))}")
    if "not" in spec:
        if not isinstance(spec["not"], dict) or not spec["not"]:
            raise WorkflowError(f"{at}: not needs at least one condition")
        _check_conditions(spec["not"], at)
    for name in ("equals", "contains"):
        if name in spec and (not isinstance(spec[name], list) or len(spec[name]) != 2):
            raise WorkflowError(f"{at}: {name} needs two values")


def plain(value: Any, what: str) -> Any:
    """These end up in systemd units and compositor config, where a line break is code."""
    if isinstance(value, str) and CONTROL.search(value):
        raise WorkflowError(f"{what} can't contain line breaks or control characters")
    return value


def validate_steps(steps: Any, where: str = "steps", budget: list | None = None, depth: int = 0) -> None:
    budget = budget if budget is not None else [MAX_STEPS]
    if depth > MAX_DEPTH:
        raise WorkflowError(f"{where}: nested too deeply")
    if not isinstance(steps, list):
        raise WorkflowError(f"{where} must be a list")
    actions = load_actions()
    for index, step in enumerate(steps, 1):
        at = f"{where}[{index}]"
        budget[0] -= 1
        if budget[0] < 0:
            raise WorkflowError(f"too many steps (the limit is {MAX_STEPS})")
        if not isinstance(step, dict):
            raise WorkflowError(f"{at}: must be a mapping")
        if "if" in step:
            if not isinstance(step["if"], dict) or not step["if"]:
                raise WorkflowError(f"{at}: if needs at least one condition")
            _check_conditions(step["if"], at)
            validate_steps(step.get("then") or [], f"{at}.then", budget, depth + 1)
            validate_steps(step.get("else") or [], f"{at}.else", budget, depth + 1)
        elif "repeat" in step:
            validate_steps(step.get("steps"), f"{at}.steps", budget, depth + 1)
        elif "action" in step:
            name = step["action"]
            if name not in actions:
                raise WorkflowError(f"{at}: unknown action '{name}'")
            params = {k: v for k, v in step.items() if k not in STEP_KEYS}
            problems = check_params(actions[name], params)
            if problems:
                raise WorkflowError(f"{at} ({name}): {'; '.join(problems)}")
        else:
            raise WorkflowError(f"{at}: needs action, if or repeat")


def parse(data: Any, path: Path) -> Workflow:
    if not isinstance(data, dict):
        raise WorkflowError("must be a mapping")
    if not data.get("name"):
        raise WorkflowError("missing name")
    budget = [MAX_STEPS]
    validate_steps(data.get("steps"), "steps", budget)
    validate_steps(data.get("on_failure") or [], "on_failure", budget)
    return Workflow(
        slug=path.stem,
        name=" ".join(str(data["name"]).split()),
        description=str(data.get("description") or ""),
        path=path,
        enabled=bool(data.get("enabled", True)),
        trigger=_trigger(data.get("trigger")),
        steps=data["steps"],
        on_failure=data.get("on_failure") or [],
        icon=str(data.get("icon", "zap")),
        color=str(data.get("color", "yellow")),
        folder=str(data.get("folder", "")),
        favorite=bool(data.get("favorite", False)),
    )


def load(path: Path) -> Workflow:
    if not SAFE_SLUG.fullmatch(path.stem):
        raise WorkflowError(f"{path.name}: rename it using lowercase letters, numbers and dashes")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as err:
        raise WorkflowError(f"{path.name}: invalid YAML: {err}") from None
    try:
        return parse(data, path)
    except WorkflowError as err:
        raise WorkflowError(f"{path.name}: {err}") from None


def discover() -> tuple[list[Workflow], list[str]]:
    """All workflows, plus an error per file that would not load."""
    workflows, errors = [], []
    folder = paths.workflows_dir()
    files = sorted([*folder.glob("*.yaml"), *folder.glob("*.yml")])
    for path in files:
        try:
            workflows.append(load(path))
        except WorkflowError as err:
            errors.append(str(err))
    return workflows, errors


def find(name: str) -> Workflow:
    """Look up by slug or display name, case-insensitively."""
    folder = paths.workflows_dir()
    for suffix in (".yaml", ".yml"):
        path = folder / f"{slugify(name)}{suffix}"
        if path.exists():
            return load(path)
    workflows, _ = discover()
    for workflow in workflows:
        if workflow.name.lower() == name.lower():
            return workflow
    raise WorkflowError(f"no workflow named '{name}' in {folder}")
