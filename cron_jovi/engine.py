"""Runs a workflow: steps in order, variables between them, overlap handling."""

import fcntl
import json
import os
import re
import signal
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable

from . import paths, shellvars
from .action_api import ActionError, coerce, load_actions
from .conditions import CONDITIONS
from .explain import explain
from .history import History
from .workflow import STEP_KEYS, Workflow

VARIABLE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")
MAX_OUTPUT_LINES = 5000
MAX_REPEATS = 100000  # a typo shouldn't mean a loop that outlives the computer
TERM_GRACE = 10  # seconds a stopped run gets before SIGKILL


class RunStopped(BaseException):
    """SIGTERM arrived. BaseException so no step's error handling swallows it."""


class StopSteps(Exception):
    """A stop_on_error step failed."""


class Progress:
    """Which step a run is on, in a file, so the app can follow any run however it started."""

    def __init__(self, slug: str):
        self.path = paths.progress_file(slug)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.steps: dict[str, str] = {}
        self._write()

    def _write(self) -> None:
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(self.steps))
        os.replace(temp, self.path)

    def mark(self, where: str, state: str) -> None:
        self.steps[where] = state
        self._write()

    def finish(self) -> None:
        self.steps = {k: "stopped" if v == "running" else v for k, v in self.steps.items()}
        self._write()


class Context:
    """What an action sees of the run."""

    def __init__(self, echo: Callable[[str], None] | None = None):
        now = datetime.now()
        self.vars: dict[str, Any] = {
            "date": f"{now:%Y-%m-%d}", "time": f"{now:%H:%M}", "weekday": f"{now:%A}",
        }
        self.lines: deque[str] = deque(maxlen=MAX_OUTPUT_LINES)
        self.echo = echo
        self.summary = ""
        self.failure: ActionError | None = None
        self.progress: Progress | None = None

    def mark(self, where: str, state: str) -> None:
        if self.progress:
            self.progress.mark(where, state)

    def log(self, line: str) -> None:
        self.lines.append(line)
        if self.echo:
            self.echo(line)

    def step(self, status: str, text: str) -> None:
        self.log(f"{datetime.now():%H:%M:%S} {status:<4} {text}")

    def lookup(self, dotted: str) -> Any:
        value: Any = self.vars
        for part in dotted.split("."):
            if isinstance(value, list) and part == "count":
                value = len(value)
            elif isinstance(value, list) and part.isdigit() and 1 <= int(part) <= len(value):
                value = value[int(part) - 1]  # counts from 1, like {{ index }}
            elif isinstance(value, dict) and part in value:
                value = value[part]
            else:
                raise ActionError(f"undefined variable: {dotted}")
        return value

    def render(self, value: Any, quote: Callable[[str], str] | None = None) -> Any:
        """Fill in {{ variables }}. A lone {{ variable }} keeps its type."""
        if isinstance(value, dict):
            return {key: self.render(item, quote) for key, item in value.items()}
        if isinstance(value, list):
            return [self.render(item, quote) for item in value]
        if not isinstance(value, str):
            return value
        whole = VARIABLE.fullmatch(value.strip())
        if whole and not quote:
            return self.lookup(whole[1])

        def fill(match: re.Match) -> str:
            text = self.text(match[1])
            return quote(text) if quote else text

        return VARIABLE.sub(fill, value)

    def text(self, dotted: str) -> str:
        found = self.lookup(dotted)
        return ", ".join(map(str, found)) if isinstance(found, list) else str(found)

    def render_shell(self, command: str) -> tuple[str, dict[str, str]]:
        """A command that refers to its variables, plus the environment holding them."""
        env: dict[str, str] = {}

        def fill(match: re.Match) -> str:
            name = f"{shellvars.PREFIX}{len(env) + 1}"
            env[name] = self.text(match[1]).replace("\0", "")
            return shellvars.reference(name, command[:match.start()])

        return VARIABLE.sub(fill, command), env

    def run(self, argv: list[str], input: str | None = None, capture: bool = True) -> str:
        """Run a helper tool and return its stdout. Failure raises ActionError."""
        out = subprocess.PIPE if capture else subprocess.DEVNULL
        try:
            proc = subprocess.run(argv, input=input, stdout=out, stderr=out, text=True)
        except FileNotFoundError:
            raise ActionError(f"{argv[0]} not found", 127) from None
        if proc.returncode:
            detail = (proc.stderr or "").strip()
            raise ActionError(detail or f"{argv[0]} exited {proc.returncode}", proc.returncode)
        return (proc.stdout or "").rstrip("\n")

    def stream(self, argv: list[str], timeout: float | None = None,
               env: dict[str, str] | None = None) -> tuple[int, str]:
        """Run a long command, logging output live. Returns (exit code, output)."""
        try:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                start_new_session=True,
                # English messages, so error_table.yaml matches on any system.
                env={**os.environ, "LC_MESSAGES": "C", "LANGUAGE": "C", **(env or {})},
            )
        except FileNotFoundError:
            raise ActionError(f"{argv[0]} not found", 127) from None
        captured: deque[str] = deque(maxlen=MAX_OUTPUT_LINES)

        def read() -> None:
            with proc.stdout:  # here, since a backgrounded child can outlive the run
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    captured.append(line)
                    self.log(line)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            code = proc.wait(timeout)
        except subprocess.TimeoutExpired:
            stop_group(proc)
            raise ActionError(f"timed out after {timeout:g}s", 124) from None
        except BaseException:
            stop_group(proc)
            raise
        reader.join(1)  # a backgrounded child may hold the pipe open forever
        return code, "\n".join(captured)


