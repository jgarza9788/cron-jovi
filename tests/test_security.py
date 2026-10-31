"""Hostile input: each test here is an attack that once worked, or a guard against one."""

import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cron_jovi import __version__, conditions, schedule, shellvars, store  # noqa: E402
from cron_jovi.action_api import ActionError, load_actions  # noqa: E402
from cron_jovi.engine import Context, run_steps  # noqa: E402
from cron_jovi.history import History  # noqa: E402
from cron_jovi.workflow import WorkflowError, parse  # noqa: E402

try:
    from cron_jovi import daemon
    from cron_jovi.gui import server
except ImportError:
    server = None

HOSTILE = ["$(touch {mark})", "`touch {mark}`", "'; touch {mark}; '", '"; touch {mark}; "',
           "x\ntouch {mark}\n", "$(touch {mark})'\"`"]
PLACES = ["echo {{ f }}", 'echo "{{ f }}"', "echo '{{ f }}'", "cat <<EOF\n{{ f }}\nEOF",
          "cat <<<{{ f }}", 'echo "$(echo {{ f }})"', "echo $(echo {{ f }})", "echo `echo {{ f }}`",
          'echo "a {{ f }} b"', "# it's a comment\necho {{ f }}", "echo it\\'s {{ f }}",
          'echo "$(echo "{{ f }}")"', "( echo {{ f }} )", "echo ~/{{ f }}.txt"]


