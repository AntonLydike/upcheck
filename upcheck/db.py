from collections import defaultdict
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
import sqlite3
from threading import Lock
import time
from typing import Generator
from upcheck.model import ConnCheckRes, Incident, Snapshot

DB_PATH = "upcheck.db"

SCHEMA = """
CREATE TABLE checks (
    check_name TEXT NOT NULL,
    timestamp REAL NOT NULL,
    duration REAL,
    size INTEGER,
    status INTEGER,
    passed BOOL NOT NULL,
    errors TEXT NOT NULL,
    PRIMARY KEY (check_name, timestamp)
);

CREATE TABLE snapshots (
    uuid TEXT NOT NULL,
    check_name TEXT NOT NULL,
    timestamp REAL NOT NULL,
    duration REAL NOT NULL,
    size INT NOT NULL,
    status INT NOT NULL,
    headers TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (uuid)
);

CREATE INDEX snapshots_name ON snapshots (check_name, timestamp);

CREATE TABLE incidents (
    uuid TEXT NOT NULL,
    check_name TEX NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    notes TEXT NOT NULL,
    PRIMARY KEY (uuid)
);

CREATE INDEX incidents_time ON incidents (start_time, end_time);
CREATE INDEX incidents_check ON incidents (check_name);
"""

def initialize_db(db_path: str = DB_PATH, soft: bool = False):
    if os.path.exists(db_path):
        if soft:
            return
        raise RuntimeError("Cannot create db: already exists")
    conn = sqlite3.connect(db_path)
    conn.commit()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


_POOL: dict[bool, list[sqlite3.Connection]] = {True: [], False: []}
_POOL_LOCK = Lock()


@contextmanager
def with_conn(
    db_path: str = DB_PATH, rdonly: bool = False
) -> Generator[sqlite3.Connection, None, None]:
    conn = None

    with _POOL_LOCK:
        if _POOL[rdonly]:
            conn = _POOL[rdonly].pop(0)
    if conn is None:
        conn = sqlite3.connect(
            f"file:{db_path}{'?mode=ro' if rdonly else ''}",
            check_same_thread=False,
            autocommit=False,
            uri=True,
        )
        conn.row_factory = sqlite3.Row
        if not rdonly:
            conn.execute('PRAGMA optimize=0x10002;')

    conn.rollback()

    try:
        yield conn
        conn.commit()
    except:
        conn.rollback()
        # discard connections where exceptions occured
        conn.close()
        raise

    with _POOL_LOCK:
        _POOL[rdonly].append(conn)


def read_histogram_new(
    conn: sqlite3.Connection,
    timespan: timedelta,
    end: datetime,
    buckets: int,
):
    res = conn.execute(
        """
WITH bucketed AS (
    SELECT
        check_name,
        timestamp,
        passed,
        LN(duration) AS duration
    FROM checks
    WHERE timestamp >= :start_date
      AND timestamp < :end_date
),
per_bucket AS (
    SELECT
        check_name,
        CAST((timestamp - :start_date) / :seconds_per_bucket AS INTEGER) AS bucket,
        AVG(passed) AS avg_uptime,
        EXP(AVG(duration)) AS geomean_latency,
        NULL AS latency_max
    FROM bucketed
    GROUP BY check_name, bucket
),
overall AS (
    SELECT
        check_name,
        NULL AS bucket,
        AVG(passed) AS avg_uptime,
        EXP(AVG(duration)) AS geomean_latency,
        EXP(MAX(duration)) as latency_max
    FROM bucketed
    GROUP BY check_name
)
SELECT * FROM per_bucket
UNION ALL
SELECT * FROM overall
""",
        {
            "start_date": (end - timespan).timestamp(),
            "end_date": (end).timestamp(),
            "seconds_per_bucket": timespan.total_seconds() / buckets,
        },
    )
    data = {}
    for row in res:
        bucket = row["bucket"]
        check = row["check_name"]
        if check not in data:
            data[check] = {
                "hist_latency": [float("nan")] * buckets,
                "hist_uptime": [float("nan")] * buckets,
                "uptime": 0,
                "latency_geomean": 1,
                "latency_max": 1,
            }
        if bucket is None:
            data[check]["uptime"] = row["avg_uptime"]
            data[check]["latency_geomean"] = row["geomean_latency"]
            data[check]["latency_max"] = row["latency_max"]
        else:
            data[check]["hist_latency"][bucket] = row["geomean_latency"]
            data[check]["hist_uptime"][bucket] = row["avg_uptime"]
    return data


def save_check(conn: sqlite3.Connection, res: ConnCheckRes):
    conn.execute(
        "INSERT INTO checks(check_name, timestamp, duration, size, status, passed, errors) VALUES (?,?,?,?,?,?,?)",
        (
            res.check,
            res.time.timestamp(),
            res.duration,
            res.size,
            res.status,
            res.passed,
            "\n".join(res.errors),
        ),
    )


def save_snapshot(conn: sqlite3.Connection, snap: Snapshot):
    conn.execute(
        "INSERT INTO snapshots(uuid, check_name, timestamp, duration, size, status, headers, content) VALUES (?,?,?,?,?,?,?,?)",
        (
            snap.uuid,
            snap.check,
            snap.timestamp.timestamp(),
            snap.duration,
            snap.size,
            snap.status,
            json.dumps(snap.headers),
            snap.content,
        ),
    )


def all_time_stats(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    return {
        row["check_name"]: {
            k: row[k] for k in ("total_uptime", "total_latency_geomean")
        }
        for row in conn.execute(
            "SELECT check_name, AVG(passed) AS total_uptime, exp(avg(log(duration))) as total_latency_geomean FROM checks GROUP BY check_name"
        )
    }


def incidents(conn: sqlite3.Connection) -> dict[str, Sequence[Incident]]:
    conn.execute("SELECT * FROM checks")
