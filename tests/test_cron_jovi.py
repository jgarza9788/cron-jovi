import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cron_jovi import conditions, hotkeys, paths, schedule, settings, store  # noqa: E402
from cron_jovi.action_api import ActionError, Duration, load_actions  # noqa: E402
from cron_jovi.engine import Context, is_running, run_single_step, run_workflow, stop_run, tell_user  # noqa: E402
from cron_jovi.history import History  # noqa: E402
from cron_jovi.workflow import Trigger, Workflow, WorkflowError, load  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for var, sub in (("XDG_STATE_HOME", "state"), ("XDG_CONFIG_HOME", "config"),
                         ("XDG_DATA_HOME", "data")):
            old = os.environ.get(var)
            os.environ[var] = str(self.root / sub)
            self.addCleanup(lambda v=var, o=old: os.environ.__setitem__(v, o) if o
                            else os.environ.pop(v, None))
        self.folder = self.root / "config/cronjovi/workflows"
        self.folder.mkdir(parents=True)
        self.history = History()
        self.addCleanup(self.history.db.close)

    def workflow(self, body: str, slug="demo") -> Workflow:
        path = self.folder / f"{slug}.yaml"
        path.write_text(textwrap.dedent(body))
        return load(path)

    def shell_wf(self, *commands, **extra) -> Workflow:
        steps = [{"action": "shell", "run": c, **extra} for c in commands]
        return Workflow("demo", "Demo", self.folder / "demo.yaml", steps=steps)

    def last(self):
        return self.history.recent("demo", 1)[0]


class LoadingTests(Base):
    def test_design_doc_sample_loads(self):
        wf = self.workflow("""
            name: Focus Mode
            trigger:
              hotkey: Super+Shift+F
            steps:
              - action: dnd
                state: on
              - action: media
                command: pause
                players: all
              - action: shell
                run: niri msg action focus-workspace 3
                timeout: 10s
                stop_on_error: true
              - if:
                  time_of_day: { after: "18:00" }
                then:
                  - action: brightness
                    percent: 40
                else:
                  - action: brightness
                    percent: 70
              - action: notify
                text: Focus mode on
            """)
        self.assertEqual(wf.action_count(), 6)
        self.assertEqual(wf.trigger.if_missed, "run_once")
        self.assertEqual(wf.trigger.if_running, "skip")

    def test_repo_examples_load_and_are_disabled(self):
        for path in (REPO / "workflows").glob("*.yaml"):
            self.assertFalse(load(path).enabled, path.name)

    def assertRejected(self, body, message):
        with self.assertRaisesRegex(WorkflowError, message):
            self.workflow(body)

    def test_rejects_bad_files(self):
        self.assertRejected("name: x\nsteps:\n  - action: nope\n", "unknown action")
        self.assertRejected("name: x\nsteps:\n  - action: notify\n", "missing option 'text'")
        self.assertRejected(
            "name: x\nsteps:\n  - action: notify\n    text: a\n    color: b\n", "unknown option")
        self.assertRejected(
            "name: x\nsteps:\n  - action: brightness\n    percent: lots\n", "not a number")
        self.assertRejected(
            "name: x\ntrigger:\n  if_running: maybe\nsteps: []\n", "if_running")
        self.assertRejected("name: x\nsteps: [{if: {moon: full}}]\n", "unknown condition")

    def test_templated_values_defer_type_checks(self):
        self.workflow("name: x\nsteps:\n  - action: brightness\n    percent: '{{ level }}'\n")

    def test_duration(self):
        self.assertEqual(Duration.parse("10s"), 10)
        self.assertEqual(Duration.parse("5m"), 300)
        self.assertEqual(Duration.parse("500ms"), 0.5)
        self.assertEqual(Duration.parse(3), 3)
        with self.assertRaises(ValueError):
            Duration.parse("soon")


