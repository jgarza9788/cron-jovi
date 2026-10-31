"""Cron Jovi: Shortcuts-style automation for the Linux desktop."""

import argparse
import json
import re
import sys
import time
from datetime import datetime


from . import __codename__, __version__, daemon, doctor, gallery, hotkeys, paths, schedule, settings, store
from . import explain as explain_module
from .action_api import load_actions
from .engine import run_single_step, run_workflow
from .history import History
from .workflow import WorkflowError, discover, find, slugify, validate_steps

HIDDEN = {"daemon", "step", "teardown", "tick"}
COMPLETION = """\
_cronjovi() {{
    local names="{names}"
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$names" -- "${{COMP_WORDS[1]}}"))
    elif [[ " run logs enable disable webhook " == *" ${{COMP_WORDS[1]}} "* ]]; then
        local folder="${{XDG_CONFIG_HOME:-$HOME/.config}}/cronjovi/workflows"
        COMPREPLY=($(compgen -W "$(ls "$folder" 2>/dev/null | sed 's/\\.ya\\?ml$//')" -- "${{COMP_WORDS[COMP_CWORD]}}"))
    fi
}}
complete -F _cronjovi cronjovi"""

TEMPLATE = """\
name: {name}
description: ""
{trigger}steps:
  - action: notify
    text: Hello from {name}
"""


def stamp(epoch: float | None) -> str:
    if epoch is None:
        return "-"
    return datetime.fromtimestamp(epoch).strftime("%a %b %d %H:%M:%S")


def took(row) -> str:
    if not row["started_at"] or not row["finished_at"]:
        return "-"
    seconds = row["finished_at"] - row["started_at"]
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} m" if hours else f"{minutes} m {seconds} s"


def result(row) -> str:
    if row["status"] == "failed":
        return f"failed (exit {row['exit_code']})"
    if row["status"] == "skipped":
        return "skipped"
    return row["status"]


