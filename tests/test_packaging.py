import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cron_jovi import daemon, hotkeys, paths, schedule, update  # noqa: E402

IMAGE = "/home/me/Apps/CronJovi.AppImage"


class AppImageTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"APPIMAGE": IMAGE})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_saved_commands_use_the_file_not_its_mount_point(self):
        self.assertEqual(paths.self_command(), [IMAGE])
        self.assertEqual(hotkeys.command("demo"), [IMAGE, "run", "demo"])

    def test_it_points_people_to_the_release_page(self):
        self.assertIn("AppImage", update.blocked())

    def test_bundled_libraries_dont_reach_workflow_commands(self):
        env = {**os.environ, "PYTHONPATH": str(REPO), "LD_LIBRARY_PATH": "/bundled", "PYTHONHOME": sys.base_prefix,
               "PYTHONNOUSERSITE": "1"}
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            env.update(XDG_CONFIG_HOME=str(folder), XDG_STATE_HOME=str(folder))
            flows = folder / "cronjovi/workflows"
            flows.mkdir(parents=True)
            (flows / "env.yaml").write_text(
                f"name: Env\nsteps:\n  - action: shell\n    run: env > {folder}/seen\n")
            subprocess.run([sys.executable, "-m", "cron_jovi", "run", "env"], env=env, cwd="/", capture_output=True)
            seen = (folder / "seen").read_text()
        self.assertIn(f"APPIMAGE={IMAGE}", seen)
        for name in ("LD_LIBRARY_PATH", "PYTHONHOME"):
            self.assertNotIn(f"{name}=", seen)


class UnitTests(unittest.TestCase):
    def test_a_normal_install_starts_itself_with_python(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("APPIMAGE", None)
            self.assertEqual(paths.self_command(), [sys.executable, "-m", "cron_jovi"])

    def test_units_have_no_leftover_placeholders(self):
        command = "/x/y"
        self.assertIn("ExecStart=/x/y tick %i", schedule.TICK_SERVICE.format(command=command))
        self.assertIn("ExecStart=/x/y daemon", daemon.ENGINE_SERVICE.format(command=command))


if __name__ == "__main__":
    unittest.main()
