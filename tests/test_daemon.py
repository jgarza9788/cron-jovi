import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cron_jovi import daemon  # noqa: E402
from cron_jovi.engine import run_workflow  # noqa: E402
from cron_jovi.history import History  # noqa: E402
from cron_jovi.workflow import Trigger, Workflow, WorkflowError, load  # noqa: E402

try:
    import watchdog  # noqa: F401
except ImportError:
    watchdog = None
try:
    import flask
except ImportError:
    flask = None


def workflow(slug="demo", **trigger):
    return Workflow(slug, slug.title(), Path("x"), trigger=Trigger(**trigger))


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
        self.fired = []

    def fire(self, wf, trigger, variables):
        self.fired.append((wf.slug, trigger, variables))


class TriggerParsingTests(Base):
    def load(self, trigger):
        path = self.root / "t.yaml"
        path.write_text(f"name: x\ntrigger:\n{trigger}\nsteps: []\n")
        return load(path).trigger

    def test_file_shorthand_and_defaults(self):
        trigger = self.load("  file: ~/Downloads")
        self.assertEqual(trigger.file, {"path": "~/Downloads", "pattern": "*",
                                        "events": ["created"], "recursive": False})
        self.assertTrue(trigger.has_events())

    def test_full_forms(self):
        trigger = self.load("  file:\n    path: /tmp\n    pattern: '*.pdf'\n    events: [created, moved]\n"
                            "  device: SanDisk\n  battery: 15\n  power: unplugged\n  webhook: true")
        self.assertEqual(trigger.file["pattern"], "*.pdf")
        self.assertEqual(trigger.device, {"match": "SanDisk", "event": "added"})
        self.assertEqual(trigger.battery, {"below": 15})

    def test_rejects_bad_values(self):
        for text, message in (
            ("  file:\n    pattern: x", "needs a path"),
            ("  file:\n    path: /x\n    events: [exploded]", "file events"),
            ("  battery: 150", "1 to 99"),
            ("  battery: lots", "1 to 99"),
            ("  power: sideways", "power must be"),
            ("  device:\n    event: wiggled", "device event"),
        ):
            with self.assertRaisesRegex(WorkflowError, message):
                self.load(text)

    def test_hotkeys_alone_need_no_engine(self):
        self.assertFalse(workflow(hotkey="Super+A", schedule="every 2h").trigger.has_events())


class FileTests(Base):
    def spec(self, **extra):
        return {"path": "/x", "pattern": "*", "events": ["created"], "recursive": False, **extra}

    def test_matching(self):
        self.assertTrue(daemon.file_matches(self.spec(), "/x/a.pdf", "created"))
        self.assertFalse(daemon.file_matches(self.spec(), "/x/a.pdf", "deleted"))
        self.assertFalse(daemon.file_matches(self.spec(pattern="*.png"), "/x/a.pdf", "created"))

    def test_partial_downloads_are_ignored(self):
        for name in ("a.pdf.part", "a.crdownload", "a.tmp", ".hidden", "a~"):
            self.assertFalse(daemon.file_matches(self.spec(), f"/x/{name}", "created"), name)

    def test_a_file_being_written_fires_once_after_it_settles(self):
        wf = workflow(file=self.spec())
        watch = daemon.FileWatch(wf, self.fire, settle=0.1)
        for _ in range(5):
            watch.on_event("created", "/x/big.iso")
            time.sleep(0.02)
        self.assertEqual(self.fired, [])
        time.sleep(0.25)
        self.assertEqual(len(self.fired), 1)
        self.assertEqual(self.fired[0][2]["file"]["name"], "big.iso")

    @unittest.skipIf(watchdog is None, "watchdog is not installed")
    def test_real_inotify(self):
        folder = self.root / "watched"
        folder.mkdir()
        spec = self.spec(path=str(folder), pattern="*.txt")
        watch = daemon.FileWatch(workflow(file=spec), self.fire, settle=0.05)
        observer, problems = daemon.start_file_watches([watch])
        self.addCleanup(observer.stop)
        self.assertEqual(problems, [])
        (folder / "skip.png").write_text("x")
        (folder / "keep.txt").write_text("x")
        deadline = time.monotonic() + 3
        while not self.fired and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual([f[2]["file"]["name"] for f in self.fired], ["keep.txt"])

    @unittest.skipIf(watchdog is None, "watchdog is not installed")
    def test_missing_folder_is_reported_not_fatal(self):
        spec = self.spec(path=str(self.root / "gone"))
        observer, problems = daemon.start_file_watches([daemon.FileWatch(workflow(file=spec), self.fire)])
        self.addCleanup(observer.stop)
        self.assertIn("Folder not found", problems[0][1])