def stop_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(5)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except ProcessLookupError:
        pass


def bind(defn, params: dict, ctx: Context) -> dict:
    hints = defn.hints()
    bound = {}
    for key, value in params.items():
        if key not in defn.raw:
            value = ctx.render(value)
        try:
            bound[key] = coerce(hints[key], value)
        except ValueError as err:
            raise ActionError(f"{key}: {err}") from None
    return bound


def run_action(step: dict, ctx: Context) -> bool:
    """True if the step worked."""
    defn = load_actions()[step["action"]]
    params = {key: value for key, value in step.items() if key not in STEP_KEYS}
    ctx.summary = defn.name
    try:
        result = defn.func(ctx, **bind(defn, params, ctx))
    except ActionError as err:
        err.step = ctx.summary
        ctx.step("fail", f"{ctx.summary}: {err} (exit {err.exit_code})")
        ctx.failure = ctx.failure or err
        if step.get("stop_on_error"):
            raise StopSteps from None
        return False
    ctx.vars["result"] = result
    if step.get("save_as"):
        ctx.vars[step["save_as"]] = result
    ctx.step("ok", ctx.summary)
    return True


def render_condition(spec: dict, ctx: Context) -> dict:
    rendered = {}
    for name, value in spec.items():
        if name == "command":
            rendered[name] = ctx.render_shell(str(value))
        elif name == "not":
            rendered[name] = render_condition(value, ctx)
        else:
            rendered[name] = ctx.render(value)
    return rendered


def evaluate(spec: dict, ctx: Context) -> bool:
    return all(CONDITIONS[name](value) for name, value in render_condition(spec, ctx).items())


def repeat_items(step: dict, ctx: Context) -> list | range:
    """What a repeat goes over: a list, parts of some text, or a count."""
    source = ctx.render(step["repeat"])
    if isinstance(source, list):
        return source
    text = "" if source is None else str(source).strip()
    if step.get("split") is not None:
        separator = str(ctx.render(step["split"]))
        if not separator:
            raise ActionError("Repeat needs something to split the text at.")
        return [part.strip() for part in text.split(separator) if part.strip()]
    if re.fullmatch(r"-?\d+(\.0+)?", text):
        count = int(float(text))
        if count > MAX_REPEATS:
            raise ActionError(f"Repeat was asked to run {count} times, and the limit is {MAX_REPEATS}.")
        return range(1, count + 1)
    return text.splitlines()


def run_repeat(step: dict, ctx: Context, where: str) -> None:
    items = repeat_items(step, ctx)
    ctx.step("ok", f"Repeat: {len(items)} time{'' if len(items) == 1 else 's'}")
    for index, item in enumerate(items, 1):
        ctx.vars.update(index=index, item=item)
        run_steps(step["steps"], ctx, f"{where}.steps")


def run_step(step: dict, ctx: Context, where: str) -> bool:
    if "if" in step:
        try:
            taken = evaluate(step["if"], ctx)
        except ActionError as err:
            ctx.step("fail", f"If: {err}")
            ctx.failure = ctx.failure or err
            raise StopSteps from None
        ctx.step("ok", f"If {', '.join(step['if'])}: {str(taken).lower()}")
        branch = "then" if taken else "else"
        run_steps(step.get(branch) or [], ctx, f"{where}.{branch}")
        return True
    if "repeat" in step:
        try:
            run_repeat(step, ctx, where)
        except ActionError as err:
            ctx.step("fail", f"Repeat: {err}")
            ctx.failure = ctx.failure or err
            raise StopSteps from None
        return True
    return run_action(step, ctx)


