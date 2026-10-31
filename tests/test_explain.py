import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from cron_jovi.action_api import ActionError  # noqa: E402
from cron_jovi.explain import explain, table  # noqa: E402

SHELL = ActionError("bash exited 23", 23)


# Real output from the programs named, captured from commands that really failed.
CORPUS = [
    ("cat x", 1, "cat: nope.txt: No such file or directory", "Can't find nope.txt"),
    ("cp a b", 1, "cp: cannot stat 'nodir': No such file or directory", "Can't find nodir"),
    ("mkdir a", 1, "mkdir: cannot create directory ‘exists’: File exists", "exists already exists"),
    ("touch a", 1, "touch: cannot touch 'locked/x': Permission denied", "permission to use locked/x"),
    ("sh", 1, "bash: line 1: locked/y: Permission denied", "permission to use locked/y"),
    ("rmdir a", 1, "rmdir: failed to remove 'full': Directory not empty", "full still has files"),
    ("cd a", 1, "bash: line 1: cd: file.txt: Not a directory", "file.txt is a file"),
    ("cat a", 1, "cat: exists: Is a directory", "exists is a folder"),
    ("zip x", 15, "zip I/O error: No such file or directory", "can't be found"),
    ("tar xf a", 2, "tar: nope.tar: Cannot open: No such file or directory", "Can't find nope.tar"),
    ("tar xf a", 2, "tar: This does not look like a tar archive", "damaged"),
    ("gzip -d a", 2, "gzip: file.txt: unknown suffix -- ignored", "isn't compressed"),
    ("jq . a", 5, "jq: parse error: Invalid numeric literal at line 2, column 0", "valid JSON"),
    ("jq . a", 3, "jq: 1 compile error", "filter has a typing mistake"),
    ("node a", 1, "Error: Cannot find module '/tmp/x/nope.js'", "Can't find /tmp/x/nope.js"),
    ("node a", 1, "Error: Cannot find module 'left-pad'", "Node package left-pad"),
    ("./x.sh", 126, "bash: line 1: ./x.sh: Permission denied", "marked as a program"),
    ("pacman -S a", 1, "error: you cannot perform this operation unless you are root.", "administrator"),
    ("docker ps", 1, "permission denied while trying to connect to the docker API", "use Docker"),
    ("kill 1", 1, "bash: line 1: kill: (999999) - No such process", "isn't running"),
    ("curl x", 1, 'curl: (1) Protocol "not-a-url" not supported', "address isn't written"),
    ("curl x", 6, "", "Can't find that website"),
    ("rsync a b", 23, "", "Some files couldn't be copied"),
    ("sudo rsync a b", 24, "", "disappeared"),
    ("grep a b", 1, "", "wasn't found"),
    ("cargo build", 101, "error: could not find `Cargo.toml` in `.`", "Can't find"),
    ("sleep x", 1, "Try 'sleep --help' for more information.", "isn't written correctly"),
    ("awk x", 1, "awk: cmd. line:1: ^ unexpected newline or end of string", "typing mistake"),
    ("make x", 2, "make: *** No rule to make target 'nothing'.  Stop.", "nothing to build"),
    ("systemctl x", 4, "Unit nope.service could not be found.", "no service called nope.service"),
    ("sudo -n x", 1, "sudo: a password is required", "needs your password"),
]
HARMLESS = [
    "CPU usage: 40%",
    "OpenSSL 3.0 loaded",
    "copied the file named no_ssl_here.txt",
    "disk usage: fine",
]