class LimiterTests(unittest.TestCase):
    def test_stops_a_runaway_and_reports_once(self):
        now = [0.0]
        limiter = daemon.Limiter(limit=2, window=60, clock=lambda: now[0])
        self.assertEqual(limiter.allow("a"), (True, False))
        self.assertEqual(limiter.allow("a"), (True, False))
        self.assertEqual(limiter.allow("a"), (False, True))
        self.assertEqual(limiter.allow("a"), (False, False))
        self.assertEqual(limiter.allow("b"), (True, False))
        now[0] = 61
        self.assertEqual(limiter.allow("a"), (True, False))


SAMPLE = """UDEV  [100.1] add /devices/pci/usb1/1-1 (usb)
ACTION=add
DEVTYPE=usb_device
ID_MODEL=Ultra_Fit
ID_VENDOR=SanDisk

UDEV  [100.2] add /devices/pci/usb1/1-1/1-1:1.0 (usb)
ACTION=add
DEVTYPE=usb_interface
ID_MODEL=Ultra_Fit

UDEV  [100.3] remove /devices/pci/usb1/1-1 (usb)
ACTION=remove
DEVTYPE=usb_device
ID_MODEL=Ultra_Fit
ID_VENDOR=SanDisk

"""


class DeviceTests(unittest.TestCase):
    def events(self):
        return list(daemon.parse_udev(SAMPLE.splitlines(keepends=True)))

    def test_parses_each_block(self):
        self.assertEqual([e["ACTION"] for e in self.events()], ["add", "add", "remove"])

    def test_one_plug_in_fires_once(self):
        spec = {"match": "", "event": "added"}
        self.assertEqual(sum(daemon.device_matches(spec, e) for e in self.events()), 1)

    def test_match_is_case_insensitive_and_ignores_underscores(self):
        add = self.events()[0]
        self.assertTrue(daemon.device_matches({"match": "ultra fit", "event": "added"}, add))
        self.assertTrue(daemon.device_matches({"match": "sandisk", "event": "added"}, add))
        self.assertFalse(daemon.device_matches({"match": "kingston", "event": "added"}, add))

    def test_removal(self):
        events = self.events()
        spec = {"match": "", "event": "removed"}
        self.assertTrue(daemon.device_matches(spec, events[2]))
        self.assertFalse(daemon.device_matches(spec, events[0]))

    def test_friendly_name(self):
        self.assertEqual(daemon.device_name(self.events()[0]), "Ultra Fit")


class PowerTests(Base):
    def supply(self, name, **files):
        path = self.root / "ps" / name
        path.mkdir(parents=True, exist_ok=True)
        for key, value in files.items():
            (path / key).write_text(f"{value}\n")

    def read(self):
        return daemon.read_power(self.root / "ps")

    def test_wireless_mouse_is_not_the_battery(self):
        self.supply("hidpp_battery_0", type="Battery", scope="Device", capacity=5, status="Discharging")
        self.assertEqual(self.read()["percent"], None)

    def test_laptop_battery(self):
        self.supply("hidpp_battery_0", type="Battery", scope="Device", capacity=5, status="Discharging")
        self.supply("BAT0", type="Battery", capacity=40, status="Discharging")
        self.supply("AC", type="Mains", online=0)
        self.assertEqual(self.read(), {"percent": 40, "discharging": True, "plugged": False})

    def test_fires_once_per_drop_and_rearms(self):
        wf = workflow(battery={"below": 15})
        watch = daemon.PowerWatch([wf], self.fire)
        low = {"percent": 14, "discharging": True, "plugged": False}
        watch.check({**low, "percent": 50})
        watch.check(low)
        watch.check({**low, "percent": 12})
        self.assertEqual(len(self.fired), 1)
        watch.check({**low, "percent": 80})
        watch.check(low)
        self.assertEqual(len(self.fired), 2)

    def test_charging_at_low_battery_does_not_fire(self):
        watch = daemon.PowerWatch([workflow(battery={"below": 15})], self.fire)
        watch.check({"percent": 5, "discharging": False, "plugged": True})
        self.assertEqual(self.fired, [])

    def test_power_fires_on_change_not_at_startup(self):
        watch = daemon.PowerWatch([workflow(power="unplugged")], self.fire)
        on = {"percent": 90, "discharging": False, "plugged": True}
        off = {"percent": 90, "discharging": True, "plugged": False}
        watch.check(off)
        self.assertEqual(self.fired, [])
        watch.check(on)
        watch.check(off)
        self.assertEqual(self.fired[0][2], {"power": {"state": "unplugged"}})