def table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [max(len(str(row[i])) for row in [headers, *rows]) for i in range(len(headers))]
    for row in [headers, *rows]:
        print("  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)).rstrip())


def cmd_run(args) -> int:
    workflow = find(args.name)
    scheduled = float(args.scheduled_for) if args.scheduled_for else None

    def echo(line: str) -> None:
        # The GUI may close while a run carries on without it.
        try:
            print(line, flush=True)
        except BrokenPipeError:
            pass

    variables = json.loads(args.vars_json) if args.vars_json else {}
    for pair in args.var:
        key, _, value = pair.partition("=")
        variables[key] = value
    return run_workflow(
        workflow, History(), args.trigger, scheduled, args.note or "", echo, variables
    )


def cmd_list(args) -> int:
    workflows, errors = discover()
    history = History()
    rows = []
    for wf in workflows:
        last = history.recent(wf.slug, 1)
        rows.append([
            wf.slug,
            wf.trigger.describe(),
            wf.action_count(),
            "yes" if wf.enabled else "no",
            f"{result(last[0])}, {stamp(last[0]['started_at'] or last[0]['scheduled_at'])}"
            if last else "never",
        ])
    if rows:
        table(["WORKFLOW", "TRIGGER", "STEPS", "ENABLED", "LAST RUN"], rows)
    else:
        print(f"No workflows in {paths.workflows_dir()}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


def cmd_new(args) -> int:
    folder = paths.workflows_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slugify(args.name)}.yaml"
    if path.exists():
        print(f"error: {path} already exists", file=sys.stderr)
        return 1
    trigger = ""
    if args.hotkey or args.schedule:
        trigger = "trigger:\n"
        if args.hotkey:
            trigger += f"  hotkey: {args.hotkey}\n"
        if args.schedule:
            trigger += f'  schedule: "{args.schedule}"\n  if_missed: run_once\n  if_running: skip\n'
    path.write_text(TEMPLATE.format(name=args.name, trigger=trigger))
    print(path)
    return 0


def cmd_logs(args) -> int:
    history = History()
    if args.run:
        row = history.get(args.run)
        if not row:
            print(f"error: no run {args.run}", file=sys.stderr)
            return 1
        print(f"{row['workflow']}: {result(row)}" + (f" · {row['note']}" if row["note"] else ""))
        print(f"scheduled {stamp(row['scheduled_at'])} · started {stamp(row['started_at'])}"
              f" · finished {stamp(row['finished_at'])}")
        if row["output"]:
            print(f"\n{row['output']}")
        return 0
    slug = find(args.name).slug if args.name else None
    rows = history.recent(slug, args.limit)
    if args.json:
        print(json.dumps([dict(row) for row in rows], indent=2))
        return 0
    if not rows:
        print("No runs yet")
        return 0
    table(
        ["RUN", "WORKFLOW", "SCHEDULED", "STARTED", "TOOK", "RESULT", "NOTE"],
        [[row["id"], row["workflow"], stamp(row["scheduled_at"]),
          stamp(row["started_at"]) if row["started_at"] else "not started",
          took(row), result(row), row["note"]] for row in rows],
    )
    return 0


def cmd_sync(args) -> int:
    report = store.sync(args.link_hotkeys)
    for line in [*report.errors, *report.problems, *report.messages]:
        print(line, file=sys.stderr)
    print(f"Synced {report.timers} timer(s) and {report.hotkeys} hotkey(s)")
    return 1 if report.errors or report.problems else 0


def cmd_validate(args) -> int:
    workflows, errors = discover()
    for workflow in workflows:
        try:
            if workflow.trigger.schedule:
                schedule.next_ticks(workflow.trigger.schedule, time.time())
            if workflow.trigger.hotkey:
                hotkeys.parse(workflow.trigger.hotkey)
            print(f"ok      {workflow.slug}")
        except WorkflowError as err:
            errors.append(f"{workflow.path.name}: {err}")
    for error in errors:
        print(f"error   {error}")
    return 1 if errors else 0


def cmd_actions(args) -> int:
    rows = []
    for name, defn in sorted(load_actions().items()):
        options = ", ".join(
            key if key in defn.required() else f"[{key}]" for key in defn.hints()
        )
        rows.append([name, options])
    table(["ACTION", "OPTIONS"], rows)
    return 0


def cmd_doctor(args) -> int:
    print("\n".join(doctor.report()))
    return 0


def cmd_gui(args) -> int:
    try:
        from .gui.app import launch
    except ImportError as err:
        print(f"error: the GUI needs Flask ({err}); re-run install.sh", file=sys.stderr)
        return 1
    return launch(browser=args.browser, no_open=args.no_open)


def cmd_step(args) -> int:
    step = json.loads(args.step_json)
    validate_steps([step])
    return run_single_step(step, lambda line: print(line, flush=True))


def cmd_enabled(args) -> int:
    workflow = find(args.name)
    store.set_enabled(workflow.slug, args.command == "enable")
    report = store.sync()
    for line in [*report.problems, *report.messages]:
        print(line, file=sys.stderr)
    print(f"{workflow.name} is {'on' if args.command == 'enable' else 'off'}")
    return 1 if report.problems else 0


def cmd_errors(args) -> int:
    """Failures the table couldn't translate, so it can grow from real use."""
    rows = [r for r in History().recent(None, 500) if explain_module.UNKNOWN_MARK in r["note"]]
    if not rows:
        print("Every recent failure had a plain-language translation.")
        return 0
    for row in rows:
        lines = [ln for ln in row["output"].splitlines()
                 if not ln.startswith("$ ") and not re.match(r"\d\d:\d\d:\d\d ", ln)]
        print(f"{row['workflow']} (exit {row['exit_code']}): {lines[-1] if lines else 'no output'}")
    print(f"\nAdd these to {paths.config_home() / 'cronjovi' / 'errors.yaml'}")
    return 0


def cmd_pause(args) -> int:
    settings.update(paused=args.command == "pause")
    report = store.sync()
    for line in report.problems:
        print(line, file=sys.stderr)
    print("Paused: no trigger will run" if args.command == "pause" else "Resumed")
    return 1 if report.problems else 0


def cmd_completion(args) -> int:
    names = " ".join(sorted(c for c in parser()._subparsers._group_actions[0].choices
                            if c not in HIDDEN))
    print(COMPLETION.format(names=names))
    return 0


def cmd_gallery(args) -> int:
    if args.action == "add":
        entry = gallery.add(args.target or "")
        print(f"Added {entry['source']}")
        return 0
    if args.action == "remove":
        gallery.remove(args.target or "")
        return 0
    if args.action == "update":
        for item in gallery.sources():
            gallery.update(item["id"])
        return 0
    if args.action == "install":
        gallery_id, _, name = (args.target or "").partition(":")
        text = gallery.read_item(gallery_id, name)
        print(text)
        data = store.parse_shared(text)
        commands = store.shell_commands((data.get("steps") or []) + (data.get("on_failure") or []))
        if commands and not args.yes:
            print("This runs commands on your computer. Read it, then add --yes.", file=sys.stderr)
            return 1
        print(f"Added {gallery.install(gallery_id, name)}, switched off")
        return 0
    for item in gallery.sources():
        print(f"{item['id']}  {item['source']}")
        for entry in gallery.items(item["id"]):
            state = entry["trigger"] if entry["ok"] else f"unusable: {entry['error']}"
            print(f"  {item['id']}:{entry['file']}  {entry['name']}  ({state})")
    return 0


def cmd_webhook(args) -> int:
    workflow = find(args.name)
    if not workflow.trigger.webhook:
        print(f"error: {workflow.name} has no webhook trigger", file=sys.stderr)
        return 1
    print(daemon.webhook_url(workflow.slug))
    return 0


def cmd_daemon(args) -> int:
    daemon.Engine().serve()
    return 0


def cmd_tick(args) -> int:
    workflow = find(args.name)
    if not workflow.enabled or not workflow.trigger.schedule:
        return 0
    print(f"{workflow.slug}: {schedule.tick(workflow, History())}")
    return 0


def cmd_teardown(args) -> int:
    daemon.remove_engine()
    schedule.remove_all()
    hotkeys.remove_all()
    return 0


def parser() -> argparse.ArgumentParser:
    main_parser = argparse.ArgumentParser(prog="cronjovi", description=__doc__)
    main_parser.add_argument("--version", action="version", version=f"cronjovi {__version__} ({__codename__})")
    sub = main_parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run = sub.add_parser("run", help="run a workflow now")
    run.add_argument("name")
    run.add_argument("--var", action="append", default=[], metavar="NAME=VALUE",
                     help="set a variable for this run")
    run.add_argument("--vars-json", help=argparse.SUPPRESS)
    run.add_argument("--trigger", default="manual", help=argparse.SUPPRESS)
    run.add_argument("--scheduled-for", help=argparse.SUPPRESS)
    run.add_argument("--note", help=argparse.SUPPRESS)
    run.set_defaults(func=cmd_run)

    sub.add_parser("list", help="list workflows").set_defaults(func=cmd_list)

    new = sub.add_parser("new", help="create a workflow file")
    new.add_argument("name")
    new.add_argument("--hotkey", help="for example Super+Shift+F")
    new.add_argument("--schedule", help='for example "daily at 02:00" or "every 2h"')
    new.set_defaults(func=cmd_new)

    logs = sub.add_parser("logs", help="show run history")
    logs.add_argument("name", nargs="?")
    logs.add_argument("-n", "--limit", type=int, default=20)
    logs.add_argument("--run", type=int, help="show one run with its output")
    logs.add_argument("--json", action="store_true")
    logs.set_defaults(func=cmd_logs)

    sync = sub.add_parser("sync", help="apply workflow triggers to systemd and the compositor")
    sync.add_argument("--link-hotkeys", action="store_true",
                      help="add the generated bindings to your compositor config")
    sync.set_defaults(func=cmd_sync)

    gui = sub.add_parser("gui", help="open the app window")
    gui.add_argument("--browser", action="store_true", help="open in your browser instead")
    gui.add_argument("--no-open", action="store_true", help="only print the address")
    gui.set_defaults(func=cmd_gui)

    for name, text in (("enable", "switch a workflow on"), ("disable", "switch a workflow off")):
        toggle = sub.add_parser(name, help=text)
        toggle.add_argument("name")
        toggle.set_defaults(func=cmd_enabled)

    sub.add_parser("errors", help="list failures with no plain translation").set_defaults(func=cmd_errors)
    sub.add_parser("pause", help="stop every trigger until you resume").set_defaults(func=cmd_pause)
    sub.add_parser("resume", help="turn triggers back on").set_defaults(func=cmd_pause)
    sub.add_parser("completion", help="print bash tab completion").set_defaults(func=cmd_completion)

    step = sub.add_parser("step")
    step.add_argument("step_json")
    step.set_defaults(func=cmd_step)

    shared = sub.add_parser("gallery", help="browse a folder or git repo of shared workflows")
    shared.add_argument("action", nargs="?", default="list",
                        choices=("list", "add", "remove", "update", "install"))
    shared.add_argument("target", nargs="?", help="folder, git address, id, or id:file")
    shared.add_argument("--yes", action="store_true", help="install after reading it")
    shared.set_defaults(func=cmd_gallery)

    webhook = sub.add_parser("webhook", help="print a workflow's webhook address")
    webhook.add_argument("name")
    webhook.set_defaults(func=cmd_webhook)

    sub.add_parser("validate", help="check every workflow file").set_defaults(func=cmd_validate)
    sub.add_parser("actions", help="list available actions").set_defaults(func=cmd_actions)
    sub.add_parser("doctor", help="report which Linux tools are installed").set_defaults(
        func=cmd_doctor)

    sub.add_parser("daemon").set_defaults(func=cmd_daemon)
    sub.add_parser("tick").add_argument("name")
    sub.choices["tick"].set_defaults(func=cmd_tick)
    sub.add_parser("teardown").set_defaults(func=cmd_teardown)
    return main_parser


def main() -> int:
    args = parser().parse_args()
    try:
        return args.func(args)
    except WorkflowError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
