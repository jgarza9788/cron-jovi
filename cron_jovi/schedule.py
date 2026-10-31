"""Schedules: systemd timers fire, this module decides what the tick means.

Every timer is Persistent, so systemd fires once when the machine comes back
however many ticks it slept through. That is the "several missed ticks still
mean one run" guarantee. `next_due` in history tells on-time from late without
needing a sleep signal from logind: if the tick we were waiting for is well in
the past, the machine wasn't there for it.
"""

import calendar
import re
import subprocess
import time
from typing import Callable

from . import paths
from .history import History
from .workflow import Workflow, WorkflowError

LATE_AFTER = 120  # seconds past the tick before a run counts as late
BATCH = 500
# On a UTC system there is no separate "(in UTC)" line, so match any line ending in UTC.
UTC_LINE = re.compile(r": \w+ (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) UTC$", re.M)

TICK_UNIT = "cronjovi-tick@.service"
TICK_SERVICE = """\
[Unit]
Description=Cron Jovi schedule tick for %i

[Service]
Type=oneshot
ExecStart={command} tick %i
"""
TIMER = """\
[Unit]
Description=Cron Jovi: {name}

[Timer]
OnCalendar={calendar}
Persistent=true
AccuracySec=1s
Unit=cronjovi-tick@{slug}.service

[Install]
WantedBy=timers.target
"""


def to_calendar(spec: str) -> str:
    """Friendly forms like `daily at 02:00` or `every 2h`, else OnCalendar."""
    text = spec.strip()
    if match := re.fullmatch(r"daily at (\d{1,2}):(\d\d)", text, re.I):
        return f"*-*-* {int(match[1]):02}:{match[2]}:00"
    if match := re.fullmatch(r"weekdays at (\d{1,2}):(\d\d)", text, re.I):
        return f"Mon..Fri *-*-* {int(match[1]):02}:{match[2]}:00"
    if match := re.fullmatch(r"weekly on (\w{3}) at (\d{1,2}):(\d\d)", text, re.I):
        return f"{match[1].title()} *-*-* {int(match[2]):02}:{match[3]}:00"
    if match := re.fullmatch(r"every (\d+) ?(m|min|minutes?)", text, re.I):
        return f"*:00/{match[1]}"
    if match := re.fullmatch(r"every (\d+) ?(h|hours?)", text, re.I):
        return f"00/{match[1]}:00"
    return text


def next_ticks(spec: str, base: float, count: int = 1) -> list[float]:
    """The next `count` ticks strictly after `base`, as epoch seconds."""
    proc = subprocess.run(
        [
            "systemd-analyze", "calendar", f"--iterations={count}",
            f"--base-time=@{int(base)}", "--", to_calendar(spec),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        raise WorkflowError(f"'{spec}' isn't a schedule Cron Jovi understands")
    return [
        float(calendar.timegm(time.strptime(stamp, "%Y-%m-%d %H:%M:%S")))
        for stamp in UTC_LINE.findall(proc.stdout)
    ]


def ticks_since(spec: str, first: float, now: float) -> list[float]:
    """Every tick from `first` through `now`."""
    ticks = [first]
    while True:
        batch = next_ticks(spec, ticks[-1], BATCH)
        ticks += [tick for tick in batch if tick <= now]
        if not batch or batch[-1] > now:
            return ticks


def spawn_run(workflow: Workflow, scheduled_at: float, note: str) -> None:
    """Start the real run outside the tick unit.

    systemd drops a timer tick while its unit is active, which would lose the
    "skipped: previous run still active" row. So the tick unit exits at once.
    """
    subprocess.run(
        [
            "systemd-run", "--user", "--collect", "--quiet",
            f"--unit=cronjovi-job-{workflow.slug}-{int(scheduled_at)}",
            f"--description=Cron Jovi: {workflow.name}",
            *paths.self_command(), "run", workflow.slug,
            "--trigger", "schedule", "--scheduled-for", str(scheduled_at), "--note", note,
        ],
        check=True,
    )


def tick(
    workflow: Workflow,
    history: History,
    now: float | None = None,
    spawn: Callable[[Workflow, float, str], None] = spawn_run,
) -> str:
    """Handle one timer firing. Returns what happened, for logs and tests."""
    now = time.time() if now is None else now
    spec = workflow.trigger.schedule
    due = history.next_due(workflow.slug, spec)
    if due is None or now < due:
        # Persistent timers catch up right after install or enable, when no
        # tick we know about is owed.
        history.set_next_due(workflow.slug, spec, due or next_ticks(spec, now)[0])
        return "nothing due"

    ticks = ticks_since(spec, due, now)
    latest = ticks[-1]
    history.set_next_due(workflow.slug, spec, next_ticks(spec, now)[0])
    late = now - latest > LATE_AFTER

    if late and workflow.trigger.if_missed == "skip":
        history.skip(workflow.slug, "schedule", latest, "machine was off")
        return "skipped"
    note = ""
    if late:
        note = "Ran late: machine was asleep or off"
        if len(ticks) > 1:
            note += f" ({len(ticks)} ticks missed)"
    spawn(workflow, latest, note)
    return "late" if late else "on time"


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def timer_name(slug: str) -> str:
    return f"cronjovi-{slug}.timer"


def installed_timers() -> list:
    return sorted(paths.systemd_user_dir().glob("cronjovi-*.timer"))


def sync_timers(workflows: list[Workflow], history: History) -> list[str]:
    """Make the user's timers match the enabled scheduled workflows."""
    unit_dir = paths.systemd_user_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / TICK_UNIT).write_text(TICK_SERVICE.format(command=" ".join(paths.self_command())))

    wanted = {w.slug: w for w in workflows if w.enabled and w.trigger.schedule}
    for slug, workflow in wanted.items():
        spec = workflow.trigger.schedule
        first = next_ticks(spec, time.time())[0]
        if history.next_due(slug, spec) is None:
            history.set_next_due(slug, spec, first)
        text = TIMER.format(
            name=workflow.name.replace("%", "%%"),
            calendar=to_calendar(spec).replace("%", "%%"),
            slug=slug,
        )
        (unit_dir / timer_name(slug)).write_text(text)

    for path in installed_timers():
        slug = path.stem.removeprefix("cronjovi-")
        if slug not in wanted:
            _systemctl("disable", "--now", path.name)
            path.unlink()
            history.forget_schedule(slug)

    _systemctl("daemon-reload")
    problems = []
    for slug in wanted:
        result = _systemctl("enable", "--now", timer_name(slug))
        if result.returncode:
            problems.append(f"{timer_name(slug)}: {result.stderr.strip()}")
    return problems


def remove_all() -> None:
    for path in installed_timers():
        _systemctl("disable", "--now", path.name)
        path.unlink()
    (paths.systemd_user_dir() / TICK_UNIT).unlink(missing_ok=True)
    for stamp in paths.timer_stamp_dir().glob("stamp-cronjovi-*.timer"):
        stamp.unlink()
    _systemctl("daemon-reload")
