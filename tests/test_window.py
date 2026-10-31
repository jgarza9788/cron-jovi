import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cron_jovi import compositor  # noqa: E402
from cron_jovi.action_api import ActionError, load_actions  # noqa: E402
from cron_jovi.engine import Context  # noqa: E402

CLIENTS = [{"class": "kitty", "initialClass": "kitty", "address": "0xa"},
           {"class": "Firefox", "initialClass": "firefox", "address": "0xb"}]
WINDOWS = [{"id": 7, "app_id": "kitty", "is_focused": True}, {"id": 9, "app_id": "firefox", "is_focused": False}]


def answer(stdout="", code=0):
    return mock.Mock(returncode=code, stdout=stdout, stderr="")


class Desktop(unittest.TestCase):
    """Calls are recorded, never made, so nothing here touches a real window."""

    def run_on(self, session, replies, *args, **kwargs):
        env = {k: v for k, v in os.environ.items()
               if k not in ("HYPRLAND_INSTANCE_SIGNATURE", "NIRI_SOCKET")}
        env.update(session)
        calls = []

        def fake(argv, **_):
            calls.append(argv)
            return replies(argv)

        with mock.patch.dict(os.environ, env, clear=True), mock.patch("subprocess.run", fake):
            try:
                compositor.control_window(*args, **kwargs)
            finally:
                self.calls = calls
        return calls


class HyprlandTests(Desktop):
    active = "0xb"
    session = {"HYPRLAND_INSTANCE_SIGNATURE": "x"}

    def replies(self, argv):
        if argv[1:] == ["clients", "-j"]:
            return answer(json.dumps(CLIENTS))
        if argv[1:] == ["activewindow", "-j"]:
            return answer(json.dumps({"address": self.active}))
        return answer()

    def dispatched(self):
        return [argv[2] for argv in self.calls if argv[1] == "dispatch"]

    def test_close_finds_the_app_first(self):
        self.run_on(self.session, self.replies, "close", "firefox")
        self.assertEqual(self.dispatched(), ['hl.dsp.focus({ window = "address:0xb" })',
                                             "hl.dsp.window.close()"])

    def test_close_without_an_app_closes_the_focused_window(self):
        self.run_on(self.session, self.replies, "close")
        self.assertEqual(self.dispatched(), ["hl.dsp.window.close()"])

    def test_nothing_closes_if_the_app_isnt_open(self):
        with self.assertRaisesRegex(ActionError, "isn't open"):
            self.run_on(self.session, self.replies, "close", "gimp")
        self.assertEqual(self.dispatched(), [])

    def test_nothing_closes_if_focus_didnt_move(self):
        self.active = "0xa"
        with self.assertRaisesRegex(ActionError, "bring"):
            self.run_on(self.session, self.replies, "close", "firefox")
        self.assertNotIn("hl.dsp.window.close()", self.dispatched())

    def test_app_names_never_reach_lua(self):
        with self.assertRaises(ActionError):
            self.run_on(self.session, self.replies, "focus", 'x" }) hl.dsp.exec_cmd("touch /tmp/x')
        self.assertEqual(self.dispatched(), [])

    def test_move(self):
        self.run_on(self.session, self.replies, "move", "firefox", 3)
        self.assertEqual(self.dispatched()[-1], 'hl.dsp.window.move({ workspace = "3", follow = false })')

    def test_classic_config_falls_back(self):
        def replies(argv):
            return answer(code=1) if argv[2].startswith("hl.") else self.replies(argv)
        self.run_on(self.session, replies, "close", "firefox")
        self.assertEqual(self.calls[-1], ["hyprctl", "dispatch", "killactive"])


class NiriTests(Desktop):
    session = {"NIRI_SOCKET": "/x"}

    def replies(self, argv):
        return answer(json.dumps(WINDOWS)) if "--json" in argv else answer()

    def test_focus(self):
        calls = self.run_on(self.session, self.replies, "focus", "FIREFOX")
        self.assertEqual(calls[-1], ["niri", "msg", "action", "focus-window", "--id", "9"])

    def test_close_defaults_to_the_focused_window(self):
        calls = self.run_on(self.session, self.replies, "close")
        self.assertEqual(calls[-1], ["niri", "msg", "action", "close-window", "--id", "7"])

    def test_move(self):
        calls = self.run_on(self.session, self.replies, "move", "firefox", 2)
        self.assertEqual(calls[-1], ["niri", "msg", "action", "move-window-to-workspace",
                                     "--window-id", "9", "--focus", "false", "2"])

    def test_focus_app_works_on_niri(self):
        replies = mock.Mock(side_effect=lambda argv, **_: self.replies(argv))
        with mock.patch.dict(os.environ, self.session, clear=True), mock.patch("subprocess.run", replies), \
                mock.patch("shutil.which", return_value="/bin/niri"):
            compositor.focus_app("firefox")
        self.assertEqual(replies.call_args[0][0][-2:], ["--id", "9"])

    def test_missing_app(self):
        with self.assertRaisesRegex(ActionError, "isn't open"):
            self.run_on(self.session, self.replies, "close", "gimp")
        self.assertEqual(len(self.calls), 1)


class ActionTests(Desktop):
    def call(self, **params):
        with mock.patch("cron_jovi.compositor.control_window") as control:
            load_actions()["window"].func(Context(lambda _: None), **params)
        return control

    def test_needs_what_it_needs(self):
        with self.assertRaisesRegex(ActionError, "focus needs"):
            self.call(op="focus")
        with self.assertRaisesRegex(ActionError, "move needs"):
            self.call(op="move", app="x")

    def test_passes_through(self):
        self.call(op="move", app="x", workspace=2).assert_called_once_with("move", "x", 2)

    def test_no_supported_desktop(self):
        with self.assertRaisesRegex(ActionError, "needs Hyprland or niri"):
            self.run_on({}, lambda argv: answer(), "close")


if __name__ == "__main__":
    unittest.main()