def run_steps(steps: list, ctx: Context, path: str = "steps") -> None:
    for index, step in enumerate(steps):
        where = f"{path}.{index}"
        if step.get("skip"):
            ctx.step("off", step.get("action") or "block")
            continue
        ctx.mark(where, "running")
        try:
            worked = run_step(step, ctx, where)
        except StopSteps:
            ctx.mark(where, "failed")
            raise
        ctx.mark(where, "ok" if worked else "failed")


def run_single_step(step: dict, echo: Callable[[str], None]) -> int:
    """Try one step on its own. Leaves no history, since it isn't a real run."""
    ctx = Context(echo)
    try:
        run_steps([step], ctx)
    except StopSteps:
        pass
    if ctx.failure and "undefined variable" in str(ctx.failure):
        echo("This step uses a value from an earlier step. Run the whole workflow to test it.")
    elif ctx.failure:
        echo(explain(ctx.failure, list(ctx.lines)))
    return ctx.failure.exit_code if ctx.failure else 0


def execute(workflow: Workflow, ctx: Context) -> None:
    """Run the steps, and on_failure if one failed. Sets ctx.failure."""
    try:
        run_steps(workflow.steps, ctx)
    except StopSteps:
        pass
    if ctx.failure and workflow.on_failure:
        ctx.vars["error"] = explain(ctx.failure, list(ctx.lines))
        first_failure = ctx.failure
        try:
            run_steps(workflow.on_failure, ctx, "on_failure")
        except StopSteps:
            pass
        ctx.failure = first_failure


def _try_lock(path) -> int | None:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def is_running(slug: str) -> bool:
    fd = _try_lock(paths.lock_file(slug)) if paths.lock_file(slug).exists() else None
    if fd is None:
        return paths.lock_file(slug).exists()
    os.close(fd)
    return False


def stop_run(slug: str) -> bool:
    """SIGTERM a workflow's run, wherever it was started from."""
    if not is_running(slug):
        return False
    try:
        os.kill(int(paths.lock_file(slug).read_text()), signal.SIGTERM)
    except (OSError, ValueError):
        return False
    return True


def _wait_for_lock(path, seconds: float) -> int | None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        fd = _try_lock(path)
        if fd is not None:
            return fd
        time.sleep(0.1)
    return None


def _stop_previous(path) -> int | None:
    """SIGTERM the run holding the lock, SIGKILL it if it ignores that."""
    try:
        pid = int(path.read_text())
    except (OSError, ValueError):
        return _wait_for_lock(path, 1)
    for sig, wait in ((signal.SIGTERM, TERM_GRACE), (signal.SIGKILL, 2)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        fd = _wait_for_lock(path, wait)
        if fd is not None:
            return fd
    return None


def run_workflow(
    workflow: Workflow,
    history: History,
    trigger: str = "manual",
    scheduled_at: float | None = None,
    note: str = "",
    echo: Callable[[str], None] | None = None,
    variables: dict | None = None,
) -> int:
    """Run under the overlap policy. Returns the exit code for the CLI."""
    lock = paths.lock_file(workflow.slug)
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = _try_lock(lock)
    if fd is None and workflow.trigger.if_running == "restart":
        fd = _stop_previous(lock)
    if fd is None:
        history.skip(workflow.slug, trigger, scheduled_at, "previous run still active")
        if echo:
            echo("skipped: previous run still active")
        return 0

    os.ftruncate(fd, 0)
    os.pwrite(fd, str(os.getpid()).encode(), 0)
    history.close_abandoned(workflow.slug)
    run_id = history.start(workflow.slug, trigger, scheduled_at, note)
    ctx = Context(echo)
    ctx.vars["workflow"] = workflow.name
    ctx.vars.update(variables or {})
    ctx.progress = Progress(workflow.slug)

    def on_term(*_):
        raise RunStopped

    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, on_term)

    status, code, notes = "succeeded", 0, [note] if note else []
    try:
        execute(workflow, ctx)
        if ctx.failure:
            status, code = "failed", ctx.failure.exit_code
            notes.append(explain(ctx.failure, list(ctx.lines)))
    except (RunStopped, KeyboardInterrupt):
        status, code = "stopped", 143
        notes.append("Stopped before it finished")
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
        ctx.progress.finish()
        history.finish(run_id, status, code, "; ".join(notes), "\n".join(ctx.lines))
        history.prune(workflow.slug)
        os.close(fd)
    if status == "failed" and trigger != "manual" and not workflow.on_failure:
        tell_user(workflow, notes[-1])
    return code


def tell_user(workflow: Workflow, reason: str) -> None:
    """Nobody is watching a background run, so its failure can't stay in a log."""
    try:
        subprocess.run(
            ["notify-send", "--app-name=Cron Jovi", "-u", "critical", "--",
             f"{workflow.name} failed", reason],
            capture_output=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
