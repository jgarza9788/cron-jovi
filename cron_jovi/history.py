"""Run history. A skipped run still gets a row, with the reason in `note`."""

import sqlite3
import time

from . import paths

KEEP_RUNS = 500  # per workflow; an every-minute job would otherwise grow forever

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY,
    workflow     TEXT NOT NULL,
    trigger      TEXT NOT NULL,
    scheduled_at REAL,
    started_at   REAL,
    finished_at  REAL,
    status       TEXT NOT NULL,
    exit_code    INTEGER,
    note         TEXT NOT NULL DEFAULT '',
    output       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS runs_by_workflow ON runs (workflow, id);
CREATE TABLE IF NOT EXISTS schedule_state (
    workflow TEXT PRIMARY KEY,
    spec     TEXT NOT NULL,
    next_due REAL NOT NULL
);
"""


class History:
    def __init__(self, path=None):
        path = path or paths.history_db()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)  # run output can hold anything a command printed
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        path.chmod(0o600)

    def close(self) -> None:
        self.db.close()

    def start(self, workflow, trigger, scheduled_at=None, note="") -> int:
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO runs (workflow, trigger, scheduled_at, started_at, status, note)"
                " VALUES (?, ?, ?, ?, 'running', ?)",
                (workflow, trigger, scheduled_at, time.time(), note),
            )
        return cursor.lastrowid

    def finish(self, run_id, status, exit_code, note, output) -> None:
        with self.db:
            self.db.execute(
                "UPDATE runs SET finished_at=?, status=?, exit_code=?, note=?, output=?"
                " WHERE id=?",
                (time.time(), status, exit_code, note, output, run_id),
            )

    def prune(self, workflow, keep=KEEP_RUNS) -> None:
        with self.db:
            self.db.execute(
                "DELETE FROM runs WHERE workflow=? AND status != 'running' AND id NOT IN"
                " (SELECT id FROM runs WHERE workflow=? ORDER BY id DESC LIMIT ?)",
                (workflow, workflow, keep),
            )

    def clear(self, workflow=None) -> None:
        where, args = ("AND workflow=?", [workflow]) if workflow else ("", [])
        with self.db:
            self.db.execute(f"DELETE FROM runs WHERE status != 'running' {where}", args)
        self.db.execute("VACUUM")  # deleted output shouldn't linger in the file

    def skip(self, workflow, trigger, scheduled_at, note) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO runs (workflow, trigger, scheduled_at, status, note)"
                " VALUES (?, ?, ?, 'skipped', ?)",
                (workflow, trigger, scheduled_at, note),
            )

    def close_abandoned(self, workflow) -> None:
        """Call while holding the workflow's lock: any 'running' row is a dead run."""
        with self.db:
            self.db.execute(
                "UPDATE runs SET status='stopped', note='Run was killed before it finished'"
                " WHERE workflow=? AND status='running'",
                (workflow,),
            )

    def recent(self, workflow=None, limit=20) -> list:
        where, args = ("WHERE workflow=?", [workflow]) if workflow else ("", [])
        return self.db.execute(
            f"SELECT * FROM runs {where} ORDER BY id DESC LIMIT ?", [*args, limit]
        ).fetchall()

    def get(self, run_id):
        return self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()

    def next_due(self, workflow, spec) -> float | None:
        row = self.db.execute(
            "SELECT next_due FROM schedule_state WHERE workflow=? AND spec=?", (workflow, spec)
        ).fetchone()
        return row["next_due"] if row else None

    def set_next_due(self, workflow, spec, next_due) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO schedule_state (workflow, spec, next_due) VALUES (?, ?, ?)",
                (workflow, spec, next_due),
            )

    def forget_schedule(self, workflow) -> None:
        with self.db:
            self.db.execute("DELETE FROM schedule_state WHERE workflow=?", (workflow,))
