"""Turns what a failed step printed into a sentence anyone can act on.

Exit codes and raw output stay in history as technical details. This is what
people see: cards, notifications, the run log and {{ error }}. The wording lives
in error_table.yaml; this file only decides which entry applies.
"""

import re
import shutil
from functools import lru_cache
from pathlib import Path

import yaml

from . import paths

UNKNOWN_MARK = "ran into a problem and stopped"
PATH = re.compile(
    r"""["'`‘“]((?:~|\.{0,2}/)[^"'`’”]+)["'`’”]"""  # quoted
    r"""|(?<![\w:/.])((?:~|\.{0,2}/)[\w./~+@-]+)"""  # bare
    r"""|["'`‘“]([\w./+@~][\w./+@~-]*)["'`’”]"""  # quoted plain name
    # `cat: nope.txt: No such file`, the form with no quotes or slash at all
    r"""|:\s([\w./+@~-]+):\s*(?:cannot open|no such|permission denied|is a directory|not a directory)"""
    r"""|--\s([\w./+@~-]+)"""  # `No such file or directory -- nope.rb`
    r"""|can't read ([\w./+@~-]+):""",  # sed
    re.I,
)
ERRORISH = re.compile(r"\b(error|exception|fatal|failed|failure|cannot|can't|unable)\b", re.I)
MAX_QUOTE = 120
RECENT = 25  # lines near the failure; a word in earlier output proves nothing
WRAPPERS = {"sudo", "env", "nice", "ionice", "nohup", "time", "command", "exec"}


def _compile(entries: list) -> list[dict]:
    rules = []
    for entry in entries or []:
        try:
            rules.append({**entry, "regex": re.compile(str(entry["match"]), re.I)})
        except (re.error, KeyError, TypeError):
            continue  # one bad line in someone's own table shouldn't lose the rest
    return rules


def _read(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def table() -> dict:
    """The shipped table, with the user's own entries in front."""
    shipped = _read(Path(__file__).with_name("error_table.yaml"))
    own = _read(paths.config_home() / "cronjovi" / "errors.yaml")
    codes = {tool: dict(values) for tool, values in (shipped.get("exit_codes") or {}).items()}
    for tool, values in (own.get("exit_codes") or {}).items():
        codes.setdefault(tool, {}).update(values or {})
    return {
        "output": _compile(own.get("output")) + _compile(shipped.get("output")),
        "messages": _compile(own.get("messages")) + _compile(shipped.get("messages")),
        "exit_codes": codes,
        "any_exit": {**(shipped.get("any_exit") or {}), **(own.get("any_exit") or {})},
        "first_exit": set(shipped.get("first_exit") or []),
    }


def _path(line: str) -> str:
    for match in PATH.finditer(line):
        found = next(group for group in match.groups() if group).rstrip(":,.")
        if found != "/":
            return found
    return ""


def _render(rule: dict, match: re.Match, line: str) -> str:
    text = str(rule["say"])
    if "{path}" in text:
        path = _path(line)
        if not path:
            return str(rule.get("else") or text.replace("{path}", "That"))
        text = text.replace("{path}", path)
    groups = {k: v for k, v in match.groupdict().items() if v}
    if "{name}" in text:
        text = text.replace("{name}", groups.get("name") or groups.get("other") or "that")
    return text


def _tool(command: str) -> str:
    """The program that ran: `sudo rsync -a x` is rsync."""
    for word in command.split():
        name = word.rsplit("/", 1)[-1]
        if "=" not in name and name not in WRAPPERS and not name.startswith("-"):
            return name
    return ""


def _program_output(lines: list[str]) -> list[str]:
    """What the program printed, without the engine's own log lines."""
    return [line for line in lines if not line.startswith("$ ")
            and not re.match(r"\d\d:\d\d:\d\d (ok|fail|off)\b", line)]


def lookup(message: str, code: int, lines: list[str], command: str = "") -> str | None:
    """A translation, or None if nothing in the table fits."""
    rules = table()
    tool = _tool(command)
    text = _program_output(lines)[-RECENT:]
    for rule in rules["messages"]:
        if match := rule["regex"].search(message):
            return _render(rule, match, message)
    if code in rules["first_exit"] and re.search(r" exited \d+$", message):
        return str(rules["any_exit"][code])
    # A program's own code is more exact than a general word in its output: grep's
    # exit 1 prints nothing, and rsync 23 prints a dozen lines.
    for rule in rules["output"]:
        if rule.get("tool") and rule["tool"] != tool:
            continue
        for line in text:
            if match := rule["regex"].search(line):
                return _render(rule, match, line)
    if known := rules["exit_codes"].get(tool, {}).get(code):
        return str(known)
    if not re.search(r" exited \d+$", message):
        return None
    if known := rules["any_exit"].get(code):
        return str(known)
    return None


def explain(failure: Exception, lines: list[str]) -> str:
    message = str(failure)
    code = getattr(failure, "exit_code", 1)
    command = getattr(failure, "step", "") or ""
    if match := re.fullmatch(r"timed out after ([\d.]+)s?", message):
        seconds = float(match[1])
        return f"This step took longer than {seconds:g} second{'' if seconds == 1 else 's'}, so it was stopped."
    if known := lookup(message, code, lines, command):
        return known
    if not re.search(r" exited \d+$", message):
        return message[0].upper() + message[1:] if message else "This step didn't work."
    first = command.split()[0] if command.split() else ""
    # A shell word like `exit` or `if` isn't a program anyone would recognise.
    who = first.rsplit("/", 1)[-1] if first and shutil.which(first) else "A command"
    said = [line.strip() for line in _program_output(lines)[-RECENT:] if line.strip()]
    if said:
        # Nothing to translate, but its own words beat sending people to a log.
        worst = [line for line in said if ERRORISH.search(line)] or said
        return f"{who} {UNKNOWN_MARK}. It said: “{worst[-1][:MAX_QUOTE]}”"
    return f"{who} {UNKNOWN_MARK} without saying why."
