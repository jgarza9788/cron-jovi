"""The contract between the engine and action plugins.

An action is one decorated function in one file under cron_jovi/actions/. Its
type hints are the action's inputs, its return value is the action's output:

    @action("notify", tools=["notify-send"])
    def notify(ctx, text: str, urgency: str = "normal") -> None:
        ctx.run(["notify-send", "-u", urgency, text])
"""

import importlib
import inspect
import pkgutil
import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

TEMPLATE = "{{"
_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*$")
_UNITS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, None: 1}


class ActionError(Exception):
    """A step failed. exit_code ends up in run history."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class Duration(float):
    """Seconds, written in YAML as 10s, 5m, 1h, 500ms or a bare number."""

    @classmethod
    def parse(cls, value: Any) -> "Duration":
        match = _DURATION.match(str(value))
        if not match:
            raise ValueError(f"not a duration: {value!r}")
        return cls(float(match[1]) * _UNITS[match[2]])


@dataclass
class ActionDef:
    name: str
    func: Callable
    tools: list = field(default_factory=list)  # a tuple entry means "any of these"
    raw: tuple = ()  # params the action renders itself
    title: str = ""
    blurb: str = ""
    category: str = "Scripting"
    icon: str = "zap"
    color: str = "blue"

    def hints(self) -> dict:
        hints = typing.get_type_hints(self.func)
        hints.pop("return", None)
        hints.pop("ctx", None)
        return hints

    def required(self) -> list[str]:
        params = list(inspect.signature(self.func).parameters.values())[1:]
        return [p.name for p in params if p.default is inspect.Parameter.empty]


REGISTRY: dict[str, ActionDef] = {}


def action(
    name: str,
    tools: list | None = None,
    raw: tuple = (),
    title: str = "",
    blurb: str = "",
    category: str = "Scripting",
    icon: str = "zap",
    color: str = "blue",
):
    def register(func: Callable) -> Callable:
        REGISTRY[name] = ActionDef(
            name, func, tools or [], raw, title or name.title(), blurb, category, icon, color
        )
        return func

    return register


def load_actions() -> dict[str, ActionDef]:
    from . import actions

    for module in pkgutil.iter_modules(actions.__path__):
        importlib.import_module(f"{actions.__name__}.{module.name}")
    return REGISTRY


def field_kind(hint: Any) -> dict:
    """How the GUI should edit a param of this type."""
    if typing.get_origin(hint) in (typing.Union, types.UnionType):
        hint = next(a for a in typing.get_args(hint) if a is not type(None))
    if typing.get_origin(hint) is typing.Literal:
        return {"kind": "choice", "choices": list(typing.get_args(hint))}
    if typing.get_origin(hint) is list:
        return {"kind": "list"}
    if hint is Duration:
        return {"kind": "duration"}
    if hint is bool:
        return {"kind": "bool"}
    if hint is int or hint is float:
        return {"kind": "number"}
    if hint is dict:
        return {"kind": "json"}
    return {"kind": "text"}


def describe(defn: ActionDef) -> dict:
    """An action as the GUI's library and blocks see it."""
    params = list(inspect.signature(defn.func).parameters.values())[1:]
    hints = defn.hints()
    fields = []
    for param in params:
        field_info = field_kind(hints[param.name])
        field_info["name"] = param.name
        field_info["required"] = param.default is inspect.Parameter.empty
        if not field_info["required"]:
            default = param.default
            field_info["default"] = default if isinstance(default, (str, int, float, bool)) else None
        fields.append(field_info)
    return {
        "name": defn.name,
        "title": defn.title,
        "blurb": defn.blurb,
        "category": defn.category,
        "icon": defn.icon,
        "color": defn.color,
        "tools": [list(t) if isinstance(t, tuple) else [t] for t in defn.tools],
        "fields": fields,
    }


def coerce(hint: Any, value: Any) -> Any:
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if hint is Any:
        return value
    if origin in (typing.Union, types.UnionType):
        if value is None:
            return None
        return coerce(next(a for a in args if a is not type(None)), value)
    if origin is typing.Literal:
        # YAML reads a bare `on`/`off` as a boolean.
        if isinstance(value, bool) and "on" in args:
            value = "on" if value else "off"
        if value not in args:
            raise ValueError(f"must be one of {', '.join(map(str, args))}; got {value!r}")
        return value
    if origin is list:
        items = value if isinstance(value, list) else [value]
        return [coerce(args[0], item) for item in items]
    if hint is Duration:
        return Duration.parse(value)
    if hint is bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "yes", "on", "1"):
            return True
        if text in ("false", "no", "off", "0"):
            return False
        raise ValueError(f"not a boolean: {value!r}")
    if hint is int or hint is float:
        try:
            return hint(value)
        except (TypeError, ValueError):
            raise ValueError(f"not a number: {value!r}") from None
    if hint is str:
        return "" if value is None else str(value)
    return value


def check_params(defn: ActionDef, params: dict) -> list[str]:
    """Problems with a step's params, found at load time rather than mid-run."""
    hints = defn.hints()
    problems = [f"unknown option '{key}'" for key in params if key not in hints]
    problems += [f"missing option '{key}'" for key in defn.required() if key not in params]
    for key, value in params.items():
        if key not in hints or (isinstance(value, str) and TEMPLATE in value):
            continue
        try:
            coerce(hints[key], value)
        except ValueError as err:
            problems.append(f"{key}: {err}")
    return problems