class EngineTests(Base):
    def test_variables_flow_between_steps(self):
        wf = self.workflow("""
            name: x
            steps:
              - action: shell
                run: echo hello
                save_as: word
              - action: set
                name: copy
                value: "{{ word }} world"
              - action: shell
                run: echo {{ copy }}
            """)
        self.assertEqual(run_workflow(wf, self.history), 0)
        self.assertIn("hello world", self.last()["output"])

    def test_shell_variables_are_quoted(self):
        marker = self.root / "pwned"
        ctx = Context()
        ctx.vars["clip"] = f"; touch {marker}"
        load_actions()["shell"].func(ctx, "echo {{ clip }}")
        self.assertFalse(marker.exists())

    def test_undefined_variable_fails_the_run(self):
        code = run_workflow(self.shell_wf("echo {{ nope }}"), self.history)
        self.assertEqual(code, 1)
        self.assertIn("undefined variable", self.last()["output"])

    def test_failure_records_exit_code_and_output(self):
        code = run_workflow(self.shell_wf("echo boom >&2; exit 23"), self.history)
        row = self.last()
        self.assertEqual((code, row["status"], row["exit_code"]), (23, "failed", 23))
        self.assertIn("boom", row["output"])

    def test_failed_step_continues_but_run_still_fails(self):
        wf = self.shell_wf("exit 3", "echo after")
        self.assertEqual(run_workflow(wf, self.history), 3)
        self.assertIn("after", self.last()["output"])

    def test_stop_on_error_halts(self):
        wf = self.shell_wf("exit 3", "echo after", stop_on_error=True)
        self.assertEqual(run_workflow(wf, self.history), 3)
        self.assertNotIn("after", self.last()["output"].replace("$ echo after", ""))

    def test_on_failure_gets_the_error_and_keeps_the_exit_code(self):
        wf = self.shell_wf("exit 23")
        wf.on_failure = [{"action": "shell", "run": "echo caught {{ error }}"}]
        self.assertEqual(run_workflow(wf, self.history), 23)
        self.assertIn("caught", self.last()["output"])

    def test_timeout_kills_the_command(self):
        wf = self.shell_wf("sleep 30", timeout=0.2)
        started = time.monotonic()
        self.assertEqual(run_workflow(wf, self.history), 124)
        self.assertLess(time.monotonic() - started, 6)

    def test_if_else_and_repeat(self):
        wf = self.workflow("""
            name: x
            steps:
              - if:
                  equals: [a, b]
                then:
                  - action: shell
                    run: echo wrong-branch
                else:
                  - repeat: 2
                    steps:
                      - action: shell
                        run: echo pass-{{ index }}
              - repeat: [red, blue]
                steps:
                  - action: shell
                    run: echo item-{{ item }}
            """)
        run_workflow(wf, self.history)
        lines = self.last()["output"].splitlines()
        for expected in ("pass-1", "pass-2", "item-red", "item-blue"):
            self.assertIn(expected, lines)
        self.assertNotIn("wrong-branch", lines)

    def test_time_of_day(self):
        at = lambda h: datetime(2026, 1, 1, h)  # noqa: E731
        self.assertTrue(conditions.time_of_day({"after": "18:00"}, at(19)))
        self.assertFalse(conditions.time_of_day({"after": "18:00"}, at(17)))
        self.assertTrue(conditions.time_of_day({"after": "22:00", "before": "06:00"}, at(1)))
        self.assertFalse(conditions.time_of_day({"after": "22:00", "before": "06:00"}, at(12)))

    def test_file_action_reports_unwritable_destination(self):
        src = self.root / "a"
        src.write_text("x")
        wf = Workflow("demo", "Demo", self.folder / "demo.yaml", steps=[
            {"action": "file", "op": "copy", "src": str(src), "dest": str(self.root / "no/such/b")}
        ])
        self.assertEqual(run_workflow(wf, self.history), 1)


class SingleStepTests(Base):
    def run_step(self, step):
        lines = []
        return run_single_step(step, lines.append), lines

    def test_runs_and_reports(self):
        code, lines = self.run_step({"action": "shell", "run": "echo hi"})
        self.assertEqual(code, 0)
        self.assertIn("hi", lines)
        self.assertEqual(self.history.recent("demo"), [])

    def test_failure_returns_the_code(self):
        self.assertEqual(self.run_step({"action": "shell", "run": "exit 4"})[0], 4)

    def test_explains_values_from_earlier_steps(self):
        code, lines = self.run_step({"action": "shell", "run": "echo {{ clip }}"})
        self.assertEqual(code, 1)
        self.assertIn("earlier step", lines[-1])


class ActionTests(Base):
    def only(self, *tools):
        return mock.patch("shutil.which", lambda name: f"/usr/bin/{name}" if name in tools else None)

    def test_brightness_prefers_omarchy(self):
        from cron_jovi.actions import brightness
        with self.only("omarchy", "brightnessctl"):
            self.assertEqual(brightness.command(40)[:3], ["omarchy", "brightness", "display"])

    def test_brightness_never_touches_leds(self):
        from cron_jovi.action_api import ActionError
        from cron_jovi.actions import brightness
        with self.only("brightnessctl"), mock.patch("pathlib.Path.glob", return_value=iter(["x"])):
            self.assertIn("--class=backlight", brightness.command(40))
        with self.only("brightnessctl"), mock.patch("pathlib.Path.glob", return_value=iter([])):
            with self.assertRaisesRegex(ActionError, "no adjustable screen"):
                brightness.command(40)

    def test_brightness_falls_back_to_ddc(self):
        from cron_jovi.actions import brightness
        with self.only("ddcutil"), mock.patch("pathlib.Path.glob", return_value=iter([])):
            self.assertEqual(brightness.command(40), ["ddcutil", "setvcp", "10", "40"])

    def test_volume(self):
        from cron_jovi.actions import volume
        with self.only("wpctl"):
            self.assertEqual(volume.command("set", 30)[-1], "30%")
        with self.only("pamixer"):
            self.assertEqual(volume.command("mute", 0), ["pamixer", "--mute"])

    def test_text_changes(self):
        func = load_actions()["text"].func
        ctx = Context()
        self.assertEqual(func(ctx, "  hi  "), "hi")
        self.assertEqual(func(ctx, "hi", "uppercase"), "HI")
        self.assertEqual(func(ctx, "one\ntwo", "first-line"), "one")
        self.assertEqual(func(ctx, "a.b.c", "replace", ".", r"\1"), r"a\1b\1c")

    def test_every_action_has_a_friendly_face(self):
        for name, defn in load_actions().items():
            self.assertTrue(defn.title and defn.blurb and defn.icon != "zap", name)