class ExplainTests(unittest.TestCase):
    def says(self, output, failure=SHELL):
        return explain(failure, output.splitlines())

    def test_real_failures(self):
        for command, code, output, expected in CORPUS:
            failure = ActionError(f"bash exited {code}", code)
            failure.step = command
            self.assertIn(expected, explain(failure, output.splitlines()), (command, output))

    def test_ordinary_output_is_not_mistaken_for_a_cause(self):
        failure = ActionError("bash exited 9", 9)
        failure.step = "ls"
        for line in HARMLESS:
            self.assertIn("It said:", explain(failure, [line]), line)

    def test_only_output_near_the_failure_counts(self):
        early = ["cp: cannot stat 'old': No such file or directory"] + ["fine"] * 40
        failure = ActionError("bash exited 9", 9)
        self.assertNotIn("old", explain(failure, early))

    def test_unknown_failures_quote_the_program(self):
        failure = ActionError("bash exited 9", 9)
        failure.step = "ls x"
        self.assertEqual(explain(failure, ["", "the flux capacitor overheated", ""]),
                         "ls ran into a problem and stopped. It said: “the flux capacitor overheated”")
        self.assertEqual(explain(failure, []), "ls ran into a problem and stopped without saying why.")

    def test_table_stays_friendly(self):
        rules = table()
        said = [str(r["say"]) for r in rules["output"] + rules["messages"]]
        said += [str(r.get("else", "")) for r in rules["output"]]
        said += [str(v) for codes in rules["exit_codes"].values() for v in codes.values()]
        said += [str(v) for v in rules["any_exit"].values()]
        self.assertGreater(len(said), 120)
        for text in said:
            self.assertNotRegex(text, r"(?i)\bexit(ed)?\b|\berrno\b|\bstderr\b|\bstdout\b|\bsegfault", text)

    def test_your_own_entries_come_first(self):
        with tempfile.TemporaryDirectory() as folder:
            own = Path(folder) / "cronjovi"
            own.mkdir()
            (own / "errors.yaml").write_text(
                "output:\n  - match: permission denied\n    say: Ask Sam for access.\n"
                "  - match: '[bad regex'\n    say: never\n"
                "exit_codes:\n  mytool:\n    4: My tool needs its dongle.\n")
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": folder}):
                table.cache_clear()
                self.addCleanup(table.cache_clear)
                self.assertEqual(explain(SHELL, ["cp: x: Permission denied"]), "Ask Sam for access.")
                failure = ActionError("bash exited 4", 4)
                failure.step = "mytool --go"
                self.assertEqual(explain(failure, []), "My tool needs its dongle.")
                self.assertIn("no space", explain(SHELL, ["No space left on device"]))

    def test_the_design_docs_rsync_failure(self):
        text = self.says('rsync: [receiver] mkdir "/mnt/backup/Documents" failed: Permission denied (13)\n'
                         "rsync error: error in file IO (code 11) at main.c(757)")
        self.assertEqual(text, "Cron Jovi doesn't have permission to use /mnt/backup/Documents.")

    def test_missing_backup_folder(self):
        text = self.says('rsync: change_dir "/mnt/backup" failed: No such file or directory (2)')
        self.assertIn("Can't find /mnt/backup", text)
        self.assertIn("plugged in", text)

    def test_plain_shell_errors(self):
        self.assertIn("Can't find ~/x.txt", self.says("cat: ~/x.txt: No such file or directory"))
        self.assertIn("no space left", self.says("cp: error writing '/mnt/a': No space left on device"))
        self.assertIn("read-only", self.says("touch: cannot touch '/mnt/a': Read-only file system"))
        self.assertIn("internet", self.says("curl: (6) Could not resolve host: example.com"))
        self.assertIn("isn't installed: frob", self.says("bash: line 1: frob: command not found"))

    def test_no_numbers_or_jargon_reach_people(self):
        for output in ('mkdir "/a" failed: Permission denied (13)', "something odd happened", ""):
            text = self.says(output)
            self.assertNotRegex(text, r"exit|exited|\(13\)|errno|bash")

    def test_unknown_failure_names_the_program(self):
        failure = ActionError("bash exited 3", 3)
        failure.step = "ls -a a b"
        self.assertIn("ls ran into a problem", explain(failure, ["weird output"]))

    def test_shell_words_are_not_called_programs(self):
        failure = ActionError("bash exited 3", 3)
        failure.step = "exit 3"
        self.assertTrue(explain(failure, []).startswith("A command ran into a problem"))

    def test_action_messages(self):
        cases = {
            ("playerctl not found", 127): "This step needs playerctl, which isn't installed.",
            ("timed out after 10s", 124): "This step took longer than 10 seconds, so it was stopped.",
            ("GET https://x.example returned 404", 1): "That web page wasn't found. Check the address.",
            ("GET https://x.example returned 503", 1): "https://x.example is having problems right now. Try again later.",
            ("timed out after 1s", 124): "This step took longer than 1 second, so it was stopped.",
            ("undefined variable: clip", 1): "A step uses clip, but nothing has set it yet. Check the steps before it.",
        }
        for (message, code), expected in cases.items():
            self.assertEqual(explain(ActionError(message, code), []), expected)

    def test_a_clear_message_passes_through(self):
        self.assertEqual(explain(ActionError("no adjustable screen found", 127), []),
                         "No adjustable screen found")

    def test_commands_echoed_in_the_log_are_not_read_as_errors(self):
        lines = ['$ grep "Permission denied" notes.txt', "21:00:00 fail grep: bash exited 1 (exit 1)"]
        self.assertNotIn("permission", explain(ActionError("bash exited 1", 1), lines))


if __name__ == "__main__":
    unittest.main()
