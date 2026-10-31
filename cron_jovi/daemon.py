"""The engine service: watches for events and starts runs.

Hotkeys and timers need nothing running. File, device, power and webhook
triggers do, so this service exists only while a workflow uses one of them.
Runs start in their own systemd units, so restarting the engine after an edit
never kills a backup that's halfway through.
"""

import fnmatch
import hmac
import json
import logging
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Callable

from . import paths
from .history import History
from .workflow import Workflow, discover

ENGINE_UNIT = "cronjovi-engine.service"
ENGINE_SERVICE = """\
[Unit]
Description=Cron Jovi engine

[Service]
ExecStart={python} -m cron_jovi daemon
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""

SETTLE = 1.0  # seconds a file must stay quiet, so half-written downloads don't fire
MAX_FIRES = 30  # per workflow, per minute; stops a workflow re-triggering itself forever
POLL = 30  # seconds between battery checks
TEMP_FILES = ("*.part", "*.crdownload", "*.tmp", "*.swp", "*~", ".*")
WEBHOOK_PORT = 8765
MAX_WEBHOOK_BYTES = 16 * 1024


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def fingerprint(workflows: list[Workflow]) -> str:
    """Changes only when what the engine watches changes."""
    wanted = [(w.slug, w.trigger.file, w.trigger.device, w.trigger.battery, w.trigger.power,
               w.trigger.webhook, w.trigger.login, w.trigger.wake)
              for w in workflows if w.enabled and w.trigger.has_events()]
    return json.dumps(wanted, sort_keys=True)


def sync_engine(workflows: list[Workflow]) -> list[str]:
    """Run the engine only while something needs it. Editing a step won't restart it."""
    unit = paths.systemd_user_dir() / ENGINE_UNIT
    stamp = paths.state_dir() / "engine.json"
    needed = any(w.enabled and w.trigger.has_events() for w in workflows)
    if not needed:
        if unit.exists():
            _systemctl("disable", "--now", ENGINE_UNIT)
            unit.unlink()
            _systemctl("daemon-reload")
        stamp.unlink(missing_ok=True)
        return []
    text = ENGINE_SERVICE.format(python=sys.executable)
    unit_changed = not unit.exists() or unit.read_text() != text
    if unit_changed:
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(text)
        _systemctl("daemon-reload")
    wanted = fingerprint(workflows)
    current = stamp.read_text() if stamp.exists() else ""
    result = _systemctl("enable", ENGINE_UNIT)
    if result.returncode:
        return [f"{ENGINE_UNIT}: {result.stderr.strip()}"]
    if wanted != current or unit_changed or engine_state() != "running":
        result = _systemctl("restart", ENGINE_UNIT)
        if result.returncode:
            return [f"{ENGINE_UNIT}: {result.stderr.strip()}"]
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(wanted)
    return []


def engine_state() -> str:
    if not (paths.systemd_user_dir() / ENGINE_UNIT).exists():
        return "not needed"
    state = _systemctl("is-active", ENGINE_UNIT).stdout.strip()
    return "running" if state == "active" else state or "stopped"


def remove_engine() -> None:
    _systemctl("disable", "--now", ENGINE_UNIT)
    (paths.systemd_user_dir() / ENGINE_UNIT).unlink(missing_ok=True)
    (paths.state_dir() / "engine.json").unlink(missing_ok=True)
    _systemctl("daemon-reload")


def spawn_event(workflow: Workflow, trigger: str, variables: dict, note: str = "") -> None:
    payload = json.dumps(variables)
    unit = f"cronjovi-job-{workflow.slug}-{time.time_ns()}"
    subprocess.run(
        [
            "systemd-run", "--user", "--collect", "--quiet", f"--unit={unit}",
            f"--description=Cron Jovi: {workflow.name}",
            sys.executable, "-m", "cron_jovi", "run", workflow.slug,
            "--trigger", trigger, "--vars-json", payload, "--note", note,
        ],
        check=True,
    )