class ProgressTests(Base):
    def seen(self):
        return json.loads(paths.progress_file("demo").read_text())

    def test_every_step_is_recorded_with_nested_paths(self):
        wf = self.workflow("""
            name: x
            steps:
              - action: shell
                run: "true"
              - if: {equals: [a, a]}
                then:
                  - action: shell
                    run: "true"
              - repeat: 2
                steps:
                  - action: shell
                    run: "true"
              - action: shell
                run: "true"
                skip: true
            """)
        run_workflow(wf, self.history)
        self.assertEqual(self.seen(), {
            "steps.0": "ok", "steps.1": "ok", "steps.1.then.0": "ok",
            "steps.2": "ok", "steps.2.steps.0": "ok",
        })

    def test_a_failed_step_and_on_failure(self):
        wf = self.shell_wf("exit 3", stop_on_error=True)
        wf.on_failure = [{"action": "shell", "run": "true"}]
        run_workflow(wf, self.history)
        self.assertEqual(self.seen(), {"steps.0": "failed", "on_failure.0": "ok"})

    def test_a_new_run_starts_clean(self):
        run_workflow(self.shell_wf("true", "true"), self.history)
        run_workflow(self.shell_wf("true"), self.history)
        self.assertEqual(self.seen(), {"steps.0": "ok"})

    def test_step_is_visible_while_it_runs(self):
        marks = []

        def spy(line):
            if line.startswith("$ "):
                marks.append(self.seen())

        run_workflow(self.shell_wf("true", "true"), self.history, echo=spy)
        self.assertEqual(marks, [{"steps.0": "running"}, {"steps.0": "ok", "steps.1": "running"}])

    def test_a_stopped_run_leaves_nothing_marked_running(self):
        mark = self.root / "started"
        (self.folder / "demo.yaml").write_text(
            f"name: Demo\nsteps:\n  - action: shell\n    run: touch {mark}; sleep 30\n")
        proc = subprocess.Popen([sys.executable, "-m", "cron_jovi", "run", "demo"], cwd=REPO,
                                stdout=subprocess.DEVNULL)
        self.addCleanup(proc.kill)
        deadline = time.monotonic() + 5
        while not mark.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.seen(), {"steps.0": "running"})
        proc.send_signal(signal.SIGTERM)
        proc.wait(5)
        self.assertEqual(self.seen(), {"steps.0": "stopped"})