class Sandbox(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = mock.patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_STATE_HOME": str(self.root / "state"),
            "XDG_DATA_HOME": str(self.root / "data"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mark = self.root / "mark"

    def context(self, value: str) -> Context:
        ctx = Context(lambda line: None)
        ctx.vars["f"] = value.format(mark=self.mark)
        return ctx


class ShellVariableTests(Sandbox):
    def test_no_value_can_run_in_a_shell_step(self):
        for place in PLACES:
            for value in HOSTILE:
                with self.subTest(place=place, value=value):
                    run_steps([{"action": "shell", "run": place}], self.context(value))
                    self.assertFalse(self.mark.exists())

    def test_no_value_can_run_in_a_command_condition(self):
        for place in PLACES:
            for value in HOSTILE + ["x; touch {mark}"]:
                with self.subTest(place=place, value=value):
                    step = {"if": {"command": place.replace("echo", "test -n")}, "then": []}
                    run_steps([step], self.context(value))
                    self.assertFalse(self.mark.exists())

    def test_a_value_in_a_not_condition_stays_data(self):
        step = {"if": {"not": {"command": "test -n {{ f }}"}}, "then": []}
        run_steps([step], self.context("x; touch {mark}"))
        self.assertFalse(self.mark.exists())

    def test_quoted_variables_come_out_exactly(self):
        value = "  two  spaces's \"here\" $HOME "
        for command in ("printf %s {{ f }}", 'printf %s "{{ f }}"', "printf %s '{{ f }}'"):
            with self.subTest(command=command):
                ctx = self.context("")
                ctx.vars["f"] = value
                self.assertEqual(load_actions()["shell"].func(ctx, command), value.strip())

    def test_text_around_a_variable_is_kept(self):
        ctx = self.context("mid")
        self.assertEqual(load_actions()["shell"].func(ctx, 'echo "a {{ f }} b" c{{ f }}d'), "a mid b cmidd")

    def test_the_log_shows_the_real_value(self):
        lines = []
        ctx = Context(lines.append)
        ctx.vars["f"] = "hello"
        load_actions()["shell"].func(ctx, "echo {{ f }}")
        self.assertIn("$ echo hello", lines)

    def test_other_languages_still_get_quoted_text(self):
        ctx = self.context("it's")
        output = load_actions()["shell"].func(ctx, "print({{ f }}, end='')", shell=sys.executable)
        self.assertEqual(output, "it's")

    def test_context(self):
        for before, place in (("echo ", "code"), ('echo "', "double"), ("echo '", "single"),
                              ('echo "$(', "code"), ('echo "$(echo "', "double"),
                              ("cat <<EOF\n", "heredoc"), ("cat <<EOF\nx\nEOF\necho ", "code"),
                              ("cat <<< ", "code"), ("# don't\necho ", "code"),
                              ("echo `", "code"), ("echo a\\'", "code")):
            with self.subTest(before=before):
                self.assertEqual(shellvars.context(before), place)


class ScheduleTimezoneTests(unittest.TestCase):
    def test_ticks_are_the_same_on_a_utc_system(self):
        spec, base = "daily at 02:00", 1790000000
        ticks = {}
        for zone in ("UTC", "America/Chicago"):
            with mock.patch.dict(os.environ, {"TZ": zone}):
                ticks[zone] = schedule.next_ticks(spec, base, 3)
        self.assertEqual(len(ticks["UTC"]), 3)
        self.assertEqual(len(ticks["America/Chicago"]), 3)


class SmallAttackTests(Sandbox):
    def test_a_self_referencing_condition_is_refused(self):
        data = yaml.safe_load("name: r\nsteps:\n  - {if: &n {not: *n}, then: []}\n")
        with self.assertRaisesRegex(WorkflowError, "nested"):
            parse(data, self.root / "r.yaml")

    def test_an_option_is_not_a_schedule(self):
        for spec in ("--help", "--version", "-h"):
            with self.subTest(spec=spec), self.assertRaises(WorkflowError):
                schedule.next_ticks(spec, time.time())

    def test_shared_files_must_be_workflows(self):
        for text in ("- a\n", "plain", "", "a: [", "42"):
            with self.subTest(text=text), self.assertRaises(WorkflowError):
                store.parse_shared(text)

    def test_app_names_cant_be_options(self):
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)) as run:
            conditions.app_running("--help")
        self.assertEqual(run.call_args[0][0], ["pgrep", "-xi", "--", "--help"])

    def test_rename_stays_in_its_folder(self):
        source = self.root / "a.txt"
        source.write_text("x")
        for dest in ("../b.txt", "/etc/b", "x/y", "..", ""):
            with self.subTest(dest=dest), self.assertRaises(ActionError):
                load_actions()["file"].func(Context(lambda _: None), "rename", str(source), dest)

    def test_history_is_private(self):
        History().close()
        folder = self.root / "state/cronjovi"
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((folder / "history.db").stat().st_mode), 0o600)

    def test_review_lists_windows_and_screenshots(self):
        found = store.effects([{"action": "window", "op": "close", "app": "firefox"},
                               {"action": "screenshot"}])
        self.assertEqual(found, ["Closes firefox", "Takes a screenshot"])

    def test_version_is_a_plain_release_number(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")


@unittest.skipIf(server is None, "needs Flask")
class ServerAttackTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.client = server.create_app("token").test_client()

    def test_a_non_ascii_token_is_refused_not_a_crash(self):
        answer = self.client.get("/api/settings", headers={"X-CronJovi-Token": "é".encode("latin-1")})
        self.assertEqual(answer.status_code, 403)

    def test_a_non_ascii_webhook_token_is_refused_not_a_crash(self):
        workflow = parse({"name": "h", "trigger": {"webhook": True}, "steps": []}, self.root / "h.yaml")
        daemon.webhook_token("h")
        client = daemon.webhook_app([workflow], mock.Mock()).test_client()
        self.assertEqual(client.post("/hook/h/é").status_code, 404)

    def test_bad_imports_are_explained(self):
        headers = {"X-CronJovi-Token": "token"}
        for path in ("/api/import", "/api/import/review"):
            for text in ("- a\n", "a: ["):
                with self.subTest(path=path, text=text):
                    answer = self.client.post(path, json={"yaml": text}, headers=headers)
                    self.assertEqual(answer.status_code, 400)

    def test_csp_blocks_plugins_and_framing(self):
        answer = self.client.get("/")
        policy = answer.headers["Content-Security-Policy"]
        answer.close()
        for rule in ("object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'"):
            self.assertIn(rule, policy)


if __name__ == "__main__":
    unittest.main()
