import json
import os
import sqlite3
import time
import uuid
import zlib
from contextlib import contextmanager
from pathlib import Path


def default_path():
    return os.environ.get(
        "VIRTUAL_WORLD_DB", str(Path.cwd() / ".data" / "world.sqlite3")
    )


def encode(value):
    return zlib.compress(json.dumps(value, separators=(",", ":")).encode(), 1)


def decode(value):
    return json.loads(zlib.decompress(value))


def new_id():
    return uuid.uuid4().hex[:16]


class Store:
    def __init__(self, path=None):
        self.path = str(path or default_path())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,name TEXT,created REAL,config TEXT,world BLOB,day INTEGER,status TEXT,parent TEXT,branch_day INTEGER,experiment TEXT,metrics TEXT);
            CREATE TABLE IF NOT EXISTS snapshots(run TEXT,day INTEGER,state BLOB,PRIMARY KEY(run,day));
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT,created REAL,status TEXT,spec TEXT,data TEXT);
            CREATE INDEX IF NOT EXISTS run_experiment ON runs(experiment);
            CREATE TABLE IF NOT EXISTS research_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,job TEXT,created REAL,kind TEXT,message TEXT,data TEXT);
            CREATE INDEX IF NOT EXISTS research_events_cursor ON research_events(job,seq);
            """)
            if "engine_version" not in [
                r["name"] for r in db.execute("PRAGMA table_info(runs)")
            ]:
                db.execute(
                    "ALTER TABLE runs ADD COLUMN engine_version TEXT NOT NULL DEFAULT '1.0.0'"
                )

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.path, timeout=60)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def create_run(
        self,
        id,
        name,
        config,
        world,
        state,
        parent=None,
        branch_day=None,
        experiment=None,
    ):
        from .engine import ENGINE_VERSION

        with self.db() as db:
            db.execute(
                "INSERT INTO runs(id,name,created,config,world,day,status,parent,branch_day,experiment,metrics,engine_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    id,
                    name,
                    time.time(),
                    json.dumps(config),
                    encode(world),
                    state["day"],
                    "ready",
                    parent,
                    branch_day,
                    experiment,
                    None,
                    ENGINE_VERSION,
                ),
            )
            db.execute(
                "INSERT INTO snapshots VALUES(?,?,?)", (id, state["day"], encode(state))
            )

    def run(self, id):
        with self.db() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (id,)).fetchone()
        if row is None:
            raise KeyError("Run not found")
        r = dict(row)
        r["config"] = json.loads(r["config"])
        r["world"] = decode(r["world"])
        r["metrics"] = json.loads(r["metrics"]) if r["metrics"] else None
        return r

    def list_runs(self, limit=100, experiment=None, offset=0):
        with self.db() as db:
            rows = db.execute(
                "SELECT id,name,created,day,status,parent,branch_day,experiment,config,metrics FROM runs "
                + ("WHERE experiment=? " if experiment else "")
                + "ORDER BY (experiment IS NULL) DESC,created DESC LIMIT ? OFFSET ?",
                ((experiment, limit, offset) if experiment else (limit, offset)),
            ).fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r["config"] = json.loads(r["config"])
            r["metrics"] = json.loads(r["metrics"]) if r["metrics"] else None
            result.append(r)
        return result

    def snapshot(self, id, day=None):
        with self.db() as db:
            if day is None:
                row = db.execute(
                    "SELECT state FROM snapshots WHERE run=? ORDER BY day DESC LIMIT 1",
                    (id,),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT state FROM snapshots WHERE run=? AND day=?", (id, day)
                ).fetchone()
        if row:
            return decode(row["state"])
        r = self.run(id)
        if r["parent"] and day is not None and day < r["branch_day"]:
            return self.snapshot(r["parent"], day)
        raise KeyError("Checkpoint not found")

    def effective_config(self, id, day):
        r = self.run(id)
        if r["parent"] and day < r["branch_day"]:
            return self.effective_config(r["parent"], day)
        return r["config"]

    def save_states(self, id, states, status, metrics):
        rows = [(id, s["day"], encode(s)) for s in states]
        with self.db() as db:
            db.executemany("INSERT OR REPLACE INTO snapshots VALUES(?,?,?)", rows)
            if states:
                db.execute(
                    "UPDATE runs SET day=?,status=?,metrics=? WHERE id=?",
                    (states[-1]["day"], status, json.dumps(metrics), id),
                )

    def create_job(self, kind, spec, data=None):
        id = new_id()
        with self.db() as db:
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,?)",
                (
                    id,
                    kind,
                    time.time(),
                    "queued",
                    json.dumps(spec),
                    json.dumps(data or {}),
                ),
            )
        return self.job(id)

    def job(self, id):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (id,)).fetchone()
        if row is None:
            raise KeyError("Job not found")
        row = dict(row)
        row["spec"] = json.loads(row["spec"])
        row["data"] = json.loads(row["data"])
        return row

    def jobs(self, kind=None):
        with self.db() as db:
            rows = db.execute(
                "SELECT id FROM jobs "
                + ("WHERE kind=? " if kind else "")
                + "ORDER BY created DESC LIMIT 100",
                ((kind,) if kind else ()),
            ).fetchall()
        return [self.job(r["id"]) for r in rows]

    def update_job(self, id, status=None, **data):
        with self.db() as db:
            row = db.execute(
                "SELECT status,data FROM jobs WHERE id=?", (id,)
            ).fetchone()
            current = json.loads(row["data"])
            current.update(data)
            db.execute(
                "UPDATE jobs SET status=?,data=? WHERE id=?",
                (status or row["status"], json.dumps(current), id),
            )

    def interrupt(self):
        with self.db() as db:
            for row in db.execute(
                "SELECT id FROM jobs WHERE kind='research' AND status IN ('queued','running','cancelling')"
            ).fetchall():
                db.execute(
                    "INSERT INTO research_events(job,created,kind,message,data) VALUES(?,?,?,?,?)",
                    (
                        row["id"],
                        time.time(),
                        "session.interrupted",
                        "The server restarted. This research session was interrupted; recorded output is preserved.",
                        "{}",
                    ),
                )
            db.execute(
                "UPDATE jobs SET status='interrupted' WHERE status IN ('queued','running','cancelling')"
            )

    def append_event(self, job, kind, message, data=None):
        with self.db() as db:
            db.execute(
                "INSERT INTO research_events(job,created,kind,message,data) VALUES(?,?,?,?,?)",
                (job, time.time(), kind, message, json.dumps(data or {})),
            )

    def events(self, job, after=0, limit=500):
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM research_events WHERE job=? AND seq>? ORDER BY seq LIMIT ?",
                (job, after, limit),
            ).fetchall()
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]