class VariableTests(Base):
    def output(self, body):
        code = run_workflow(self.workflow(body), self.history)
        return code, self.last()["output"].splitlines()

    def test_repeat_count_from_a_variable(self):
        for value in ("5", "'5'"):
            code, lines = self.output(f"""
                name: x
                steps:
                  - action: set
                    name: num
                    value: {value}
                  - repeat: "{{{{ num }}}}"
                    steps:
                      - action: shell
                        run: echo pass-{{{{ index }}}}
                """)
            self.assertEqual(code, 0)
            self.assertEqual([ln for ln in lines if ln.startswith("pass-")], [f"pass-{i}" for i in range(1, 6)])
            self.assertIn("Repeat: 5 times", " ".join(lines))

    def test_repeat_splits_text(self):
        for source in ('"one,two,three"', '"one, two ,three,"'):
            _, lines = self.output(f"""
                name: x
                steps:
                  - repeat: {source}
                    split: ","
                    steps:
                      - action: shell
                        run: echo got-{{{{ item }}}}
                """)
            self.assertEqual([ln for ln in lines if ln.startswith("got-")], ["got-one", "got-two", "got-three"])

    def test_split_from_a_variable_with_other_separators(self):
        _, lines = self.output("""
            name: x
            steps:
              - action: set
                name: names
                value: a|b
              - repeat: "{{ names }}"
                split: "|"
                steps:
                  - action: shell
                    run: echo got-{{ item }}
            """)
        self.assertEqual([ln for ln in lines if ln.startswith("got-")], ["got-a", "got-b"])

    def test_digits_stay_text_when_splitting(self):
        _, lines = self.output("""
            name: x
            steps:
              - repeat: "7,8"
                split: ","
                steps:
                  - action: shell
                    run: echo got-{{ item }}
            """)
        self.assertEqual([ln for ln in lines if ln.startswith("got-")], ["got-7", "got-8"])

    def test_silly_counts(self):
        code, _ = self.output('name: x\nsteps:\n  - repeat: 999999999\n    steps: []\n')
        self.assertEqual(code, 1)
        self.assertIn("limit", self.history.recent("demo", 1)[0]["note"])
        self.assertEqual(self.output('name: x\nsteps:\n  - repeat: -2\n    steps: []\n')[0], 0)
        self.assertEqual(self.output('name: x\nsteps:\n  - repeat: 0\n    steps: []\n')[0], 0)

    def test_lists_as_values(self):
        ctx = Context()
        ctx.vars["parts"] = ["a", "b"]
        self.assertEqual(ctx.render("{{ parts.count }}"), 2)
        self.assertEqual(ctx.render("{{ parts.1 }}"), "a")
        self.assertEqual(ctx.render("x {{ parts }}"), "x a, b")
        with self.assertRaises(ActionError):
            ctx.render("{{ parts.3 }}")

    def test_builtin_values(self):
        _, lines = self.output("""
            name: Named
            steps:
              - action: shell
                run: echo {{ workflow }} {{ weekday }} {{ date }}
            """)
        self.assertRegex(" ".join(lines), r"Named \w+day \d{4}-\d\d-\d\d")

    def test_text_split_then_loop(self):
        _, lines = self.output("""
            name: x
            steps:
              - action: text
                text: red;blue
                change: split
                split_at: ";"
                save_as: colors
              - repeat: "{{ colors }}"
                steps:
                  - action: shell
                    run: echo got-{{ item }} of {{ colors.count }}
            """)
        self.assertIn("got-blue of 2", lines)


class MathTests(Base):
    def calc(self, text, **values):
        ctx = Context()
        return load_actions()["math"].func(ctx, text)

    def test_sums(self):
        self.assertEqual(self.calc("5 * 2 + 1"), 11)
        self.assertEqual(self.calc("(1 + 2) * 3"), 9)
        self.assertEqual(self.calc("7 / 2"), 3.5)
        self.assertEqual(self.calc("10 / 2"), 5)
        self.assertEqual(self.calc("7 % 3"), 1)
        self.assertEqual(self.calc("-3 + 1"), -2)

    def test_code_is_not_a_sum(self):
        for text in ("__import__('os').system('x')", "open('/etc/passwd')", "(1).real", "lambda: 1",
                     "'a' * 3", "9**9**9", "True + 1", ""):
            with self.assertRaises(ActionError, msg=text):
                self.calc(text)

    def test_divide_by_zero_reads_plainly(self):
        with self.assertRaisesRegex(ActionError, "divides by zero"):
            self.calc("1 / 0")

    def test_with_variables_in_a_workflow(self):
        wf = self.workflow("""
            name: x
            steps:
              - action: set
                name: num
                value: 5
              - action: math
                sum: "{{ num }} * 2"
                save_as: twice
              - repeat: "{{ twice }}"
                steps: []
              - action: shell
                run: echo answer-{{ twice }}
            """)
        self.assertEqual(run_workflow(wf, self.history), 0)
        self.assertIn("answer-10", self.last()["output"])
        self.assertIn("Repeat: 10 times", self.last()["output"])


class SkipStepTests(Base):
    def test_a_turned_off_step_does_nothing(self):
        wf = self.workflow("""
            name: x
            steps:
              - action: shell
                run: echo first
                skip: true
              - if: {equals: [a, a]}
                skip: true
                then:
                  - action: shell
                    run: echo second
              - action: shell
                run: echo third
            """)
        self.assertEqual(run_workflow(wf, self.history), 0)
        lines = self.last()["output"].splitlines()
        self.assertNotIn("first", lines)
        self.assertNotIn("second", lines)
        self.assertIn("third", lines)


class SettingsAndPauseTests(Base):
    def test_defaults_and_bad_values(self):
        self.assertEqual(settings.load(), {"paused": False, "accent": ""})
        self.assertEqual(settings.update(accent="red; evil")["accent"], "")
        self.assertEqual(settings.update(accent="#ff8800")["accent"], "#ff8800")
        self.assertNotIn("nonsense", settings.update(nonsense=1))

    def test_pause_clears_every_trigger_and_resume_restores_them(self):
        self.workflow("name: A\ntrigger:\n  schedule: every 2h\n  hotkey: Super+Z\nsteps: []\n", "a")
        with mock.patch("cron_jovi.schedule._systemctl", return_value=mock.Mock(returncode=0, stderr="")), \
                mock.patch("cron_jovi.daemon._systemctl", return_value=mock.Mock(returncode=0, stderr="", stdout="")):
            self.assertEqual(store.sync().timers, 1)
            timer = self.root / "config/systemd/user/cronjovi-a.timer"
            self.assertTrue(timer.exists())
            settings.update(paused=True)
            report = store.sync()
            self.assertEqual((report.timers, report.hotkeys), (0, 0))
            self.assertFalse(timer.exists())
            settings.update(paused=False)
            self.assertEqual(store.sync().timers, 1)
            self.assertTrue(timer.exists())


