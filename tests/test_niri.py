"""Checks against the real niri program. They need no session, and are skipped without niri."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cron_jovi import hotkeys  # noqa: E402
from cron_jovi.workflow import parse  # noqa: E402


@unittest.skipUnless(shutil.which("niri"), "needs niri")
class RealNiriTests(unittest.TestCase):
    def help_for(self, action):
        done = subprocess.run(["niri", "msg", "action", action, "--help"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_generated_hotkeys_are_valid_config(self):
        rules = [parse({"name": "One", "trigger": {"hotkey": "Super+Shift+F"}, "steps": []}, Path("one.yaml")),
                 parse({"name": "Two", "trigger": {"hotkey": "Ctrl+Alt+T"}, "steps": []}, Path("two.yaml"))]
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.kdl"
            config.write_text(hotkeys.niri_kdl(rules))
            done = subprocess.run(["niri", "validate", "-c", str(config)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_the_flags_we_use_exist(self):
        self.assertIn("--id", self.help_for("focus-window"))
        self.assertIn("--id", self.help_for("close-window"))
        move = self.help_for("move-window-to-workspace")
        self.assertIn("--window-id", move)
        self.assertIn("--focus", move)
        self.help_for("focus-workspace")

    def test_windows_can_be_listed_as_json(self):
        done = subprocess.run(["niri", "msg", "--help"], capture_output=True, text=True)
        self.assertIn("--json", done.stdout)
        self.assertIn("windows", done.stdout)


if __name__ == "__main__":
    unittest.main()
