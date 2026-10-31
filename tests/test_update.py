import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cron_jovi import __version__, settings, update  # noqa: E402

try:
    from cron_jovi.gui import server
except ImportError:
    server = None

HEADERS = {"X-CronJovi-Token": "token"}


def release(tag, draft=False, name=None):
    return {"tag_name": tag, "draft": draft, "name": name or tag}


def github(*releases):
    answer = mock.Mock()
    answer.json.return_value = list(releases)
    return mock.patch("requests.get", return_value=answer)


class Sandbox(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {
            "XDG_CONFIG_HOME": f"{tmp.name}/config", "XDG_STATE_HOME": f"{tmp.name}/state"})
        patcher.start()
        self.addCleanup(patcher.stop)


class VersionTests(unittest.TestCase):
    def test_only_a_newer_exact_version_counts(self):
        self.assertTrue(update.is_newer("v0.0.2", "0.0.1"))
        self.assertTrue(update.is_newer("v0.0.10", "0.0.9"))
        for tag in ("v0.0.1", "v0.0.0", "0.0.2", "v0.0.2-rc1", "v0.0.2; rm -rf ~", "../v9.9.9", "", None):
            with self.subTest(tag=tag):
                self.assertFalse(update.is_newer(tag, "0.0.1"))


class CheckTests(Sandbox):
    def test_checks_stay_off_until_turned_on(self):
        with mock.patch("requests.get") as get:
            self.assertIsNone(update.check())
        get.assert_not_called()

    def test_a_button_press_checks_even_when_off(self):
        with github(release("v99.0.0")) as get:
            self.assertEqual(update.check(force=True)["tag"], "v99.0.0")
        get.assert_called_once()

    def test_turned_on_it_asks_once_a_day(self):
        settings.update(update_check=True)
        with github(release("v99.0.0")) as get:
            update.check()
            update.check()
        self.assertEqual(get.call_count, 1)

    def test_a_beta_counts_but_a_draft_and_odd_tags_dont(self):
        with github(release("v98.0.0"), release("v99.0.0", draft=True), release("nightly")):
            self.assertEqual(update.check(force=True)["tag"], "v98.0.0")

    def test_no_offer_when_already_current(self):
        with github(release(f"v{__version__}")):
            self.assertIsNone(update.check(force=True))


class InstallTests(Sandbox):
    def install(self, tag="v99.0.0", pip_code=0, version="99.0.0"):
        calls = []

        def run(argv, **_):
            calls.append(argv)
            if "pip" in argv:
                return mock.Mock(returncode=pip_code, stderr="ERROR: no such file\n")
            return mock.Mock(returncode=0, stdout=f"{version}\n")

        with mock.patch.object(update, "blocked", return_value=""), mock.patch("subprocess.run", run):
            result = update.install(tag)
        return result, calls

    def test_installs_only_from_the_fixed_address(self):
        done, calls = self.install()
        self.assertTrue(done)
        self.assertIn("https://github.com/jgarza9788/cron-jovi/archive/refs/tags/v99.0.0.tar.gz", calls[0])
        self.assertEqual(update.status()["state"], "done")

    def test_refuses_an_old_or_odd_tag_without_running_pip(self):
        for tag in ("v0.0.0", "v9.9.9 --index-url=http://evil"):
            with self.subTest(tag=tag):
                done, calls = self.install(tag)
                self.assertFalse(done)
                self.assertEqual(calls, [])

    def test_a_failed_install_says_so_and_stops(self):
        done, calls = self.install(pip_code=1)
        self.assertFalse(done)
        self.assertEqual(len(calls), 1)
        self.assertIn("no such file", update.status()["message"])

    def test_the_new_version_must_really_appear(self):
        done, _ = self.install(version=__version__)
        self.assertFalse(done)
        self.assertEqual(update.status()["state"], "failed")

    def test_a_run_from_source_cant_update(self):
        with mock.patch.object(sys, "prefix", "/venv"), mock.patch.object(sys, "base_prefix", "/usr"), \
                mock.patch.object(update, "__file__", "/home/me/cron-jovi/cron_jovi/update.py"):
            self.assertIn("source", update.blocked())

    def test_a_dead_updater_isnt_shown_as_still_running(self):
        update._status_path().parent.mkdir(parents=True)
        update._status_path().write_text(json.dumps({"state": "installing", "tag": "v1.0.0", "pid": 2 ** 22 + 1}))
        self.assertEqual(update.status()["state"], "failed")


@unittest.skipIf(server is None, "needs Flask")
class ApiTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.client = server.create_app("token").test_client()

    def post(self, tag):
        return self.client.post("/api/update/install", json={"tag": tag}, headers=HEADERS)

    def test_needs_the_token(self):
        self.assertEqual(self.client.post("/api/update/install", json={"tag": "v99.0.0"}).status_code, 403)
        self.assertEqual(self.client.post("/api/update/restart").status_code, 403)

    def test_opening_the_app_contacts_nobody_by_default(self):
        with mock.patch("requests.get") as get:
            answer = self.client.get("/api/update", headers=HEADERS).json
        get.assert_not_called()
        self.assertIsNone(answer["available"])

    def test_an_offline_check_is_explained(self):
        with mock.patch("requests.get", side_effect=requests.ConnectionError):
            answer = self.client.get("/api/update?force=1", headers=HEADERS).json
        self.assertIn("GitHub", answer["error"])

    def test_refuses_a_bad_tag(self):
        with mock.patch("subprocess.Popen") as popen:
            self.assertEqual(self.post("v0.0.0").status_code, 400)
        popen.assert_not_called()

    def test_waits_for_running_workflows(self):
        workflow = mock.Mock(slug="demo")
        workflow.name = "Demo"
        with mock.patch.object(server, "discover", return_value=([workflow], [])), \
                mock.patch.object(server, "is_running", return_value=True), \
                mock.patch.object(update, "blocked", return_value=""), mock.patch("subprocess.Popen") as popen:
            answer = self.post("v99.0.0")
        self.assertEqual(answer.status_code, 409)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