class CliTests(Base):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "cron_jovi", *args], cwd=REPO,
                              capture_output=True, text=True)

    def test_version(self):
        self.assertRegex(self.cli("--version").stdout, r"cronjovi \d+\.\d+")

    def test_completion_is_valid_bash_and_hides_internals(self):
        text = self.cli("completion").stdout
        self.assertEqual(subprocess.run(["bash", "-n"], input=text, text=True).returncode, 0)
        self.assertIn("run", text)
        self.assertNotIn("teardown", text)


class ConditionTests(Base):
    MONDAY = datetime(2026, 11, 2, 9)

    def test_weekday(self):
        self.assertTrue(conditions.weekday(["Mon", "Tue"], self.MONDAY))
        self.assertTrue(conditions.weekday("Mon", self.MONDAY))
        self.assertFalse(conditions.weekday(["Sat"], self.MONDAY))

    def test_contains_ignores_case(self):
        self.assertTrue(conditions.contains(["Hello World", "world"]))
        self.assertFalse(conditions.contains(["Hello", "bye"]))

    def test_not(self):
        self.assertTrue(conditions.negate({"equals": ["a", "b"]}))
        self.assertFalse(conditions.negate({"equals": ["a", "a"]}))

    def test_on_battery_reads_power_state(self):
        with mock.patch("cron_jovi.daemon.read_power", return_value={"discharging": True}):
            self.assertTrue(conditions.on_battery(True))
            self.assertFalse(conditions.on_battery(False))

    def test_all_conditions_must_hold(self):
        wf = self.workflow("""
            name: x
            steps:
              - if:
                  equals: [a, a]
                  contains: [abc, z]
                then:
                  - action: shell
                    run: echo wrong
                else:
                  - action: shell
                    run: echo right
            """)
        run_workflow(wf, self.history)
        self.assertIn("right", self.last()["output"].splitlines())

    def test_bad_condition_shapes_are_refused(self):
        for text in ("{equals: [a]}", "{contains: x}", "{not: {}}", "{not: {moon: 1}}"):
            with self.assertRaises(WorkflowError):
                self.workflow(f"name: x\nsteps:\n  - if: {text}\n")


class ChainingTests(Base):
    def test_run_another_workflow_and_its_failure(self):
        self.workflow("name: Child\nsteps:\n  - action: shell\n    run: echo from-child\n", "child")
        self.workflow("name: Bad\nsteps:\n  - action: shell\n    run: exit 9\n", "bad")
        parent = self.workflow("name: P\nsteps:\n  - action: run\n    workflow: child\n", "parent")
        self.assertEqual(run_workflow(parent, self.history), 0)
        self.assertIn("from-child", self.history.recent("parent", 1)[0]["output"])
        self.assertEqual(self.history.recent("child", 1)[0]["status"], "succeeded")
        parent = self.workflow("name: P\nsteps:\n  - action: run\n    workflow: bad\n", "parent2")
        self.assertEqual(run_workflow(parent, self.history), 9)

    def test_a_loop_of_workflows_stops_itself(self):
        one = self.workflow("name: A\nsteps:\n  - action: run\n    workflow: b\n", "a")
        self.workflow("name: B\nsteps:\n  - action: run\n    workflow: a\n", "b")
        self.assertEqual(run_workflow(one, self.history), 0)
        self.assertEqual(self.history.recent("a", 1)[0]["note"], "previous run still active")


