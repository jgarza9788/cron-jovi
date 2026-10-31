import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from cron_jovi import compositor, gallery, hotkeys, schedule, store  # noqa: E402
from cron_jovi.action_api import ActionError  # noqa: E402
from cron_jovi.workflow import WorkflowError, discover, load, parse  # noqa: E402

GOOD = "name: Shared\nsteps:\n  - action: shell\n    run: echo hi\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_STATE_HOME": str(self.root / "state"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.shared = self.root / "shared"
        self.shared.mkdir()


class GalleryTests(Base):
    def test_folder_lists_good_and_broken_files(self):
        (self.shared / "good.yaml").write_text(GOOD)
        (self.shared / "broken.yaml").write_text("name: x\nsteps:\n  - action: nope\n")
        (self.shared / "workflows").mkdir()
        (self.shared / "workflows/nested.yml").write_text(GOOD)
        entry = gallery.add(str(self.shared))
        found = {i["file"]: i for i in gallery.items(entry["id"])}
        self.assertEqual(set(found), {"good.yaml", "broken.yaml", "workflows/nested.yml"})
        self.assertTrue(found["good.yaml"]["runs_commands"])
        self.assertFalse(found["broken.yaml"]["ok"])

    def test_install_arrives_off_even_if_the_file_says_on(self):
        (self.shared / "good.yaml").write_text("enabled: true\n" + GOOD)
        entry = gallery.add(str(self.shared))
        slug = gallery.install(entry["id"], "good.yaml")
        path = self.root / f"config/cronjovi/workflows/{slug}.yaml"
        self.assertFalse(load(path).enabled)

    def test_symlinks_cannot_read_private_files(self):
        secret = self.root / "id_rsa"
        secret.write_text("PRIVATE KEY")
        (self.shared / "nice.yaml").symlink_to(secret)
        entry = gallery.add(str(self.shared))
        self.assertEqual(gallery.items(entry["id"]), [])
        with self.assertRaises(WorkflowError):
            gallery.read_item(entry["id"], "nice.yaml")

    def test_cannot_walk_out_of_the_gallery(self):
        (self.root / "outside.yaml").write_text(GOOD)
        entry = gallery.add(str(self.shared))
        with self.assertRaises(WorkflowError):
            gallery.read_item(entry["id"], "../outside.yaml")

    def test_huge_files_are_ignored(self):
        (self.shared / "big.yaml").write_text("x" * (gallery.MAX_FILE_BYTES + 1))
        entry = gallery.add(str(self.shared))
        self.assertEqual(gallery.items(entry["id"]), [])

    def test_only_safe_git_addresses(self):
        for source in ("ext::sh -c 'touch x'", "file:///etc", "--upload-pack=evil", "http://x/y.git", ""):
            with self.assertRaises(WorkflowError):
                gallery.add(source)
        for source in ("https://example.com/a/b.git", "git@example.com:a/b.git",
                       "ssh://git@example.com/a/b.git"):
            self.assertTrue(gallery.GIT_URL.match(source), source)

    def test_no_duplicates_and_remove(self):
        entry = gallery.add(str(self.shared))
        with self.assertRaisesRegex(WorkflowError, "already"):
            gallery.add(str(self.shared))
        gallery.remove(entry["id"])
        self.assertEqual(gallery.sources(), [])

    def test_real_git_clone_runs_no_hooks_and_updates(self):
        origin = self.root / "origin"
        origin.mkdir()
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run([*git, "init", "-q", str(origin)], check=True)
        (origin / "good.yaml").write_text(GOOD)
        subprocess.run([*git, "-C", str(origin), "add", "."], check=True)
        subprocess.run([*git, "-C", str(origin), "commit", "-qm", "x"], check=True)
        source = origin.as_uri()
        gallery._clone(source, gallery._cache("abc"))
        gallery._write([{"id": "abc", "kind": "git", "source": source}])
        self.assertEqual([i["file"] for i in gallery.items("abc")], ["good.yaml"])
        (origin / "more.yaml").write_text(GOOD)
        subprocess.run([*git, "-C", str(origin), "add", "."], check=True)
        subprocess.run([*git, "-C", str(origin), "commit", "-qm", "y"], check=True)
        gallery.update("abc")
        self.assertEqual(len(gallery.items("abc")), 2)


class HostileWorkflowTests(Base):
    def parse(self, text):
        return parse(yaml.safe_load(text), self.root / "x.yaml")

    def test_custom_shell_shows_in_review(self):
        wf = self.parse("name: a\nsteps:\n  - action: shell\n    run: nice\n    shell: /tmp/evil\n")
        self.assertEqual(store.shell_commands(wf.steps), ["/tmp/evil -c nice"])

    def test_review_lists_effects_without_commands(self):
        wf = self.parse(
            "name: a\nsteps:\n"
            "  - action: http\n    url: https://evil.example\n    method: post\n"
            "  - action: file\n    op: move\n    src: ~/.ssh/id_rsa\n    dest: /tmp/x\n"
            "  - if: {file_exists: ~/.ssh}\n    then:\n      - action: clipboard\n")
        found = " | ".join(store.effects(wf.steps))
        for text in ("POST request to https://evil.example", "Moves ~/.ssh/id_rsa", "Reads your clipboard", "~/.ssh exists"):
            self.assertIn(text, found)

    def test_negated_conditions_cannot_hide_a_command(self):
        wf = self.parse("name: a\nsteps:\n  - if:\n      not:\n        not:\n          command: curl evil\n")
        self.assertEqual(store.shell_commands(wf.steps), ["curl evil"])

    def test_line_breaks_cannot_reach_generated_config(self):
        for text in ('hotkey: "Super+F\\nexec-once = evil"', 'schedule: "daily\\nUnit=evil.service"'):
            with self.assertRaises(WorkflowError):
                self.parse(f"name: a\ntrigger:\n  {text}\nsteps: []\n")

    def test_hotkey_key_must_be_a_key_name(self):
        for bad in ("Super+F, exec, evil", "Super+F;x", "Super+"):
            with self.assertRaises(WorkflowError):
                hotkeys.parse(bad)
        self.assertEqual(hotkeys.parse("Super+XF86AudioPlay")[1], "XF86AudioPlay")

    def test_name_is_flattened_to_one_line(self):
        wf = self.parse('name: "x\\nUnit=evil.service"\nsteps: []\n')
        self.assertEqual(wf.name, "x Unit=evil.service")
        self.assertEqual(len(schedule.TIMER.format(name=wf.name, calendar="daily", slug="s").splitlines()), 11)

    def test_alias_bomb_is_refused_quickly(self):
        layers = "".join(
            f"z{i}: &a{i}\n" + "".join(f"  - {{repeat: 1, steps: *a{i - 1}}}\n" for _ in range(9))
            for i in range(1, 9))
        text = f"name: b\nz0: &a0\n  - {{action: wait, duration: 1}}\n{layers}steps: *a8\n"
        started = time.monotonic()
        with self.assertRaisesRegex(WorkflowError, "too many steps"):
            self.parse(text)
        self.assertLess(time.monotonic() - started, 2)

    def test_deep_nesting_is_refused(self):
        steps = [{"action": "wait", "duration": 1}]
        for _ in range(40):
            steps = [{"repeat": 1, "steps": steps}]
        with self.assertRaisesRegex(WorkflowError, "nested too deeply"):
            parse({"name": "x", "steps": steps}, self.root / "x.yaml")

    def test_unsafe_file_names_are_reported(self):
        folder = self.root / "config/cronjovi/workflows"
        folder.mkdir(parents=True)
        (folder / "a b;x.yaml").write_text("name: q\nsteps: []\n")
        workflows, errors = discover()
        self.assertEqual(workflows, [])
        self.assertIn("rename it", errors[0])


class CompositorTests(unittest.TestCase):
    def run_with(self, results, env):
        calls = []

        def fake(argv, **_):
            calls.append(argv)
            return results.pop(0)

        with mock.patch.dict(os.environ, env, clear=False), mock.patch("subprocess.run", fake):
            compositor.focus_workspace(3)
        return calls

    def test_lua_hyprland_uses_lua(self):
        calls = self.run_with([mock.Mock(returncode=0)], {"HYPRLAND_INSTANCE_SIGNATURE": "x"})
        self.assertEqual(calls, [["hyprctl", "dispatch", 'hl.dsp.focus({ workspace = "3" })']])

    def test_older_hyprland_falls_back(self):
        calls = self.run_with([mock.Mock(returncode=7), mock.Mock(returncode=0)],
                              {"HYPRLAND_INSTANCE_SIGNATURE": "x"})
        self.assertEqual(calls[1], ["hyprctl", "dispatch", "workspace", "3"])

    def test_both_failing_is_an_error(self):
        with self.assertRaises(ActionError):
            self.run_with([mock.Mock(returncode=7, stdout="no", stderr=""),
                           mock.Mock(returncode=7, stdout="no", stderr="")],
                          {"HYPRLAND_INSTANCE_SIGNATURE": "x"})

    def test_niri(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
            calls = self.run_with([mock.Mock(returncode=0)], {"NIRI_SOCKET": "/x"})
        self.assertEqual(calls, [["niri", "msg", "action", "focus-workspace", "3"]])

    def test_unsupported_desktop_says_so(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("HYPRLAND_INSTANCE_SIGNATURE", "NIRI_SOCKET")}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ActionError, "needs Hyprland or niri"):
                compositor.focus_workspace(1)


if __name__ == "__main__":
    unittest.main()
