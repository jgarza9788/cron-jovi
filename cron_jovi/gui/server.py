"""The local API behind the app window.

This process can run arbitrary commands, so it must never be reachable by
anything but the window that started it: it binds to 127.0.0.1 only, checks the
Host header (against DNS rebinding) and requires a per-launch token on every
API call. A web page can't send the token header without a CORS preflight,
which this server never approves.
"""

import hmac
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, send_from_directory

from .. import daemon, doctor, gallery, hotkeys, paths, schedule, settings, store
from ..action_api import describe, load_actions
from ..engine import is_running, stop_run
from ..history import History
from ..workflow import WorkflowError, discover, load, parse, validate_steps
from . import theme

HERE = Path(__file__).parent
PACKAGE_MANAGERS = (
    ("omarchy", "omarchy pkg add {pkg}"),
    ("pacman", "sudo pacman -S {pkg}"),
    ("apt", "sudo apt install {pkg}"),
    ("dnf", "sudo dnf install {pkg}"),
    ("zypper", "sudo zypper install {pkg}"),
)
PACKAGES = {"wl-copy": "wl-clipboard", "wl-paste": "wl-clipboard", "notify-send": "libnotify",
            "xdg-open": "xdg-utils", "omarchy-shell": "mako"}


class LiveRun:
    """A run started from the app, with its output kept for the log pane."""

    def __init__(self, args: list[str]):
        self.id = uuid.uuid4().hex
        self.lines: list[str] = []
        self.code: int | None = None
        # Its own session: closing the window must not kill a running backup.
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "cron_jovi", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.append(line.rstrip("\n"))
        self.code = self.proc.wait()


def install_hint(tool: str) -> str:
    package = PACKAGES.get(tool, tool)
    for manager, template in PACKAGE_MANAGERS:
        if shutil.which(manager):
            return template.format(pkg=package)
    return f"Install {package} with your package manager"


NEXT_TICKS: dict[str, float] = {}  # stays right until the tick passes, so no need to re-ask systemd


def next_run(workflow) -> float | None:
    spec = workflow.trigger.schedule
    if not workflow.enabled or not spec:
        return None
    now = time.time()
    if NEXT_TICKS.get(spec, 0) > now:
        return NEXT_TICKS[spec]
    try:
        NEXT_TICKS[spec] = schedule.next_ticks(spec, now)[0]
    except (WorkflowError, IndexError):
        return None
    return NEXT_TICKS[spec]


def summary(workflow, history: History) -> dict:
    last = history.recent(workflow.slug, 1)
    return {
        "slug": workflow.slug,
        "stamp": store.stamp(workflow.slug) if store.path_for(workflow.slug).exists() else "",
        "name": workflow.name,
        "description": workflow.description,
        "enabled": workflow.enabled,
        "favorite": workflow.favorite,
        "icon": workflow.icon,
        "color": workflow.color,
        "folder": workflow.folder,
        "hotkey": workflow.trigger.hotkey,
        "schedule": workflow.trigger.schedule,
        "login": workflow.trigger.login,
        "wake": workflow.trigger.wake,
        "file": workflow.trigger.file,
        "device": workflow.trigger.device,
        "battery": workflow.trigger.battery,
        "power": workflow.trigger.power,
        "webhook": workflow.trigger.webhook,
        "actions": workflow.action_count(),
        "running": is_running(workflow.slug),
        "next_run": next_run(workflow),
        "last_run": {k: last[0][k] for k in last[0].keys() if k != "output"} if last else None,
    }


def status() -> dict:
    tools = [{"tool": tool, "found": found, "actions": actions,
              "hint": "" if found else install_hint(tool.split(" or ")[0])}
             for tool, found, actions in doctor.tool_report()]
    links = [{"name": a.name, "linked": a.linked()} for a in hotkeys.active()]
    return {
        "session": doctor.compositor(),
        "tools": tools,
        "timers_active": doctor.timers_active(),
        "timers_total": len(schedule.installed_timers()),
        "hotkey_links": links,
        "engine": daemon.engine_state(),
        "paused": settings.load()["paused"],
        "has_battery": bool(daemon.system_batteries(Path("/sys/class/power_supply"))),
    }


