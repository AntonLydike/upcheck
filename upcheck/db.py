from collections import defaultdict
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
import sqlite3
from threading import Lock
from typing import Generator
from upcheck.model import ConnCheckRes, Incident, Snapshot

DB_PATH = "upcheck.db"

SCHEMA = """
CREATE TABLE checks (
    check_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    duration REAL NOT NULL,
    size INTEGER NOT NULL,
    status INTEGER NOT NULL,
    passed BOOL NOT NULL,
    errors TEXT NOT NULL,
    PRIMARY KEY (check_name, timestamp)
);

CREATE TABLE snapshots (
    uuid TEXT NOT NULL,
    check_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
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

_POOL:dict[bool, list[sqlite3.Connection]] = {True: [], False: []}
_POOL_LOCK = Lock()

@contextmanager
def with_conn(db_path: str = DB_PATH, rdonly: bool = False) -> Generator[sqlite3.Connection, None, None]:
    conn = None

    with _POOL_LOCK:
        if _POOL[rdonly]:
            conn = _POOL[rdonly].pop(0)
    if conn is None:
        conn = sqlite3.connect(f'file:{db_path}{'?mode=ro' if rdonly else ''}', check_same_thread=False, autocommit=False, uri=True)
        conn.row_factory = sqlite3.Row

    conn.rollback();

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


def read_histogramm(conn: sqlite3.Connection | None, timespan: timedelta = timedelta(days=1), end: datetime | None = None, buckets: int = 24 * 4) -> dict[str, Sequence[Sequence[ConnCheckRes]]]:
    if conn is None:
        with with_conn(rdonly=True):
            return read_histogramm(conn, timespan, start)
    if end is None:
        end = datetime.now()
    start = end - timespan
    data = defaultdict(lambda: [list() for _ in range(buckets)])

    minutes_per_bucket = int(timespan.total_seconds() / 60 / buckets)
    print(start, end, minutes_per_bucket)
    for row in conn.execute('SELECT * FROM checks WHERE ? < timestamp AND timestamp < ?', (start.isoformat(), end.isoformat())):
        item = ConnCheckRes(
            row['check_name'],
            datetime.fromisoformat(row['timestamp']),
            row['duration'],
            row['size'],
            row['status'],
            row['passed'],
            row['errors'].split("\n"),
        )
        bucket = int(((item.time - start).total_seconds() / 60) / (minutes_per_bucket))
        data[item.check][bucket].append(item)

    return data


def save_check(conn: sqlite3.Connection, res: ConnCheckRes):
    conn.execute("INSERT INTO checks(check_name, timestamp, duration, size, status, passed, errors) VALUES (?,?,?,?,?,?,?)", (
        res.check,
        res.time.isoformat(),
        res.duration,
        res.size,
        res.status,
        res.passed,
        "\n".join(res.errors)
    ))


def save_snapshot(conn: sqlite3.Connection, snap: Snapshot):
    conn.execute("INSERT INTO snapshots(uuid, check_name, timestamp, duration, size, status, headers, content) VALUES (?,?,?,?,?,?,?,?)", (
        snap.uuid,
        snap.check,
        snap.timestamp.isoformat(),
        snap.duration,
        snap.size,
        snap.status,
        json.dumps(snap.headers),
        snap.content,
    ))

def all_time_stats(conn: sqlite3.Connection) -> dict[str, float]:
    return  {
        row['check_name']: row['uptime'] 
        for row in conn.execute("SELECT check_name, AVG(passed) AS uptime FROM checks GROUP BY check_name")
    }


def incidents(conn: sqlite3.Connection) -> dict[str, Sequence[Incident]]:
    conn.execute("SELECT * FROM checks")