class Limiter:
    """Refuses a workflow that fires too fast, and reports it once per burst."""

    def __init__(self, limit: int = MAX_FIRES, window: float = 60, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self.fires: dict[str, deque] = defaultdict(deque)
        self.reported: set[str] = set()

    def allow(self, slug: str) -> tuple[bool, bool]:
        """(may fire, should report that it was stopped)."""
        now = self.clock()
        recent = self.fires[slug]
        while recent and now - recent[0] > self.window:
            recent.popleft()
        if len(recent) >= self.limit:
            first = slug not in self.reported
            self.reported.add(slug)
            return False, first
        self.reported.discard(slug)
        recent.append(now)
        return True, False


def file_matches(spec: dict, path: str, event: str) -> bool:
    name = os.path.basename(path)
    if any(fnmatch.fnmatch(name, pattern) for pattern in TEMP_FILES):
        return False
    return event in spec["events"] and fnmatch.fnmatch(name, spec["pattern"])


class FileWatch:
    """One watched folder. Waits for a file to settle before firing."""

    def __init__(self, workflow: Workflow, fire: Callable, settle: float = SETTLE):
        self.workflow = workflow
        self.spec = workflow.trigger.file
        self.fire = fire
        self.settle = settle
        self.lock = threading.Lock()
        self.timers: dict[str, threading.Timer] = {}

    def on_event(self, kind: str, path: str) -> None:
        if not file_matches(self.spec, path, kind):
            return
        with self.lock:
            if path in self.timers:
                self.timers[path].cancel()
            timer = threading.Timer(self.settle, self._done, (kind, path))
            timer.daemon = True
            self.timers[path] = timer
            timer.start()

    def _done(self, kind: str, path: str) -> None:
        with self.lock:
            self.timers.pop(path, None)
        self.fire(self.workflow, "file", {
            "file": {"path": path, "name": os.path.basename(path), "event": kind},
        })


def start_file_watches(watches: list[FileWatch]):
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class Handler(FileSystemEventHandler):
        def __init__(self, watch: FileWatch):
            self.watch = watch

        def on_any_event(self, event):
            if event.is_directory:
                return
            if event.event_type == "closed":
                self.watch.on_event("created", event.src_path)
            elif event.event_type == "moved":
                self.watch.on_event("moved", event.dest_path)
                self.watch.on_event("created", event.dest_path)
            elif event.event_type in ("created", "modified", "deleted"):
                self.watch.on_event(event.event_type, event.src_path)

    observer = Observer()
    problems = []
    for watch in watches:
        folder = Path(watch.spec["path"]).expanduser()
        if not folder.is_dir():
            problems.append((watch.workflow, f"Folder not found: {folder}"))
            continue
        observer.schedule(Handler(watch), str(folder), recursive=watch.spec["recursive"])
    observer.daemon = True
    observer.start()
    return observer, problems


def parse_udev(lines):
    """Turn `udevadm monitor --property` output into one dict per event."""
    block: dict = {}
    for line in lines:
        line = line.rstrip("\n")
        if not line:
            if block.get("ACTION"):
                yield block
            block = {}
        elif "=" in line and not line.startswith("UDEV"):
            key, _, value = line.partition("=")
            block[key] = value
    if block.get("ACTION"):
        yield block


def device_name(event: dict) -> str:
    for key in ("ID_MODEL_FROM_DATABASE", "ID_MODEL", "ID_SERIAL", "PRODUCT"):
        if event.get(key):
            return event[key].replace("_", " ")
    vendor = event.get("ID_VENDOR_FROM_DATABASE") or event.get("ID_VENDOR") or ""
    return vendor or "USB device"


def device_matches(spec: dict, event: dict) -> bool:
    if event.get("DEVTYPE") != "usb_device":
        return False  # one plug-in produces an event per interface
    if event.get("ACTION") != {"added": "add", "removed": "remove"}[spec["event"]]:
        return False
    needle = spec["match"].lower()
    haystack = " ".join(str(event.get(key, "")) for key in (
        "ID_MODEL", "ID_MODEL_FROM_DATABASE", "ID_VENDOR", "ID_VENDOR_FROM_DATABASE", "ID_SERIAL",
    )).replace("_", " ").lower()
    return needle in haystack


def watch_devices(rules: list[Workflow], fire: Callable, stop: threading.Event) -> None:
    proc = subprocess.Popen(
        # stdbuf: into a pipe these tools hold events back until a buffer fills.
        ["stdbuf", "-oL", "udevadm", "monitor", "--udev", "--subsystem-match=usb", "--property"],
        stdout=subprocess.PIPE, text=True, errors="replace",
    )
    threading.Thread(target=lambda: (stop.wait(), proc.terminate()), daemon=True).start()
    for event in parse_udev(proc.stdout):
        for workflow in rules:
            if device_matches(workflow.trigger.device, event):
                fire(workflow, "device", {"device": {"name": device_name(event)}})


def system_batteries(root: Path) -> list[Path]:
    """Laptop batteries only. Wireless mice and keyboards list here too."""
    found = []
    for path in sorted(root.glob("*")):
        try:
            kind = (path / "type").read_text().strip()
            scope = (path / "scope").read_text().strip() if (path / "scope").exists() else "System"
        except OSError:
            continue
        if kind == "Battery" and scope != "Device" and (path / "capacity").exists():
            found.append(path)
    return found


def mains_supplies(root: Path) -> list[Path]:
    found = []
    for path in sorted(root.glob("*")):
        try:
            if (path / "type").read_text().strip() == "Mains":
                found.append(path)
        except OSError:
            continue
    return found


def read_power(root: Path) -> dict:
    """{percent, discharging, plugged}, with None where this machine has no such thing."""
    state = {"percent": None, "discharging": False, "plugged": None}
    batteries = system_batteries(root)
    if batteries:
        try:
            state["percent"] = min(int((b / "capacity").read_text()) for b in batteries)
            state["discharging"] = any(
                (b / "status").read_text().strip() == "Discharging" for b in batteries)
        except (OSError, ValueError):
            pass
    mains = mains_supplies(root)
    if mains:
        try:
            state["plugged"] = any((m / "online").read_text().strip() == "1" for m in mains)
        except OSError:
            pass
    elif batteries:
        state["plugged"] = not state["discharging"]
    return state


class PowerWatch:
    """Fires on the change, not the state: once per drop below, once per plug."""

    def __init__(self, rules: list[Workflow], fire: Callable):
        self.rules = rules
        self.fire = fire
        self.armed = {w.slug: True for w in rules if w.trigger.battery}
        self.plugged: bool | None = None

    def check(self, state: dict) -> None:
        percent = state["percent"]
        for workflow in self.rules:
            spec = workflow.trigger.battery
            if not spec or percent is None:
                continue
            low = percent < spec["below"]
            if low and state["discharging"] and self.armed[workflow.slug]:
                self.armed[workflow.slug] = False
                self.fire(workflow, "battery", {"battery": {"percent": percent}})
            elif not low:
                self.armed[workflow.slug] = True
        plugged = state["plugged"]
        if plugged is None:
            return
        if self.plugged is not None and plugged != self.plugged:
            word = "plugged" if plugged else "unplugged"
            for workflow in self.rules:
                if workflow.trigger.power == word:
                    self.fire(workflow, "power", {"power": {"state": word}})
        self.plugged = plugged


def watch_power(rules, fire, stop, root=Path("/sys/class/power_supply"), every=POLL) -> None:
    watch = PowerWatch(rules, fire)
    while not stop.is_set():
        watch.check(read_power(root))
        stop.wait(every)


def login_marker() -> Path:
    """In the runtime dir, which lasts exactly as long as the session."""
    return Path(os.environ.get("XDG_RUNTIME_DIR") or paths.state_dir()) / "cronjovi-logged-in"


def fire_login(rules: list[Workflow], fire: Callable) -> None:
    """Once per session, however many times the engine restarts after edits."""
    marker = login_marker()
    done = set(marker.read_text().split()) if marker.exists() else set()
    for workflow in rules:
        if workflow.slug not in done:
            fire(workflow, "login", {})
            done.add(workflow.slug)
    marker.write_text("\n".join(sorted(done)))


def woke_up(line: str) -> bool:
    return "PrepareForSleep" in line and "false" in line


def watch_wake(rules: list[Workflow], fire: Callable, stop: threading.Event) -> None:
    proc = subprocess.Popen(
        ["stdbuf", "-oL", "gdbus", "monitor", "--system", "--dest", "org.freedesktop.login1",
         "--object-path", "/org/freedesktop/login1"],
        stdout=subprocess.PIPE, text=True, errors="replace",
    )
    threading.Thread(target=lambda: (stop.wait(), proc.terminate()), daemon=True).start()
    for line in proc.stdout:
        if woke_up(line):
            for workflow in rules:
                fire(workflow, "wake", {})


def webhook_tokens() -> dict:
    path = paths.state_dir() / "webhooks.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def webhook_token(slug: str) -> str:
    """Kept out of the workflow file, so sharing a workflow can't leak it."""
    tokens = webhook_tokens()
    if slug not in tokens:
        tokens[slug] = secrets.token_urlsafe(24)
        path = paths.state_dir() / "webhooks.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(tokens, handle)
    return tokens[slug]


def webhook_url(slug: str, port: int = WEBHOOK_PORT) -> str:
    return f"http://127.0.0.1:{port}/hook/{slug}/{webhook_token(slug)}"


def webhook_app(rules: list[Workflow], fire: Callable):
    from flask import Flask, jsonify, request

    app = Flask("cronjovi-webhook")
    app.config["MAX_CONTENT_LENGTH"] = MAX_WEBHOOK_BYTES
    by_slug = {w.slug: w for w in rules}

    @app.post("/hook/<slug>/<token>")
    def hook(slug, token):
        expected = webhook_tokens().get(slug, "")
        workflow = by_slug.get(slug)
        if not workflow or not expected or not hmac.compare_digest(token.encode(), expected.encode()):
            return jsonify(error="not found"), 404
        body = request.get_json(silent=True)
        text = request.get_data(as_text=True) if body is None else ""
        fire(workflow, "webhook", {"webhook": {"body": body if body is not None else text}})
        return jsonify(ok=True), 202

    return app


class Engine:
    def __init__(self, spawn: Callable = spawn_event, power_root=Path("/sys/class/power_supply")):
        self.spawn = spawn
        self.power_root = power_root
        self.stop = threading.Event()
        self.limiter = Limiter()

    def record_skip(self, workflow: Workflow, trigger: str, note: str) -> None:
        history = History()
        history.skip(workflow.slug, trigger, None, note)
        history.db.close()

    def fire(self, workflow: Workflow, trigger: str, variables: dict) -> None:
        allowed, report = self.limiter.allow(workflow.slug)
        if not allowed:
            if report:
                self.record_skip(workflow, trigger, f"more than {MAX_FIRES} triggers in a minute")
            return
        try:
            self.spawn(workflow, trigger, variables)
        except (OSError, subprocess.CalledProcessError) as err:
            logging.error("%s: could not start: %s", workflow.slug, err)

    def serve(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        workflows, errors = discover()
        for error in errors:
            logging.error(error)
        active = [w for w in workflows if w.enabled and w.trigger.has_events()]
        signal.signal(signal.SIGTERM, lambda *_: self.stop.set())
        signal.signal(signal.SIGINT, lambda *_: self.stop.set())

        watches = [FileWatch(w, self.fire) for w in active if w.trigger.file]
        if watches:
            _, problems = start_file_watches(watches)
            for workflow, problem in problems:
                self.record_skip(workflow, "file", problem)
        devices = [w for w in active if w.trigger.device]
        if devices:
            threading.Thread(target=watch_devices, args=(devices, self.fire, self.stop),
                             daemon=True).start()
        power = [w for w in active if w.trigger.battery or w.trigger.power]
        if power:
            threading.Thread(target=watch_power, args=(power, self.fire, self.stop, self.power_root),
                             daemon=True).start()
        logins = [w for w in active if w.trigger.login]
        if logins:
            fire_login(logins, self.fire)
        wakes = [w for w in active if w.trigger.wake]
        if wakes:
            threading.Thread(target=watch_wake, args=(wakes, self.fire, self.stop), daemon=True).start()
        hooks = [w for w in active if w.trigger.webhook]
        if hooks:
            threading.Thread(target=self._serve_webhooks, args=(hooks,), daemon=True).start()
        logging.info("Watching %d workflow(s)", len(active))
        self.stop.wait()

    def _serve_webhooks(self, hooks: list[Workflow]) -> None:
        from werkzeug.serving import make_server

        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        try:
            make_server("127.0.0.1", WEBHOOK_PORT, webhook_app(hooks, self.fire),
                        threaded=True).serve_forever()
        except OSError as err:
            for workflow in hooks:
                self.record_skip(workflow, "webhook", f"Webhook port {WEBHOOK_PORT}: {err}")