def templates() -> list[dict]:
    found = []
    for path in sorted((HERE / "templates").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        found.append({
            "id": path.stem,
            "blurb": data.pop("blurb", ""),
            "workflow": data,
        })
    return found


def create_app(token: str, port_holder: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.json.sort_keys = False  # a hand-written file keeps its order when the app saves it
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    live: dict[str, LiveRun] = {}

    def history() -> History:
        return History()

    @app.errorhandler(WorkflowError)
    def on_workflow_error(err):
        return jsonify(error=str(err)), 400

    @app.before_request
    def guard():
        port = (port_holder or {}).get("port")
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"} if port else None
        if allowed and request.host not in allowed:
            return jsonify(error="forbidden host"), 403
        if request.path.startswith("/api/"):
            supplied = request.headers.get("X-CronJovi-Token", "")
            if not hmac.compare_digest(supplied, token):
                return jsonify(error="forbidden"), 403
        return None

    @app.after_request
    def harden(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return send_from_directory(HERE / "static", "index.html")

    @app.get("/static/<path:name>")
    def static_file(name):
        return send_from_directory(HERE / "static", name)

    @app.get("/api/state")
    def api_state():
        workflows, errors = discover()
        db = history()
        return jsonify(
            workflows=[summary(w, db) for w in workflows],
            errors=errors,
            status=status(),
        )

    @app.get("/api/theme")
    def api_theme():
        return jsonify(theme.load())

    @app.get("/api/actions")
    def api_actions():
        return jsonify([describe(d) for _, d in sorted(load_actions().items())])

    @app.get("/api/templates")
    def api_templates():
        return jsonify(templates())

    @app.post("/api/workflows")
    def api_create():
        workflow = store.create(request.get_json())
        report = store.sync()
        return jsonify(slug=workflow.slug, messages=report.messages + report.problems), 201

    @app.get("/api/workflows/<slug>")
    def api_read(slug):
        path = store.path_for(slug)
        data = store.read_raw(slug)
        workflow = load(path)
        return jsonify(data=data, yaml=path.read_text(), stamp=store.stamp(slug),
                       summary=summary(workflow, history()))

    def changed_elsewhere(slug):
        expected = request.headers.get("If-Match")
        return expected and store.path_for(slug).exists() and expected != store.stamp(slug)

    @app.put("/api/workflows/<slug>")
    def api_save(slug):
        if changed_elsewhere(slug):
            return jsonify(error="changed", changed=True), 409
        store.save(slug, request.get_json())
        report = store.sync()
        return jsonify(stamp=store.stamp(slug), messages=report.messages + report.problems)

    @app.put("/api/workflows/<slug>/yaml")
    def api_save_yaml(slug):
        if changed_elsewhere(slug):
            return jsonify(error="changed", changed=True), 409
        store.save_yaml(slug, request.get_json()["yaml"])
        report = store.sync()
        return jsonify(stamp=store.stamp(slug), messages=report.messages + report.problems)

    @app.delete("/api/workflows/<slug>")
    def api_delete(slug):
        store.delete(slug)
        store.sync()
        return jsonify(ok=True)

    @app.post("/api/workflows/<slug>/run")
    def api_run(slug):
        load(store.path_for(slug))  # refuse a broken file before spawning
        paths.progress_file(slug).unlink(missing_ok=True)  # no flash of the previous run's marks
        run = LiveRun(["run", slug])
        live[run.id] = run
        return jsonify(id=run.id), 202

    @app.post("/api/test-step")
    def api_test_step():
        step = request.get_json()
        validate_steps([step])
        run = LiveRun(["step", json.dumps(step)])
        live[run.id] = run
        return jsonify(id=run.id), 202

    @app.post("/api/workflows/<slug>/export")
    def api_export(slug):
        risky = store.secrets_in(store.read_raw(slug))
        if risky and not request.get_json(silent=True, force=True).get("confirmed"):
            return jsonify(secrets=risky)
        return jsonify(path=str(store.export(slug, Path.home() / "Downloads")))

    @app.get("/api/workflows/<slug>/progress")
    def api_progress(slug):
        store.path_for(slug)
        try:
            steps = json.loads(paths.progress_file(slug).read_text())
        except (OSError, ValueError):
            steps = {}
        return jsonify(running=is_running(slug), steps=steps)

    @app.post("/api/workflows/<slug>/stop")
    def api_stop_workflow(slug):
        store.path_for(slug)
        return jsonify(stopped=stop_run(slug))

    @app.delete("/api/history")
    def api_history_clear():
        history().clear(request.args.get("workflow") or None)
        return jsonify(ok=True)

    @app.get("/api/live/<run_id>")
    def api_live(run_id):
        run = live.get(run_id)
        if run is None:
            return jsonify(error="unknown run"), 404
        start = request.args.get("from", 0, type=int)
        return jsonify(lines=run.lines[start:], done=run.code is not None, code=run.code)

    @app.post("/api/live/<run_id>/stop")
    def api_stop(run_id):
        run = live.get(run_id)
        if run is None:
            return jsonify(error="unknown run"), 404
        if run.code is None:
            os.kill(run.proc.pid, signal.SIGTERM)
        return jsonify(ok=True)

    @app.get("/api/history")
    def api_history():
        slug = request.args.get("workflow") or None
        limit = min(request.args.get("limit", 50, type=int), 500)
        rows = history().recent(slug, limit)
        return jsonify([{k: r[k] for k in r.keys() if k != "output"} for r in rows])

    @app.get("/api/history/<int:run_id>")
    def api_history_row(run_id):
        row = history().get(run_id)
        if row is None:
            return jsonify(error="unknown run"), 404
        return jsonify(dict(row))

    @app.post("/api/schedule/preview")
    def api_schedule_preview():
        spec = request.get_json().get("schedule", "")
        return jsonify(next=schedule.next_ticks(spec, time.time(), 3))

    @app.post("/api/hotkey/check")
    def api_hotkey_check():
        combo = request.get_json().get("hotkey", "")
        slug = request.get_json().get("slug")
        hotkeys.parse(combo)
        workflow = parse(
            {"name": "This workflow", "steps": [], "trigger": {"hotkey": combo}},
            paths.workflows_dir() / "x.yaml",
        )
        conflicts = hotkeys.hyprland_conflicts([workflow])
        others, _ = discover()
        conflicts += [f"{w.name} uses this hotkey" for w in others
                      if w.slug != slug and w.trigger.hotkey
                      and hotkeys.same(w.trigger.hotkey, combo)]
        return jsonify(conflicts=conflicts)

    @app.get("/api/settings")
    def api_settings():
        return jsonify(settings.load())

    @app.put("/api/settings")
    def api_settings_save():
        settings.update(**request.get_json())
        store.sync()
        return jsonify(settings.load())

    @app.get("/api/welcome")
    def api_welcome():
        return jsonify(seen=(paths.state_dir() / "welcomed").exists())

    @app.post("/api/welcome")
    def api_welcomed():
        (paths.state_dir() / "welcomed").parent.mkdir(parents=True, exist_ok=True)
        (paths.state_dir() / "welcomed").touch()
        return jsonify(ok=True)

    @app.get("/api/webhook/<slug>")
    def api_webhook(slug):
        store.path_for(slug)
        return jsonify(url=daemon.webhook_url(slug))

    @app.post("/api/hotkeys/link")
    def api_link_hotkeys():
        report = store.sync(link_config=True)
        return jsonify(messages=report.messages + report.problems)

    @app.post("/api/import/review")
    def api_import_review():
        """Describe a shared workflow without saving or running anything."""
        try:
            data = yaml.safe_load(request.get_json().get("yaml", ""))
        except yaml.YAMLError as err:
            raise WorkflowError(f"That file isn't valid YAML: {err}") from None
        workflow = parse(data, paths.workflows_dir() / "import.yaml")
        return jsonify(
            name=workflow.name,
            description=workflow.description,
            actions=workflow.action_count(),
            trigger=workflow.trigger.describe(),
            commands=store.shell_commands(workflow.steps + workflow.on_failure),
            effects=store.effects(workflow.steps + workflow.on_failure),
        )

    @app.post("/api/import")
    def api_import():
        data = yaml.safe_load(request.get_json().get("yaml", ""))
        if isinstance(data, dict):
            data["enabled"] = False  # imports never start firing on their own
        workflow = store.create(data)
        return jsonify(slug=workflow.slug), 201

    @app.get("/api/galleries")
    def api_galleries():
        found = []
        for item in gallery.sources():
            try:
                found.append({**item, "items": gallery.items(item["id"])})
            except OSError as err:
                found.append({**item, "items": [], "error": str(err)})
        return jsonify(found)

    @app.post("/api/galleries")
    def api_gallery_add():
        return jsonify(gallery.add(request.get_json().get("source", ""))), 201

    @app.delete("/api/galleries/<gallery_id>")
    def api_gallery_remove(gallery_id):
        gallery.remove(gallery_id)
        return jsonify(ok=True)

    @app.post("/api/galleries/<gallery_id>/update")
    def api_gallery_update(gallery_id):
        gallery.update(gallery_id)
        return jsonify(ok=True)

    @app.get("/api/galleries/<gallery_id>/item")
    def api_gallery_item(gallery_id):
        return jsonify(yaml=gallery.read_item(gallery_id, request.args.get("file", "")))

    return app