class SessionTests(Base):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_login_fires_once_per_session_despite_engine_restarts(self):
        wf = workflow(login=True)
        daemon.fire_login([wf], self.fire)
        daemon.fire_login([wf], self.fire)
        self.assertEqual(len(self.fired), 1)
        daemon.fire_login([wf, workflow("new", login=True)], self.fire)
        self.assertEqual([f[0] for f in self.fired], ["demo", "new"])

    def test_wake_signal_parsing(self):
        line = "/org/freedesktop/login1: org.freedesktop.login1.Manager.PrepareForSleep (%s)"
        self.assertTrue(daemon.woke_up(line % "false"))
        self.assertFalse(daemon.woke_up(line % "true"))
        self.assertFalse(daemon.woke_up("something else false"))

    def test_login_and_wake_need_the_engine(self):
        self.assertTrue(workflow(login=True).trigger.has_events())
        self.assertTrue(workflow(wake=True).trigger.has_events())
        self.assertNotEqual(daemon.fingerprint([workflow(login=True)]), daemon.fingerprint([workflow(wake=True)]))


@unittest.skipIf(flask is None, "Flask is not installed")
class WebhookTests(Base):
    def client(self):
        return daemon.webhook_app([workflow(webhook=True)], self.fire).test_client()

    def test_needs_the_right_token(self):
        good = daemon.webhook_token("demo")
        client = self.client()
        self.assertEqual(client.post(f"/hook/demo/{good}", json={"a": 1}).status_code, 202)
        self.assertEqual(self.fired[0][2], {"webhook": {"body": {"a": 1}}})
        self.assertEqual(client.post("/hook/demo/wrong").status_code, 404)
        self.assertEqual(client.post(f"/hook/other/{good}").status_code, 404)
        self.assertEqual(client.get(f"/hook/demo/{good}").status_code, 405)
        self.assertEqual(len(self.fired), 1)

    def test_token_file_is_private_and_stable(self):
        first = daemon.webhook_token("demo")
        self.assertEqual(daemon.webhook_token("demo"), first)
        mode = (self.root / "state/cronjovi/webhooks.json").stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_oversized_body_is_refused(self):
        good = daemon.webhook_token("demo")
        response = self.client().post(f"/hook/demo/{good}", data="x" * (daemon.MAX_WEBHOOK_BYTES + 1))
        self.assertEqual(response.status_code, 413)


class EngineTests(Base):
    def test_trigger_values_reach_the_workflow_safely(self):
        marker = self.root / "pwned"
        wf = Workflow("demo", "Demo", Path("x"), steps=[
            {"action": "shell", "run": "echo {{ file.name }}"}])
        history = History()
        self.addCleanup(history.db.close)
        evil = f"a; touch {marker}"
        run_workflow(wf, history, "file", variables={"file": {"name": evil}})
        self.assertFalse(marker.exists())
        self.assertIn(evil, history.recent("demo", 1)[0]["output"])

    def test_runaway_is_recorded_once_and_a_spawn_failure_is_survived(self):
        spawned = []
        engine = daemon.Engine(spawn=lambda *a: spawned.append(a))
        engine.limiter = daemon.Limiter(limit=1)
        wf = workflow()
        for _ in range(4):
            engine.fire(wf, "file", {})
        self.assertEqual(len(spawned), 1)
        history = History()
        self.addCleanup(history.db.close)
        rows = history.recent("demo")
        self.assertEqual(len(rows), 1)
        self.assertIn("triggers in a minute", rows[0]["note"])
        engine = daemon.Engine(spawn=mock.Mock(side_effect=OSError("no systemd")))
        engine.fire(wf, "file", {})

    def test_fingerprint_ignores_steps_and_disabled_workflows(self):
        a = workflow(file={"path": "/x"})
        b = workflow(file={"path": "/x"})
        b.steps = [{"action": "wait", "duration": 1}]
        self.assertEqual(daemon.fingerprint([a]), daemon.fingerprint([b]))
        off = workflow(file={"path": "/x"})
        off.enabled = False
        self.assertEqual(daemon.fingerprint([off]), "[]")

    def test_engine_only_runs_while_needed(self):
        calls = []

        def fake(*args):
            calls.append(args)
            return mock.Mock(returncode=0, stdout="active\n", stderr="")

        unit = self.root / "config/systemd/user" / daemon.ENGINE_UNIT
        with mock.patch.object(daemon, "_systemctl", fake):
            self.assertEqual(daemon.sync_engine([workflow(hotkey="Super+A")]), [])
            self.assertFalse(unit.exists())
            self.assertEqual(calls, [])
            daemon.sync_engine([workflow(webhook=True)])
            self.assertTrue(unit.exists())
            self.assertIn(("restart", daemon.ENGINE_UNIT), calls)
            calls.clear()
            daemon.sync_engine([workflow(webhook=True)])
            self.assertNotIn(("restart", daemon.ENGINE_UNIT), calls)
            daemon.sync_engine([workflow(hotkey="Super+A")])
            self.assertFalse(unit.exists())
            self.assertIn(("disable", "--now", daemon.ENGINE_UNIT), calls)


if __name__ == "__main__":
    unittest.main()
