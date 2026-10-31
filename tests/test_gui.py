import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

try:
    from cron_jovi.gui import server, theme
except ImportError:
    server = None

from cron_jovi import store  # noqa: E402
from cron_jovi.workflow import WorkflowError, load  # noqa: E402

TOKEN = "test-token"
HEADERS = {"X-CronJovi-Token": TOKEN}
COMMENTED = "# keep me\nname: Commented\nsteps:\n  - action: notify  # and me\n    text: hi\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_DATA_HOME": str(root / "data"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        # Never touch the real user's systemd from a test.
        for target, value in (
            ("cron_jovi.schedule._systemctl", mock.Mock(returncode=0, stderr="", stdout="")),
            ("cron_jovi.doctor.timers_active", 0),
        ):
            fake = mock.patch(target, return_value=value)
            fake.start()
            self.addCleanup(fake.stop)
        self.folder = root / "config/cronjovi/workflows"
        self.folder.mkdir(parents=True)


class StoreTests(Base):
    def test_save_rejects_invalid_and_keeps_the_old_file(self):
        store.save("demo", {"name": "Demo", "steps": []})
        before = (self.folder / "demo.yaml").read_text()
        with self.assertRaises(WorkflowError):
            store.save("demo", {"name": "Demo", "steps": [{"action": "nope"}]})
        self.assertEqual((self.folder / "demo.yaml").read_text(), before)

    def test_bad_schedule_is_refused_on_save(self):
        data = {"name": "Demo", "trigger": {"schedule": "whenever"}, "steps": []}
        with self.assertRaisesRegex(WorkflowError, "isn't a schedule"):
            store.save("demo", data)

    def test_dump_round_trip_drops_empty_lists(self):
        data = {"name": "Demo", "steps": [], "on_failure": [], "enabled": False}
        store.save("demo", data)
        self.assertEqual(store.read_raw("demo"),
                         {"name": "Demo", "description": "", "enabled": False, "steps": []})

    def test_description_is_always_there_and_stays_readable(self):
        store.save("demo", {"name": "Demo", "steps": []})
        self.assertIn("name: Demo\ndescription: ''\n", (self.folder / "demo.yaml").read_text())
        text = "First line.\n\nSecond paragraph: with a colon."
        store.save("demo", {"name": "Demo", "description": text, "steps": []})
        written = (self.folder / "demo.yaml").read_text()
        self.assertIn("description: |", written)
        self.assertEqual(store.read_raw("demo")["description"], text)
        self.assertEqual(load(self.folder / "demo.yaml").description, text)

    def test_yaml_save_keeps_comments(self):
        store.save("demo", {"name": "Demo", "steps": []})
        store.save_yaml("demo", COMMENTED)
        self.assertEqual((self.folder / "demo.yaml").read_text(), COMMENTED)

    def test_create_never_overwrites(self):
        first = store.create({"name": "Same", "steps": []})
        second = store.create({"name": "Same", "steps": []})
        self.assertEqual((first.slug, second.slug), ("same", "same-2"))

    def test_enable_keeps_comments(self):
        (self.folder / "demo.yaml").write_text(COMMENTED)
        store.set_enabled("demo", False)
        text = (self.folder / "demo.yaml").read_text()
        self.assertIn("# keep me", text)
        self.assertIn("name: Commented\nenabled: false\n", text)
        store.set_enabled("demo", True)
        self.assertIn("enabled: true\n", (self.folder / "demo.yaml").read_text())
        self.assertEqual((self.folder / "demo.yaml").read_text().count("enabled"), 1)

    def test_export_strips_personal_settings_and_never_overwrites(self):
        store.save("demo", {"name": "Demo", "enabled": False, "favorite": True, "folder": "Work",
                            "trigger": {"webhook": True}, "steps": []})
        target = Path(self.tmp.name) / "out"
        first = store.export("demo", target)
        second = store.export("demo", target)
        self.assertNotEqual(first, second)
        data = store.yaml.safe_load(first.read_text())
        self.assertEqual(set(data), {"name", "description", "trigger", "steps"})

    def test_secret_scan(self):
        data = {"steps": [
            {"action": "http", "url": "https://x", "headers": {"Authorization": "Bearer abc"}},
            {"action": "shell", "run": "curl --password hunter2 x"},
            {"action": "notify", "text": "{{ token }}"},
            {"action": "notify", "text": "Time for water"},
        ]}
        found = store.secrets_in(data)
        self.assertTrue(any("Authorization" in item for item in found))
        self.assertTrue(any("run" in item for item in found))
        self.assertEqual(len(found), 2)

    def test_path_for_refuses_escapes(self):
        for slug in ("../evil", "a/b", ".hidden", ""):
            with self.assertRaises(WorkflowError):
                store.path_for(slug)

    def test_shell_commands_finds_nested_commands(self):
        steps = [
            {"action": "shell", "run": "one"},
            {"if": {"command": "two"}, "then": [{"action": "shell", "run": "three"}], "else": []},
            {"repeat": 2, "steps": [{"action": "shell", "run": "four"}]},
        ]
        self.assertEqual(sorted(store.shell_commands(steps)), ["four", "one", "three", "two"])


@unittest.skipIf(server is None, "Flask is not installed")
class ApiTests(Base):
    def setUp(self):
        super().setUp()
        self.client = server.create_app(TOKEN, {"port": 5000}).test_client()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.client.__enter__()

    def call(self, method, path, **kwargs):
        kwargs.setdefault("headers", HEADERS)
        kwargs.setdefault("base_url", "http://127.0.0.1:5000")
        return getattr(self.client, method)(f"/api{path}", **kwargs)

    def make(self, name="Demo", **extra):
        return self.call("post", "/workflows", json={"name": name, "steps": [], **extra}).json["slug"]

    def test_every_api_route_needs_the_token(self):
        app = server.create_app(TOKEN, {"port": 5000})
        client = app.test_client()
        rules = [r for r in app.url_map.iter_rules() if r.rule.startswith("/api/")]
        self.assertGreater(len(rules), 15)
        for rule in rules:
            path = rule.rule.replace("<slug>", "x").replace("<run_id>", "1").replace("<int:run_id>", "1")
            method = next(iter(rule.methods - {"HEAD", "OPTIONS"})).lower()
            response = getattr(client, method)(path, base_url="http://127.0.0.1:5000")
            self.assertEqual(response.status_code, 403, rule.rule)

    def test_foreign_host_is_refused_even_with_the_token(self):
        response = self.call("get", "/state", base_url="http://evil.example:5000")
        self.assertEqual(response.status_code, 403)

    def test_no_cors_is_granted(self):
        response = self.call("get", "/state", headers={**HEADERS, "Origin": "http://evil.example"})
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_page_has_a_content_security_policy(self):
        response = self.client.get("/", base_url="http://127.0.0.1:5000")
        self.addCleanup(response.close)
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])

    def test_create_read_save_delete(self):
        slug = self.make()
        read = self.call("get", f"/workflows/{slug}").json
        self.assertEqual(read["data"]["name"], "Demo")
        data = {**read["data"], "favorite": True}
        self.assertEqual(self.call("put", f"/workflows/{slug}", json=data).status_code, 200)
        state = self.call("get", "/state").json
        self.assertTrue(state["workflows"][0]["favorite"])
        self.assertEqual(self.call("delete", f"/workflows/{slug}").status_code, 200)
        self.assertEqual(self.call("get", f"/workflows/{slug}").status_code, 400)

    def test_outside_edit_is_never_overwritten(self):
        slug = self.make()
        read = self.call("get", f"/workflows/{slug}").json
        path = self.folder / f"{slug}.yaml"
        path.write_text("name: Edited Elsewhere\nsteps: []\n")
        headers = {**HEADERS, "If-Match": read["stamp"]}
        response = self.call("put", f"/workflows/{slug}", json=read["data"], headers=headers)
        self.assertEqual(response.status_code, 409)
        self.assertIn("Edited Elsewhere", path.read_text())
        response = self.call("put", f"/workflows/{slug}/yaml", json={"yaml": "name: x\nsteps: []\n"}, headers=headers)
        self.assertEqual(response.status_code, 409)
        fresh = self.call("get", f"/workflows/{slug}").json["stamp"]
        ok = self.call("put", f"/workflows/{slug}", json=read["data"], headers={**HEADERS, "If-Match": fresh})
        self.assertEqual(ok.status_code, 200)
        self.assertNotEqual(ok.json["stamp"], fresh)

    def test_export_stops_for_secrets_until_confirmed(self):
        slug = self.make(steps=[{"action": "shell", "run": "use api_key=123"}])
        with mock.patch("pathlib.Path.home", return_value=Path(self.tmp.name)):
            first = self.call("post", f"/workflows/{slug}/export", json={}).json
            self.assertIn("secrets", first)
            self.assertFalse((Path(self.tmp.name) / "Downloads").exists())
            done = self.call("post", f"/workflows/{slug}/export", json={"confirmed": True}).json
        self.assertTrue(Path(done["path"]).exists())

    def test_clear_history_keeps_running_rows(self):
        from cron_jovi.history import History
        history = History()
        self.addCleanup(history.close)
        history.finish(history.start("a", "manual"), "succeeded", 0, "", "private output")
        running = history.start("b", "manual")
        self.assertEqual(self.call("delete", "/history").status_code, 200)
        self.assertEqual([r["id"] for r in history.recent()], [running])

    def test_stop_with_nothing_running(self):
        slug = self.make()
        self.assertIs(self.call("post", f"/workflows/{slug}/stop", json={}).json["stopped"], False)

    def test_step_test_refuses_bad_steps(self):
        response = self.call("post", "/test-step", json={"action": "nope"})
        self.assertEqual(response.status_code, 400)

    def test_validation_errors_come_back_as_messages(self):
        slug = self.make()
        response = self.call("put", f"/workflows/{slug}", json={"name": "x", "steps": [{"action": "no"}]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("unknown action", response.json["error"])

    def test_state_does_not_ship_run_output(self):
        slug = self.make()
        from cron_jovi.history import History
        history = History()
        self.addCleanup(history.close)
        history.finish(history.start(slug, "manual"), "succeeded", 0, "", "x" * 1000)
        row = self.call("get", "/state").json["workflows"][0]["last_run"]
        self.assertNotIn("output", row)

    def test_import_is_reviewed_and_arrives_off(self):
        text = "name: Shared\nsteps:\n  - action: shell\n    run: rm -rf ~/\n"
        review = self.call("post", "/import/review", json={"yaml": text}).json
        self.assertEqual(review["commands"], ["rm -rf ~/"])
        self.assertEqual(list(self.folder.glob("*.yaml")), [])
        slug = self.call("post", "/import", json={"yaml": text}).json["slug"]
        self.assertIs(self.call("get", f"/workflows/{slug}").json["data"]["enabled"], False)

    def test_hotkey_conflict_with_another_workflow(self):
        self.make("Other", trigger={"hotkey": "Super+Z"})
        with mock.patch("cron_jovi.hotkeys.hyprland_conflicts", return_value=[]):
            result = self.call("post", "/hotkey/check", json={"hotkey": "super+z"}).json
        self.assertEqual(result["conflicts"], ["Other uses this hotkey"])

    def test_templates_are_all_valid(self):
        templates = self.call("get", "/templates").json
        self.assertGreaterEqual(len(templates), 5)
        for template in templates:
            self.assertTrue(template["blurb"])
            response = self.call("post", "/workflows", json=template["workflow"])
            self.assertEqual(response.status_code, 201, template["id"])

    def test_settings_round_trip_and_reach_the_theme(self):
        saved = self.call("put", "/settings", json={"accent": "#112233"}).json
        self.assertEqual(saved["accent"], "#112233")
        self.assertEqual(self.call("get", "/theme").json["colors"]["accent"], "#112233")

    def test_actions_describe_themselves(self):
        actions = self.call("get", "/actions").json
        self.assertEqual(len(actions), 21)
        for action in actions:
            self.assertTrue(action["title"] and action["blurb"] and action["icon"], action["name"])


@unittest.skipIf(server is None, "Flask is not installed")
class ThemeTests(Base):
    def test_falls_back_without_omarchy(self):
        with mock.patch.object(theme, "theme_file", return_value=Path("/nonexistent")):
            self.assertEqual(theme.load()["source"], "default")

    def test_reads_omarchy_colors_and_fills_gaps(self):
        path = Path(self.tmp.name) / "colors.toml"
        path.write_text('accent = "#123456"\nmode = "light"\nnot_a_color = "x"\n')
        with mock.patch.object(theme, "theme_file", return_value=path):
            loaded = theme.load()
        self.assertEqual(loaded["source"], "omarchy")
        self.assertEqual(loaded["colors"]["accent"], "#123456")
        self.assertEqual(loaded["colors"]["mode"], "light")
        self.assertIn("background", loaded["colors"])
        self.assertNotIn("not_a_color", loaded["colors"])


if __name__ == "__main__":
    unittest.main()