class FakeToolTests(Base):
    """Real action code against stand-in programs, so no test touches this desktop."""

    def setUp(self):
        super().setUp()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls"
        for tool in ("wpctl", "pamixer", "omarchy", "loginctl", "slurp", "brightnessctl", "ddcutil"):
            self.tool(tool, 'echo "$(basename "$0") $*" >> "$CALLS"; echo "10,10 50x50"')
        self.tool("grim", 'echo "grim $*" >> "$CALLS"\n'
                          'if [ "${@: -1}" = "-" ]; then printf PNGDATA; else printf PNGDATA > "${@: -1}"; fi')
        self.tool("wl-copy", 'echo "wl-copy $*" >> "$CALLS"; cat > "$CALLS.clip"')
        for helper in ("basename", "cat"):
            (self.bin / helper).symlink_to(shutil.which(helper))
        # Only the fake folder: removing a fake must never fall through to the real tool.
        patcher = mock.patch.dict(os.environ, {"PATH": str(self.bin), "CALLS": str(self.log)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tool(self, name, body):
        path = self.bin / name
        path.write_text(f"#!/bin/bash\n{body}\n")
        path.chmod(0o755)

    def remove(self, *names):
        for name in names:
            (self.bin / name).unlink()

    def run_step(self, **step):
        wf = Workflow("demo", "Demo", self.folder / "demo.yaml", steps=[step])
        code = run_workflow(wf, self.history)
        return code, self.log.read_text() if self.log.exists() else ""

    def test_volume_set_mute_unmute(self):
        self.assertEqual(self.run_step(action="volume", percent=30)[0], 0)
        self.run_step(action="volume", do="mute")
        _, calls = self.run_step(action="volume", do="unmute")
        self.assertEqual(calls.splitlines(), [
            "wpctl set-volume @DEFAULT_AUDIO_SINK@ 30%",
            "wpctl set-mute @DEFAULT_AUDIO_SINK@ 1",
            "wpctl set-mute @DEFAULT_AUDIO_SINK@ 0",
        ])

    def test_volume_uses_pamixer_without_wpctl(self):
        self.remove("wpctl")
        self.assertIn("pamixer --set-volume 30", self.run_step(action="volume", percent=30)[1])

    def test_lock(self):
        self.assertIn("omarchy system lock", self.run_step(action="lock")[1])
        self.remove("omarchy")
        self.assertIn("loginctl lock-session", self.run_step(action="lock")[1])

    def test_pausing_silence_is_not_a_failure(self):
        self.tool("playerctl", "echo 'No players found' >&2; exit 1")
        for command in ("pause", "stop"):
            self.assertEqual(self.run_step(action="media", command=command)[0], 0)
        self.assertIn("Nothing was playing", self.last()["output"])

    def test_playing_with_no_player_is_a_failure_in_plain_words(self):
        self.tool("playerctl", "echo 'No players found' >&2; exit 1")
        self.assertEqual(self.run_step(action="media", command="next")[0], 1)
        self.assertIn("Nothing is playing", self.last()["note"])

    def test_screenshot_to_clipboard_pipes_the_image(self):
        code, calls = self.run_step(action="screenshot")
        self.assertEqual(code, 0)
        self.assertIn("wl-copy --type image/png", calls)
        self.assertEqual(Path(f"{self.log}.clip").read_text(), "PNGDATA")

    def test_screenshot_of_a_selection_asks_slurp(self):
        _, calls = self.run_step(action="screenshot", area="selection")
        self.assertIn("slurp", calls)
        self.assertIn("grim -g 10,10 50x50 -", calls)

    def test_screenshot_to_file(self):
        folder = self.root / "shots"
        code, _ = self.run_step(action="screenshot", send_to="file", folder=str(folder))
        self.assertEqual(code, 0)
        self.assertEqual(list(folder.glob("*.png"))[0].read_text(), "PNGDATA")

    def test_cancelled_selection_fails_clearly(self):
        self.tool("slurp", "echo 'selection cancelled' >&2; exit 1")
        code, _ = self.run_step(action="screenshot", area="selection")
        self.assertEqual(code, 1)
        self.assertIn("Selection cancelled", self.last()["note"])

    def test_missing_tool_says_which(self):
        self.remove("grim")
        self.assertEqual(self.run_step(action="screenshot")[0], 127)
        self.assertEqual(self.last()["note"], "This step needs grim, which isn't installed.")

    def ask(self, script, **step):
        self.tool("zenity", script)
        return self.run_step(action="ask", question="Well?", save_as="answer", **step)

    def test_ask_returns_what_was_typed(self):
        self.assertEqual(self.ask("echo my answer")[0], 0)

    def test_ask_yes_no_treats_no_as_an_answer(self):
        wf = Workflow("demo", "Demo", self.folder / "demo.yaml", steps=[
            {"action": "ask", "question": "Sure?", "kind": "yes-no", "save_as": "answer"},
            {"action": "set", "name": "seen", "value": "{{ answer }}"},
            {"if": {"equals": ["{{ seen }}", "no"]}, "then": [{"action": "lock"}]}])
        self.tool("zenity", "exit 1")
        self.assertEqual(run_workflow(wf, self.history), 0)
        self.assertIn("omarchy system lock", self.log.read_text())

    def test_cancelling_a_typed_question_is_a_failure(self):
        self.assertEqual(self.ask("exit 1")[0], 1)
        self.assertEqual(self.last()["note"], "The question was closed without an answer.")

    def test_choose_passes_the_choices(self):
        self.tool("zenity", 'echo "$*" >> "$CALLS"; echo Later')
        _, calls = self.run_step(action="ask", question="When?", kind="choose", choices=["Now", "Later"])
        self.assertIn("--list", calls)
        self.assertIn("Now Later", calls)

    def test_brightness_reaches_omarchy(self):
        self.assertIn("omarchy brightness display --no-osd 40%", self.run_step(action="brightness", percent=40)[1])


class BackgroundFailureTests(Base):
    def run_it(self, trigger, on_failure=()):
        wf = self.shell_wf("exit 5")
        wf.on_failure = list(on_failure)
        with mock.patch("cron_jovi.engine.tell_user") as tell:
            run_workflow(wf, self.history, trigger)
        return tell

    def test_background_failure_tells_the_user(self):
        for trigger in ("schedule", "file", "webhook"):
            self.run_it(trigger).assert_called_once()

    def test_manual_runs_are_already_being_watched(self):
        self.run_it("manual").assert_not_called()

    def test_on_failure_takes_over(self):
        step = {"action": "shell", "run": "true"}
        self.run_it("schedule", [step]).assert_not_called()

    def test_missing_notifier_is_harmless(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            tell_user(self.shell_wf("true"), "reason")


class PruneTests(Base):
    def test_keeps_the_newest_and_never_a_running_row(self):
        for number in range(6):
            run = self.history.start("demo", "manual")
            self.history.finish(run, "succeeded", 0, str(number), "")
        running = self.history.start("demo", "manual")
        self.history.start("other", "manual")
        self.history.prune("demo", keep=3)
        rows = self.history.recent("demo")
        self.assertEqual([r["note"] for r in rows if r["id"] != running], ["5", "4"])
        self.assertEqual(rows[0]["id"], running)
        self.assertEqual(len(self.history.recent("other")), 1)


class OverlapTests(Base):
    def spawn(self, body, wait_for):
        path = self.folder / "demo.yaml"
        path.write_text(textwrap.dedent(body))
        proc = subprocess.Popen(
            [sys.executable, "-m", "cron_jovi", "run", "demo"], cwd=REPO,
            stdout=subprocess.DEVNULL)
        self.addCleanup(proc.kill)
        deadline = time.monotonic() + 5
        while not wait_for.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(wait_for.exists())
        return proc

    def body(self, mark, policy):
        return f"""
            name: Demo
            trigger:
              if_running: {policy}
            steps:
              - action: shell
                run: touch {mark}; sleep 30
            """

    def test_skip_new_run_when_previous_active(self):
        mark = self.root / "started"
        proc = self.spawn(self.body(mark, "skip"), mark)
        wf = load(self.folder / "demo.yaml")
        self.assertEqual(run_workflow(wf, self.history, "schedule", 100.0), 0)
        row = self.last()
        self.assertEqual((row["status"], row["note"], row["scheduled_at"], row["started_at"]),
                         ("skipped", "previous run still active", 100.0, None))
        proc.send_signal(signal.SIGTERM)
        proc.wait(5)

    def test_restart_stops_the_old_run(self):
        mark = self.root / "started"
        proc = self.spawn(self.body(mark, "restart"), mark)
        wf = self.shell_wf("echo fresh")
        wf.trigger = Trigger(if_running="restart")
        self.assertEqual(run_workflow(wf, self.history), 0)
        self.assertEqual(proc.wait(5), 143)
        new, old = self.history.recent("demo", 2)
        self.assertEqual(new["status"], "succeeded")
        self.assertEqual(old["status"], "stopped")

    def test_is_running_and_stop_reach_a_run_started_elsewhere(self):
        mark = self.root / "started"
        self.assertFalse(is_running("demo"))
        proc = self.spawn(self.body(mark, "skip"), mark)
        self.assertTrue(is_running("demo"))
        self.assertTrue(is_running("demo"), "checking must not disturb the run")
        self.assertTrue(stop_run("demo"))
        self.assertEqual(proc.wait(5), 143)
        self.assertFalse(is_running("demo"))
        self.assertFalse(stop_run("demo"))

    def test_killed_run_is_closed_by_the_next_one(self):
        mark = self.root / "started"
        proc = self.spawn(self.body(mark, "skip"), mark)
        proc.kill()
        proc.wait()
        run_workflow(self.shell_wf("true"), self.history)
        _, old = self.history.recent("demo", 2)
        self.assertEqual(old["status"], "stopped")


class ScheduleTests(Base):
    SPEC = "*-*-* 02:00:00 UTC"
    DAY = 86400
    TICK = 1798768800.0  # 2027-01-01 02:00:00 UTC

    def wf(self, **trigger):
        return Workflow("demo", "Demo", self.folder / "demo.yaml",
                        trigger=Trigger(schedule=self.SPEC, **trigger))

    def fire(self, wf, now):
        self.spawned = []
        return schedule.tick(wf, self.history, now, lambda w, at, note: self.spawned.append(
            (at, note)))

    def test_friendly_forms(self):
        self.assertEqual(schedule.to_calendar("daily at 2:30"), "*-*-* 02:30:00")
        self.assertEqual(schedule.to_calendar("every 2h"), "00/2:00")
        self.assertEqual(schedule.to_calendar("every 15m"), "*:00/15")
        self.assertEqual(schedule.to_calendar("Mon 09:00"), "Mon 09:00")
        for spec in ("every 2h", "every 15m", "daily at 2:30"):
            self.assertEqual(len(schedule.next_ticks(spec, self.TICK, 2)), 2)

    def test_bad_schedule_is_reported(self):
        with self.assertRaises(WorkflowError):
            schedule.next_ticks("whenever", self.TICK)

    def test_next_ticks_are_exact(self):
        self.assertEqual(schedule.next_ticks(self.SPEC, self.TICK - 60), [self.TICK])
        self.assertEqual(schedule.next_ticks(self.SPEC, self.TICK), [self.TICK + self.DAY])

    def test_on_time_tick_runs_without_a_note(self):
        self.history.set_next_due("demo", self.SPEC, self.TICK)
        self.assertEqual(self.fire(self.wf(), self.TICK + 1), "on time")
        self.assertEqual(self.spawned, [(self.TICK, "")])
        self.assertEqual(self.history.next_due("demo", self.SPEC), self.TICK + self.DAY)

    def test_missed_ticks_run_once_with_a_note(self):
        self.history.set_next_due("demo", self.SPEC, self.TICK)
        now = self.TICK + 3 * self.DAY + 5 * 3600
        self.assertEqual(self.fire(self.wf(), now), "late")
        self.assertEqual(len(self.spawned), 1)
        at, note = self.spawned[0]
        self.assertEqual(at, self.TICK + 3 * self.DAY)
        self.assertIn("Ran late", note)
        self.assertIn("4 ticks missed", note)

    def test_skip_policy_records_a_row_and_does_not_run(self):
        self.history.set_next_due("demo", self.SPEC, self.TICK)
        self.assertEqual(self.fire(self.wf(if_missed="skip"), self.TICK + 3600), "skipped")
        self.assertEqual(self.spawned, [])
        row = self.last()
        self.assertEqual((row["status"], row["note"]), ("skipped", "machine was off"))
        self.assertIsNone(row["started_at"])

    def test_catch_up_fire_with_nothing_owed_is_ignored(self):
        self.history.set_next_due("demo", self.SPEC, self.TICK)
        self.assertEqual(self.fire(self.wf(), self.TICK - 3600), "nothing due")
        self.assertEqual(self.spawned, [])
        self.assertEqual(self.history.recent("demo"), [])

    def test_changed_schedule_starts_clean(self):
        self.history.set_next_due("demo", "*-*-* 05:00:00", self.TICK - 30 * self.DAY)
        self.assertEqual(self.fire(self.wf(), self.TICK + 60), "nothing due")


class HotkeyTests(Base):
    def wf(self, hotkey="Super+Shift+F", name="Focus Mode", slug="focus-mode"):
        return Workflow(slug, name, Path("x"), trigger=Trigger(hotkey=hotkey))

    def test_parse(self):
        self.assertEqual(hotkeys.parse("Super+Shift+F"), (["SUPER", "SHIFT"], "F"))
        self.assertEqual(hotkeys.parse("Print"), ([], "Print"))
        with self.assertRaises(WorkflowError):
            hotkeys.parse("Hyper+F")

    def test_lua(self):
        text = hotkeys.hyprland_lua([self.wf()])
        self.assertIn('hl.bind("SUPER + SHIFT + F", hl.dsp.exec_cmd("', text)
        self.assertIn('run focus-mode"), { description = "Cron Jovi: Focus Mode" })', text)

    def test_lua_escapes_names(self):
        self.assertIn('Say \\"hi\\"', hotkeys.hyprland_lua([self.wf(name='Say "hi"')]))

    def test_conf_and_niri(self):
        self.assertIn("bind = SUPER SHIFT, F, exec, ", hotkeys.hyprland_conf([self.wf()]))
        self.assertIn('Super+Shift+F { spawn "', hotkeys.niri_kdl([self.wf()]))

    def test_link_and_unlink_restore_the_config(self):
        hypr = self.root / "config/hypr"
        hypr.mkdir(parents=True)
        original = 'require("hypr.input")\nrequire("hypr.bindings")\nrequire("hypr.looknfeel")\n'
        (hypr / "hyprland.lua").write_text(original)
        adapter = hotkeys.active()[0]
        hotkeys.link(adapter)
        hotkeys.link(adapter)
        lines = (hypr / "hyprland.lua").read_text().splitlines()
        self.assertEqual(len([ln for ln in lines if hotkeys.MARKER in ln]), 1)
        self.assertIn(hotkeys.MARKER, lines[2])
        self.assertTrue(list(hypr.glob("hyprland.lua.bak.*")))
        hotkeys.unlink(adapter)
        self.assertEqual((hypr / "hyprland.lua").read_text(), original)


if __name__ == "__main__":
    unittest.main()
